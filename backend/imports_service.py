"""Review + post service for imports (design lock §1, §2, Properties I/K/L/M).

Turns confirmed `ImportCandidate` rows into real `LedgerEntry` rows via the
existing `ledger.post_entry` (so imports share the exact same append path,
FX conversion, and derivation as manual entries), handles candidate edits
(recomputing the content dedup key when economic fields change), and deletes a
whole import — staging *and* its posted ledger entries (Property I).

Import DAG: imports_service -> ingestion, ledger, fx, models. No cycle.
"""
from fastapi import HTTPException

import fx
import ledger
import ingestion
import models

_EDITABLE_ECON = ("amount", "date", "direction", "currency")


def apply_edit(db, user, candidate, *, category=None, counterparty_label=None,
               amount=None, date=None, direction=None, currency=None):
    """Edit a pending candidate. Economic edits (amount/date/direction/currency)
    recompute the content dedup key and re-classify against the posted set;
    label/category edits do not touch the key (the salted counterparty hash is
    derived from the original raw, which we no longer hold — J2)."""
    if candidate.status not in ("pending", "duplicate"):
        raise HTTPException(status_code=409,
                            detail=f"Candidate is '{candidate.status}' and can no longer be edited.")

    if category is not None:
        candidate.category = category
    if counterparty_label is not None:
        candidate.counterparty_label = counterparty_label

    econ_changed = False
    if amount is not None:
        candidate.amount = round(float(amount), 2)
        econ_changed = True
    if date is not None:
        candidate.date = ingestion._norm_date(date)
        econ_changed = True
    if direction is not None:
        candidate.direction = ingestion._norm_direction(direction)
        econ_changed = True
    if currency is not None:
        candidate.currency = ingestion._norm_currency(currency)
        econ_changed = True

    if econ_changed:
        candidate.idempotency_key = ingestion.content_key(
            date=candidate.date, amount=candidate.amount,
            currency=candidate.currency, direction=candidate.direction,
            counterparty_hash=candidate.counterparty_hash)
        nkey = ingestion.native_key(candidate.batch.source_type, candidate.source_ref)
        status, flag = ingestion.classify_duplicate(
            nkey, candidate.idempotency_key,
            ingestion._posted_native_keys(db, user),
            ingestion._posted_content_keys(db, user),
            set(), set())
        candidate.status, candidate.review_flag = status, flag

    db.commit()
    db.refresh(candidate)
    return candidate


def post_batch(db, user, batch):
    """Post every still-`pending` candidate into the immutable ledger.

    Per candidate: re-check the exact native key against the live posted set
    (race-safe: never double-posts an exact source-native duplicate); resolve
    direction to wallet accounts; append via post_entry (FX applied inside);
    stamp idempotency_key + source_key + provenance link. A single row's FX
    failure flags that row 'fx_failed' and is skipped — the batch is not failed.
    """
    spend = ledger.spending_account(db, user.id)
    if spend is None:
        raise HTTPException(status_code=400, detail="No wallet account found.")

    posted_native = ingestion._posted_native_keys(db, user)
    posted = skipped = fx_failed = 0

    pending = db.query(models.ImportCandidate).filter_by(
        batch_id=batch.id, user_id=user.id, status="pending").all()

    for c in pending:
        nkey = ingestion.native_key(batch.source_type, c.source_ref)
        if nkey and nkey in posted_native:
            c.status, c.review_flag = "duplicate", "exact_duplicate"
            skipped += 1
            continue

        frm, to = (spend.id, None) if c.direction == "out" else (None, spend.id)
        try:
            entry = ledger.post_entry(
                db, user, amount=c.amount, currency=c.currency,
                from_account_id=frm, to_account_id=to, date=c.date,
                category=c.category, counterparty=c.counterparty_label,
                batch_id=batch.id, wallet_linked=True, inferred=False)
        except fx.FXUnavailableError:
            c.review_flag = "fx_failed"          # stays pending; user can retry later
            fx_failed += 1
            continue

        entry.idempotency_key = c.idempotency_key
        entry.source_key = nkey
        db.flush()                               # assign entry.id
        c.status, c.review_flag = "confirmed", None
        c.posted_entry_id = entry.id
        if nkey:
            posted_native.add(nkey)
        posted += 1

    _recount(db, batch)
    db.commit()
    return {"posted": posted, "skipped_duplicate": skipped, "fx_failed": fx_failed}


def delete_import(db, user, batch):
    """Property I: remove the whole import — its posted ledger entries first
    (balances are derived, so they simply recompute), then the staging
    candidates, then the batch. All scoped to the owner."""
    posted = db.query(models.LedgerEntry).filter_by(
        user_id=user.id, batch_id=batch.id).delete(synchronize_session=False)
    db.query(models.ImportCandidate).filter_by(
        user_id=user.id, batch_id=batch.id).delete(synchronize_session=False)
    db.delete(batch)
    db.commit()
    return {"deleted_batch": batch.id, "removed_ledger_entries": posted}


def _recount(db, batch):
    def n(status):
        return db.query(models.ImportCandidate).filter_by(
            batch_id=batch.id, status=status).count()
    batch.count_posted = n("confirmed")
    batch.count_duplicate = n("duplicate")
    batch.count_rejected = n("rejected")
    batch.status = "posted" if n("pending") == 0 else "partial"