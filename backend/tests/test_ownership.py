"""Tier 3 — cross-user isolation and ownership, via TestClient + fake providers.

The headline is the Gate 2 invariant: updating your own entry to point at an
account you do not own is rejected (400). Also: list isolation, and 404 on
mutating an entry you don't own.
"""
import models


def _signup(client, email, password="demo1234"):
    return client.post("/auth/signup", json={"email": email, "password": password}).json()["access_token"]


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _make_expense(client, token, amount=50):
    r = client.post("/ledger/expense", json={"amount": amount}, headers=_hdr(token))
    assert r.status_code == 200, r.text
    entries = client.get("/ledger/entries", headers=_hdr(token)).json()["entries"]
    return entries[0]["id"]


def test_entries_list_is_isolated_per_user(client):
    token_a = _signup(client, "a@b.com")
    token_b = _signup(client, "b@b.com")
    _make_expense(client, token_a)                      # A has one entry
    a_entries = client.get("/ledger/entries", headers=_hdr(token_a)).json()["entries"]
    b_entries = client.get("/ledger/entries", headers=_hdr(token_b)).json()["entries"]
    assert len(a_entries) == 1
    assert b_entries == []                              # B sees none of A's data


def test_update_entry_with_foreign_account_is_rejected(client, db):
    # ★ Gate 2: A owns the entry, but points it at B's account -> 400
    token_a = _signup(client, "a@b.com")
    _signup(client, "b@b.com")
    a_entry = _make_expense(client, token_a)

    b_user = db.query(models.User).filter_by(email="b@b.com").first()
    b_account = db.query(models.Account).filter_by(
        user_id=b_user.id, type="spending").first()

    r = client.put(f"/ledger/entries/{a_entry}",
                   json={"from_account_id": b_account.id}, headers=_hdr(token_a))
    assert r.status_code == 400
    assert "Invalid source account" in r.text


def test_update_foreign_entry_is_404(client):
    token_a = _signup(client, "a@b.com")
    token_b = _signup(client, "b@b.com")
    a_entry = _make_expense(client, token_a)
    # B tries to edit A's entry -> not found (scoped out)
    r = client.put(f"/ledger/entries/{a_entry}",
                   json={"note": "hijack"}, headers=_hdr(token_b))
    assert r.status_code == 404


def test_delete_foreign_entry_is_404(client):
    token_a = _signup(client, "a@b.com")
    token_b = _signup(client, "b@b.com")
    a_entry = _make_expense(client, token_a)
    r = client.delete(f"/ledger/entries/{a_entry}", headers=_hdr(token_b))
    assert r.status_code == 404
    # and it's still there for A
    a_entries = client.get("/ledger/entries", headers=_hdr(token_a)).json()["entries"]
    assert len(a_entries) == 1