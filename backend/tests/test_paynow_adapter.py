"""PayNow adapter gate — deterministic extraction from OCR'd screenshots, J2
de-identification of the recipient, source-ref dedup, and the /imports paynow
branch end to end.
"""
import models
import ingestion
from paynow_adapter import (
    extract_paynow, PayNowAdapter,
    _extract_amount, _extract_direction, _extract_reference, _extract_counterparty,
)


SAMPLE = (
    "PayLah!\n"
    "Transfer Successful\n"
    "You paid to JANE TAN\n"
    "Mobile +65 9123 4821\n"
    "SGD 50.00\n"
    "10 Jun 2026, 2:45 PM\n"
    "Transaction Reference 7734829105\n"
)

INCOMING = (
    "You received SGD 120.00 from ACME PTE LTD\n"
    "Reference: RC-556677\n"
    "01 Jun 2026\n"
)


class FakeOCR:
    def __init__(self, text):
        self._text = text

    def extract_text(self, image_bytes):
        return self._text


# --- deterministic field extraction ------------------------------------------

def test_amount_variants():
    assert _extract_amount("SGD 50.00") == 50.0
    assert _extract_amount("S$1,234.56") == 1234.56
    assert _extract_amount("$50.00") == 50.0
    assert _extract_amount("50.00 SGD") == 50.0
    assert _extract_amount("no money here") is None
    # picks the prominent (largest) currency amount
    assert _extract_amount("Fee $0.50 Amount SGD 88.00") == 88.0


def test_direction_inference():
    assert _extract_direction("You paid to Jane") == "out"
    assert _extract_direction("You received from Acme") == "in"
    assert _extract_direction("PayNow transfer") == "out"     # default


def test_reference_extraction():
    assert _extract_reference("Transaction Reference 7734829105") == "7734829105"
    assert _extract_reference("Reference: RC-556677") == "RC-556677"
    assert _extract_reference("no ref here") is None


def test_counterparty_prefers_mobile_then_name():
    # mobile is preferred (stable id + safe mask); name is the dropped PII
    assert _extract_counterparty("You paid to JANE TAN\nMobile +65 9123 4821") == "+65 9123 4821"
    assert _extract_counterparty("You paid to JANE TAN") == "JANE TAN"


def test_extract_paynow_full():
    t = extract_paynow(SAMPLE)
    assert t is not None
    assert t.amount == 50.0 and t.direction == "out" and t.currency == "SGD"
    assert t.date == "2026-06-10"
    assert t.source_ref == "7734829105"
    assert t.counterparty_raw == "+65 9123 4821"


def test_extract_paynow_incoming():
    t = extract_paynow(INCOMING)
    assert t.direction == "in" and t.amount == 120.0


def test_no_amount_yields_nothing():
    assert extract_paynow("PayNow\nTransfer\nno amount visible") is None


# --- adapter via the OCR seam ------------------------------------------------

def test_adapter_parses_via_ocr():
    txns = PayNowAdapter(ocr_provider=FakeOCR(SAMPLE)).parse(b"<image>")
    assert len(txns) == 1 and txns[0].amount == 50.0


def test_adapter_satisfies_port():
    assert isinstance(PayNowAdapter(), ingestion.IngestionAdapter)


# --- end to end through the pipeline (J2: recipient de-identified) -----------

def test_paynow_through_pipeline_deidentifies_recipient(db, user):
    adapter = PayNowAdapter(ocr_provider=FakeOCR(SAMPLE))
    batch = ingestion.ingest(db, user, adapter, b"<image>")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.direction == "out" and c.amount == 50.0
    assert c.counterparty_label is None            # reveal_label=False -> no raw name kept
    assert c.counterparty_masked == "***4821"      # trailing mobile digits only
    assert c.counterparty_hash and "JANE" not in c.counterparty_hash
    assert c.source_ref == "7734829105"


def test_same_transfer_twice_dedups_on_reference(db, user):
    adapter = PayNowAdapter(ocr_provider=FakeOCR(SAMPLE))
    b1 = ingestion.ingest(db, user, adapter, b"<image>")
    c = db.query(models.ImportCandidate).filter_by(batch_id=b1.id).one()
    # simulate it having been posted
    db.add(models.LedgerEntry(
        user_id=user.id, amount=c.amount, amount_base=c.amount, currency="SGD",
        base_currency="SGD", date=c.date, idempotency_key=c.idempotency_key,
        source_key=f"paynow:{c.source_ref}"))
    db.commit()
    b2 = ingestion.ingest(db, user, adapter, b"<image>")
    c2 = db.query(models.ImportCandidate).filter_by(batch_id=b2.id).one()
    assert c2.status == "duplicate" and c2.review_flag == "exact_duplicate"


def test_incomplete_parse_is_flagged_low_confidence(db, user):
    # Amount-only text: date, ref, and counterparty all fail to extract, so
    # confidence lands at 0.55, below MIN_IMPORT_CONFIDENCE (0.7).
    adapter = PayNowAdapter(ocr_provider=FakeOCR("PayNow SGD 50.00"))
    batch = ingestion.ingest(db, user, adapter, b"<image>")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.status == "pending"                    # still staged, not rejected
    assert c.review_flag == "low_confidence"


def test_full_parse_is_not_flagged_low_confidence(db, user):
    # SAMPLE has amount, date, ref, and counterparty -> confidence 1.0.
    adapter = PayNowAdapter(ocr_provider=FakeOCR(SAMPLE))
    batch = ingestion.ingest(db, user, adapter, b"<image>")
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.review_flag is None


# --- endpoint branch ---------------------------------------------------------

def test_paynow_upload_endpoint(client, db):
    import providers
    providers.set_ocr(FakeOCR(SAMPLE))             # OCR returns a PayNow screen
    r = client.post("/auth/signup", json={"email": "pn@t.com", "password": "demo1234"})
    tok = r.json()["access_token"]
    up = client.post(
        "/imports",
        files={"file": ("shot.png", b"<image-bytes>", "image/png")},
        data={"source_type": "paynow", "attested": "true"},
        headers={"Authorization": f"Bearer {tok}"})
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["source_type"] == "paynow" and body["count_total"] == 1
    cand = body["candidates"][0]
    assert cand["direction"] == "out" and cand["counterparty_masked"] == "***4821"
    assert "counterparty_hash" not in cand         # J2: never exposed
    providers.reset_ocr()