"""Data-model gate — the ingestion staging tables persist and link, and the
`get_owned` ownership primitive (design lock §3.5, Property K) structurally
cannot return another user's row.
"""
import pytest
from fastapi import HTTPException

import models
import auth


@pytest.fixture
def other_user(db):
    u = models.User(email="other@t.com", hashed_password="x",
                    primary_currency="SGD", savings_strategy="proportional")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_batch(db, owner, source_type="csv"):
    b = models.ImportBatch(user_id=owner.id, source_type=source_type)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _make_candidate(db, owner, batch, **kw):
    base = dict(user_id=owner.id, batch_id=batch.id, amount=12.34,
                direction="out", idempotency_key="k1")
    base.update(kw)
    c = models.ImportCandidate(**base)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- models persist & defaults hold -----------------------------------------

def test_import_batch_persists_with_defaults(db, user):
    b = _make_batch(db, user)
    assert b.id
    assert b.status == "pending"          # default
    assert b.attested is False            # Property M consent flag defaults off
    assert b.count_total == 0
    assert b.candidates == []


def test_import_candidate_persists_and_links_batch(db, user):
    b = _make_batch(db, user)
    c = _make_candidate(db, user, b, counterparty_label="Mum",
                        counterparty_masked="transfer ***8821")
    assert c.id
    assert c.status == "pending"          # default
    assert c.batch.id == b.id             # candidate -> batch
    assert b.candidates[0].id == c.id     # batch -> candidates


def test_candidate_holds_no_raw_counterparty_identity(db, user):
    # Property J2: only label / salted hash / masked display — never a raw
    # name, NRIC, phone, or raw artifact column.
    cols = set(models.ImportCandidate.__table__.columns.keys())
    assert {"counterparty_label", "counterparty_hash", "counterparty_masked"} <= cols
    assert not (cols & {"counterparty_name", "nric", "phone", "raw_artifact", "raw_text"})


def test_ledger_entry_has_idempotency_key_column(db, user):
    assert "idempotency_key" in models.LedgerEntry.__table__.columns.keys()


# --- get_owned: Property K ---------------------------------------------------

def test_get_owned_returns_owners_row(db, user):
    b = _make_batch(db, user)
    got = auth.get_owned(db, models.ImportBatch, b.id, user)
    assert got.id == b.id


def test_get_owned_is_404_across_users(db, user, other_user):
    # ★ Property K: the other user cannot fetch this user's batch — scoped out.
    b = _make_batch(db, user)
    with pytest.raises(HTTPException) as ei:
        auth.get_owned(db, models.ImportBatch, b.id, other_user)
    assert ei.value.status_code == 404


def test_get_owned_is_404_for_missing_row(db, user):
    with pytest.raises(HTTPException) as ei:
        auth.get_owned(db, models.ImportBatch, "no-such-id", user)
    assert ei.value.status_code == 404


def test_get_owned_works_for_candidates_too(db, user, other_user):
    b = _make_batch(db, user)
    c = _make_candidate(db, user, b)
    assert auth.get_owned(db, models.ImportCandidate, c.id, user).id == c.id
    with pytest.raises(HTTPException):
        auth.get_owned(db, models.ImportCandidate, c.id, other_user)