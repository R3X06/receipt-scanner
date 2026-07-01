"""Source-agnostic ingestion pipeline (design lock §1–§3).

Every import source is an `IngestionAdapter` that turns raw bytes into a list of
`CandidateTxn` DTOs. The shared pipeline then normalises, de-identifies the
counterparty (Property J2), computes the two dedup keys (§2), classifies
duplicates (§2 policy), and stages the result as `ImportCandidate` rows under
one `ImportBatch`.

Invariants enforced here:
  * The immutable `LedgerEntry` log is never touched — candidates are proposals
    until a human confirms them in a later gate (Property D).
  * Money math is deterministic, never produced by an LLM (Property A).
  * Raw counterparty identity is never persisted — only a label, a salted
    one-way hash, and a masked display (Property J2).
  * Raw source bytes are not stored; they exist only for the duration of
    `parse()` (Property J1).

Import DAG: ingestion -> models. Adapters (next gate) -> ingestion. No cycle.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import models

# Stable server-side salt so a counterparty hashes identically across imports
# (required for matching). Reuses the app secret if a dedicated one isn't set;
# falls back to a clearly-labelled dev value locally.
_COUNTERPARTY_SALT = (
    os.getenv("COUNTERPARTY_SALT")
    or os.getenv("JWT_SECRET")
    or "dev-only-counterparty-salt-do-not-use-in-prod"
).encode()


# --------------------------------------------------------------------------- DTO
@dataclass
class CandidateTxn:
    """An adapter's normalised output for one transaction — in memory only.

    `counterparty_raw` lives here transiently and is de-identified before any
    write (Property J2); it is never persisted.
    """
    amount: float
    direction: str                       # 'in' | 'out'
    date: str | None = None              # ISO calendar day
    currency: str | None = None
    counterparty_raw: str | None = None
    source_ref: str | None = None        # source-native ID (exact dedup)
    category: str | None = None
    confidence: float | None = None


# -------------------------------------------------------------------------- port
@runtime_checkable
class IngestionAdapter(Protocol):
    """Port for an import source. Parallel to the FX/OCR provider seam.

    `parse` is the ONLY source-specific code; everything downstream is shared.
    `reveal_counterparty_label` is True for low-sensitivity merchant descriptors
    (bank statements) and False for PII-bearing person identifiers (PayNow).
    """
    source_type: str
    reveal_counterparty_label: bool

    def parse(self, raw: bytes) -> list[CandidateTxn]: ...


# ----------------------------------------------------------------- normalisation
def _norm_currency(c, default="SGD") -> str:
    return (c or default or "SGD").strip().upper()


def _norm_date(d) -> str | None:
    if not d:
        return None
    d = str(d).strip()
    return d[:10] if len(d) >= 10 and d[4:5] == "-" else d


def _norm_direction(direction) -> str:
    direction = (direction or "").strip().lower()
    return direction if direction in ("in", "out") else "out"


def _norm_counterparty(raw) -> str:
    """Collapse whitespace + case for stable hashing/matching. Not stored."""
    return re.sub(r"\s+", " ", (raw or "").strip()).lower()


# --------------------------------------------------------- de-identification (J2)
def _counterparty_hash(normalized: str) -> str | None:
    if not normalized:
        return None
    return hmac.new(_COUNTERPARTY_SALT, normalized.encode(),
                    hashlib.sha256).hexdigest()[:32]


def _mask(raw: str | None, *, reveal_label: bool) -> str:
    """Safe display string. Prefers trailing digits (account/phone) -> '***1234';
    otherwise the cleaned value when revealing is allowed, else a placeholder."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 4:
        return f"***{digits[-4:]}"
    if reveal_label and raw:
        return raw[:40]
    return "(hidden)"


def deidentify_counterparty(raw, *, reveal_label: bool):
    """Return (label, hash, masked) — never the raw name/identifier (J2).

    reveal_label=True  -> merchant descriptors: the cleaned descriptor is a
                          reasonable provisional label the user can edit.
    reveal_label=False -> PII-bearing identifiers (PayNow name/NRIC/phone): no
                          label is auto-filled; only hash + masked survive.
    """
    normalized = _norm_counterparty(raw)
    chash = _counterparty_hash(normalized)
    masked = _mask(raw, reveal_label=reveal_label)
    label = (raw or "").strip()[:60] if (reveal_label and raw) else None
    return label, chash, masked


# ------------------------------------------------------------------ dedup keys (§2)
def native_key(source_type: str, source_ref) -> str | None:
    """Exact, within-source key from a source-native ID (PayNow txn id /
    statement ref). None when the source provides no stable id."""
    source_ref = (source_ref or "").strip()
    return f"{source_type}:{source_ref}" if source_ref else None


def content_key(*, date, amount, currency, direction, counterparty_hash) -> str:
    """Cross-source key. Anchored ONLY on fields the counterparty does not
    control — date, amount, currency, direction — plus the *salted*
    counterparty hash. Attacker-controlled free text is excluded, so a crafted
    descriptor cannot force or avoid a collision (§2 hash hygiene).

    Note: keyed on native (amount, currency), not amount_base — a single real
    transaction has one native currency, so cross-source copies share it, and
    this keeps the dedup key free of any FX dependency or rounding drift.
    """
    basis = "|".join([
        _norm_date(date) or "",
        f"{round(float(amount), 2):.2f}",
        _norm_currency(currency),
        _norm_direction(direction),
        counterparty_hash or "",
    ])
    return "c:" + hashlib.sha256(basis.encode()).hexdigest()[:32]


# ------------------------------------------------------- duplicate classification
def _posted_native_keys(db, user) -> set:
    rows = db.query(models.LedgerEntry.source_key).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.source_key.isnot(None),
    ).all()
    return {r[0] for r in rows}


def _posted_content_keys(db, user) -> set:
    rows = db.query(models.LedgerEntry.idempotency_key).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.idempotency_key.isnot(None),
    ).all()
    return {r[0] for r in rows}


def classify_duplicate(nkey, ckey, posted_native, posted_content,
                       seen_native, seen_content):
    """(status, review_flag) per the §2 policy:

      * exact source-native match (already posted, or earlier in this batch)
            -> 'duplicate' / 'exact_duplicate'   (auto-skip; will not post)
      * content-hash match (cross-source / cross-session)
            -> 'pending'   / 'possible_duplicate' (kept, FLAGGED for review)
      * otherwise
            -> 'pending'   / None

    Conservative by design: only the exact native key auto-skips; a content
    match is never silently merged.
    """
    if nkey and (nkey in posted_native or nkey in seen_native):
        return "duplicate", "exact_duplicate"
    if ckey in posted_content or ckey in seen_content:
        return "pending", "possible_duplicate"
    return "pending", None


# ----------------------------------------------------------------- orchestration
def ingest(db, user, adapter: IngestionAdapter, raw: bytes, *, attested=False):
    """Run one import end-to-end: parse -> normalise -> de-identify -> dedup ->
    stage. Returns the persisted `ImportBatch`. Touches no `LedgerEntry`.
    """
    batch = models.ImportBatch(
        user_id=user.id,
        source_type=adapter.source_type,
        attested=bool(attested),
    )
    db.add(batch)
    db.flush()  # assign batch.id without committing

    reveal = bool(getattr(adapter, "reveal_counterparty_label", False))
    default_currency = (user.primary_currency or "SGD")
    posted_native = _posted_native_keys(db, user)
    posted_content = _posted_content_keys(db, user)
    seen_native: set = set()
    seen_content: set = set()

    total = duplicates = flagged = 0
    for t in adapter.parse(raw):
        currency = _norm_currency(t.currency, default=default_currency)
        date = _norm_date(t.date)
        direction = _norm_direction(t.direction)
        amount = round(float(t.amount), 2)

        label, chash, masked = deidentify_counterparty(
            t.counterparty_raw, reveal_label=reveal)
        nkey = native_key(adapter.source_type, t.source_ref)
        ckey = content_key(date=date, amount=amount, currency=currency,
                           direction=direction, counterparty_hash=chash)

        status, flag = classify_duplicate(
            nkey, ckey, posted_native, posted_content, seen_native, seen_content)

        db.add(models.ImportCandidate(
            user_id=user.id, batch_id=batch.id,
            source_ref=t.source_ref, idempotency_key=ckey,
            date=date, amount=amount, currency=currency, direction=direction,
            category=t.category,
            counterparty_label=label, counterparty_hash=chash,
            counterparty_masked=masked,
            confidence=t.confidence, status=status, review_flag=flag,
        ))

        if nkey:
            seen_native.add(nkey)
        seen_content.add(ckey)
        total += 1
        if status == "duplicate":
            duplicates += 1
        elif flag:
            flagged += 1

    batch.count_total = total
    batch.count_duplicate = duplicates
    db.commit()
    db.refresh(batch)
    return batch