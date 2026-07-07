"""Review + post gate — the /imports endpoints end to end, via TestClient.

Exercises Property M (attestation), the staging round-trip, candidate edits
with key recomputation, posting confirmed candidates into the real ledger,
Property I deletion (staging + posted entries), and Property K cross-user 404.
"""
import models


CSV = (
    "Date,Description,Amount,Reference No\n"
    "10/06/2026,Kopitiam,-12.50,A1\n"
    "01/06/2026,Salary,4000.00,B2\n"
).encode()


def _token(client, email="imp@t.com"):
    import email_utils
    orig = email_utils.send_verification_email
    captured = {}
    email_utils.send_verification_email = lambda to, token: captured.update(token=token) or True
    try:
        r = client.post("/auth/signup", json={"email": email, "password": "demo1234"})
        assert r.status_code == 200, r.text
        r2 = client.post("/auth/verify-email", json={"token": captured["token"]})
        assert r2.status_code == 200, r2.text
        return r2.json()["access_token"]
    finally:
        email_utils.send_verification_email = orig


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def _user(db, email="imp@t.com"):
    return db.query(models.User).filter_by(email=email).first()


def _upload(client, tok, data=CSV, attested="true"):
    return client.post(
        "/imports",
        files={"file": ("stmt.csv", data, "text/csv")},
        data={"source_type": "csv", "attested": attested},
        headers=_hdr(tok))


# --- Property M: attestation -------------------------------------------------

def test_upload_requires_attestation(client):
    tok = _token(client)
    r = _upload(client, tok, attested="false")
    assert r.status_code == 400
    assert "authorised" in r.json()["detail"].lower()


# --- staging round-trip ------------------------------------------------------

def test_upload_stages_candidates_and_hides_hash(client, db):
    tok = _token(client)
    r = _upload(client, tok)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count_total"] == 2 and body["status"] == "pending"
    cands = body["candidates"]
    assert {c["direction"] for c in cands} == {"out", "in"}
    # J1/J2: never leak the salted hash or any raw text
    assert all("counterparty_hash" not in c for c in cands)
    assert all("raw" not in k for c in cands for k in c)


def test_upload_rejects_unparseable(client):
    tok = _token(client)
    r = _upload(client, tok, data=b"just some text\nwith no columns\n")
    assert r.status_code == 422


# --- edit with key recomputation --------------------------------------------

def test_edit_amount_recomputes_idempotency_key(client, db):
    tok = _token(client)
    batch = _upload(client, tok).json()
    cid = batch["candidates"][0]["id"]
    before = db.get(models.ImportCandidate, cid).idempotency_key
    r = client.patch(f"/imports/candidates/{cid}",
                     json={"amount": 999.99}, headers=_hdr(tok))
    assert r.status_code == 200
    after = db.get(models.ImportCandidate, cid).idempotency_key
    assert after != before                       # economic edit -> key recomputed
    assert db.get(models.ImportCandidate, cid).amount == 999.99


def test_edit_label_does_not_change_key(client, db):
    tok = _token(client)
    batch = _upload(client, tok).json()
    cid = batch["candidates"][0]["id"]
    before = db.get(models.ImportCandidate, cid).idempotency_key
    client.patch(f"/imports/candidates/{cid}",
                 json={"counterparty_label": "My Kopi"}, headers=_hdr(tok))
    assert db.get(models.ImportCandidate, cid).idempotency_key == before


def test_reject_candidate(client, db):
    tok = _token(client)
    batch = _upload(client, tok).json()
    cid = batch["candidates"][0]["id"]
    r = client.post(f"/imports/candidates/{cid}/reject", headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["status"] == "rejected"


# --- confirm -> ledger -------------------------------------------------------

def test_confirm_posts_to_ledger(client, db):
    tok = _token(client)
    user = _user(db)
    wallet = db.query(models.Account).filter_by(
        user_id=user.id, type="spending").first()   # seeded at signup
    batch = _upload(client, tok).json()

    r = client.post(f"/imports/{batch['id']}/confirm", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["posted"] == 2 and res["fx_failed"] == 0

    entries = db.query(models.LedgerEntry).filter_by(
        user_id=user.id, batch_id=batch["id"]).all()
    assert len(entries) == 2
    # the expense uses the wallet as source; income uses it as destination
    exp = next(e for e in entries if e.amount == 12.50)
    inc = next(e for e in entries if e.amount == 4000.0)
    assert exp.from_account_id == wallet.id and exp.to_account_id is None
    assert inc.to_account_id == wallet.id and inc.from_account_id is None
    # keys + provenance link stamped
    assert all(e.idempotency_key for e in entries)
    cands = db.query(models.ImportCandidate).filter_by(batch_id=batch["id"]).all()
    assert all(c.status == "confirmed" and c.posted_entry_id for c in cands)


def test_confirm_without_wallet_400(client, db):
    tok = _token(client)
    user = _user(db)
    db.query(models.Account).filter_by(
        user_id=user.id, type="spending").delete()   # remove the seeded wallet
    db.commit()
    batch = _upload(client, tok).json()
    r = client.post(f"/imports/{batch['id']}/confirm", headers=_hdr(tok))
    assert r.status_code == 400


# --- Property I: full delete -------------------------------------------------

def test_delete_removes_staging_and_posted(client, db):
    tok = _token(client)
    batch = _upload(client, tok).json()
    client.post(f"/imports/{batch['id']}/confirm", headers=_hdr(tok))
    assert db.query(models.LedgerEntry).filter_by(batch_id=batch["id"]).count() == 2

    r = client.delete(f"/imports/{batch['id']}", headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["removed_ledger_entries"] == 2
    assert db.query(models.LedgerEntry).filter_by(batch_id=batch["id"]).count() == 0
    assert db.query(models.ImportCandidate).filter_by(batch_id=batch["id"]).count() == 0
    assert db.get(models.ImportBatch, batch["id"]) is None


# --- Property K: cross-user isolation ----------------------------------------

def test_cross_user_cannot_access_batch(client, db):
    tok_a = _token(client, "a@t.com")
    batch = _upload(client, tok_a).json()
    tok_b = _token(client, "b@t.com")
    r = client.get(f"/imports/{batch['id']}", headers=_hdr(tok_b))
    assert r.status_code == 404
    r2 = client.delete(f"/imports/{batch['id']}", headers=_hdr(tok_b))
    assert r2.status_code == 404


# --- Property L: rate cap ----------------------------------------------------

def test_rate_limit_blocks_after_cap(client, db):
    tok = _token(client)
    user = _user(db)
    for _ in range(10):                          # fill the hourly window directly
        db.add(models.ImportBatch(user_id=user.id, source_type="csv"))
    db.commit()
    r = _upload(client, tok)
    assert r.status_code == 429