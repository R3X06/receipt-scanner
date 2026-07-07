"""Scan router gate — /scan does one OCR pass then routes: PayNow screenshots
into the import pipeline (staging + attestation), everything else to a receipt
draft. Plus unit coverage of the looks_like_paynow classifier.
"""
import paynow_adapter


PAYNOW_TEXT = (
    "PayLah!\nTransfer Successful\nYou paid to JANE TAN\n"
    "Mobile +65 9123 4821\nSGD 50.00\n10 Jun 2026\n"
    "Transaction Reference 7734829105\n"
)
RECEIPT_TEXT = "KOPITIAM\nNasi Lemak 5.50\nKopi 1.40\nTOTAL 6.90\nGST INCLUDED\n"


class FakeOCR:
    def __init__(self, text):
        self._text = text

    def extract_text(self, image_bytes):
        return self._text


def _token(client, email="scan@t.com"):
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


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def _scan(client, tok, attested="false"):
    return client.post(
        "/scan",
        files={"file": ("img.png", b"<image>", "image/png")},
        data={"attested": attested},
        headers=_hdr(tok))


# --- classifier --------------------------------------------------------------

def test_classifier_distinguishes():
    assert paynow_adapter.looks_like_paynow(PAYNOW_TEXT) is True
    assert paynow_adapter.looks_like_paynow(RECEIPT_TEXT) is False
    assert paynow_adapter.looks_like_paynow("") is False


# --- routing -----------------------------------------------------------------

def test_scan_routes_paynow_to_import(client, db):
    import providers
    providers.set_ocr(FakeOCR(PAYNOW_TEXT))
    tok = _token(client)
    r = _scan(client, tok, attested="true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "paynow"
    assert body["batch"]["count_total"] == 1
    cand = body["batch"]["candidates"][0]
    assert cand["direction"] == "out" and cand["counterparty_masked"] == "***4821"
    providers.reset_ocr()


def test_scan_paynow_requires_attestation(client, db):
    import providers
    providers.set_ocr(FakeOCR(PAYNOW_TEXT))
    tok = _token(client)
    r = _scan(client, tok, attested="false")
    assert r.status_code == 400
    providers.reset_ocr()


def test_scan_routes_receipt_to_draft(client, db):
    import providers
    providers.set_ocr(FakeOCR(RECEIPT_TEXT))
    tok = _token(client)
    r = _scan(client, tok)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "receipt"
    assert body["amount"] == 6.90
    assert body["raw_ocr_text"]
    providers.reset_ocr()