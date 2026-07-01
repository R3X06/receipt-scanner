"""Ingestion pipeline gate — the shared parse -> normalise -> de-identify ->
dedup -> stage flow, the §2 dedup-key computation, and Property J2.

A tiny in-memory fake adapter stands in for a real source so the pipeline is
tested without any file parsing, FX, or network.
"""
import models
import ingestion
from ingestion import CandidateTxn


class FakeAdapter:
    source_type = "fake"
    reveal_counterparty_label = True

    def __init__(self, txns, reveal=True):
        self._txns = txns
        self.reveal_counterparty_label = reveal

    def parse(self, raw):
        return list(self._txns)


def _seed_posted(db, user, *, idempotency_key=None, source_key=None):
    """Put a row in the immutable ledger as if a prior import had posted it."""
    e = models.LedgerEntry(
        user_id=user.id, amount=10.0, amount_base=10.0, currency="SGD",
        base_currency="SGD", date="2026-06-01",
        idempotency_key=idempotency_key, source_key=source_key,
    )
    db.add(e)
    db.commit()


# --- the adapter satisfies the port -----------------------------------------

def test_fake_adapter_is_an_ingestion_adapter():
    assert isinstance(FakeAdapter([]), ingestion.IngestionAdapter)


# --- staging -----------------------------------------------------------------

def test_ingest_stages_candidates_under_one_batch(db, user):
    txns = [
        CandidateTxn(amount=12.50, direction="out", date="2026-06-10",
                     currency="SGD", counterparty_raw="Kopitiam"),
        CandidateTxn(amount=4000.0, direction="in", date="2026-06-01",
                     currency="SGD", counterparty_raw="Payroll"),
    ]
    batch = ingestion.ingest(db, user, FakeAdapter(txns), b"")
    assert batch.id and batch.source_type == "fake"
    assert batch.count_total == 2
    cands = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).all()
    assert len(cands) == 2
    assert {c.status for c in cands} == {"pending"}


def test_ingest_never_writes_to_the_ledger(db, user):
    before = db.query(models.LedgerEntry).count()
    ingestion.ingest(db, user, FakeAdapter(
        [CandidateTxn(amount=9.0, direction="out", date="2026-06-10")]), b"")
    assert db.query(models.LedgerEntry).count() == before  # log untouched


# --- normalisation -----------------------------------------------------------

def test_normalisation_of_currency_date_direction(db, user):
    t = CandidateTxn(amount=5, direction="OUT ", date="2026-06-10T13:45:00Z",
                     currency="usd", counterparty_raw="X")
    batch = ingestion.ingest(db, user, FakeAdapter([t]), b"")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.currency == "USD"
    assert c.direction == "out"
    assert c.date == "2026-06-10"           # truncated to calendar day


# --- Property J2: de-identification ------------------------------------------

def test_counterparty_is_deidentified_not_stored_raw(db, user):
    # PayNow-style PII-bearing source: reveal_label=False -> no label retained.
    t = CandidateTxn(amount=50, direction="out", date="2026-06-10",
                     counterparty_raw="Jane Tan 91234821")
    batch = ingestion.ingest(db, user, FakeAdapter([t], reveal=False), b"")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.counterparty_label is None             # raw name not auto-kept
    assert c.counterparty_masked == "***4821"       # trailing digits only
    assert c.counterparty_hash and len(c.counterparty_hash) == 32
    assert "Jane" not in (c.counterparty_hash or "")  # one-way


def test_merchant_descriptor_reveals_label(db, user):
    t = CandidateTxn(amount=8, direction="out", date="2026-06-10",
                     counterparty_raw="Starbucks")
    batch = ingestion.ingest(db, user, FakeAdapter([t], reveal=True), b"")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.counterparty_label == "Starbucks"


# --- §2 dedup keys & policy --------------------------------------------------

def test_content_key_excludes_raw_text_and_is_stable():
    # Same economic txn, different raw descriptor spelling -> SAME content key,
    # because only the salted hash of the counterparty enters the key and the
    # two spellings normalise identically is NOT assumed; here we prove the key
    # ignores fields outside (date, amount, currency, direction, cp-hash).
    h = ingestion._counterparty_hash("acme")
    k1 = ingestion.content_key(date="2026-06-10", amount=12.0, currency="SGD",
                               direction="out", counterparty_hash=h)
    k2 = ingestion.content_key(date="2026-06-10", amount=12.00, currency="sgd",
                               direction="OUT", counterparty_hash=h)
    assert k1 == k2                                  # normalisation is stable
    assert k1.startswith("c:")


def test_exact_native_duplicate_is_auto_skipped(db, user):
    # A prior import posted this exact source-native key.
    _seed_posted(db, user, source_key="fake:REF-1",
                 idempotency_key="c:whatever")
    t = CandidateTxn(amount=20, direction="out", date="2026-06-10",
                     source_ref="REF-1", counterparty_raw="Shop")
    batch = ingestion.ingest(db, user, FakeAdapter([t]), b"")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.status == "duplicate"                   # auto-skip
    assert c.review_flag == "exact_duplicate"
    assert batch.count_duplicate == 1


def test_content_match_is_flagged_not_skipped(db, user):
    # Compute the content key the pipeline will derive, then pre-post it.
    chash = ingestion._counterparty_hash(ingestion._norm_counterparty("Shop"))
    ckey = ingestion.content_key(date="2026-06-10", amount=20.0, currency="SGD",
                                 direction="out", counterparty_hash=chash)
    _seed_posted(db, user, idempotency_key=ckey)     # posted via another source, no native key
    t = CandidateTxn(amount=20, direction="out", date="2026-06-10",
                     counterparty_raw="Shop")          # no source_ref this time
    batch = ingestion.ingest(db, user, FakeAdapter([t]), b"")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.status == "pending"                     # NOT skipped
    assert c.review_flag == "possible_duplicate"     # flagged for review


def test_within_batch_native_duplicate_is_caught(db, user):
    t = CandidateTxn(amount=7, direction="out", date="2026-06-10",
                     source_ref="DUP", counterparty_raw="A")
    t2 = CandidateTxn(amount=7, direction="out", date="2026-06-10",
                      source_ref="DUP", counterparty_raw="A")
    batch = ingestion.ingest(db, user, FakeAdapter([t, t2]), b"")
    statuses = [c.status for c in
                db.query(models.ImportCandidate).filter_by(batch_id=batch.id).all()]
    assert statuses.count("pending") == 1
    assert statuses.count("duplicate") == 1          # second row skipped