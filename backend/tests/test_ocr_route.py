"""/ocr and /scan upload guardrails — size cap and content-type rejection.

/ocr previously had no test coverage at all and, until this pass, no size cap
either (its sibling /scan already had one — this closes that parity gap).
Both endpoints proxy to the metered Vision API, so bounding what reaches them
matters for cost as well as correctness.
"""
import main


RECEIPT_TEXT = "KOPITIAM\nNasi Lemak 5.50\nKopi 1.40\nTOTAL 6.90\nGST INCLUDED\n"


class FakeOCR:
    def __init__(self, text):
        self._text = text

    def extract_text(self, image_bytes):
        return self._text


def _token(client, email="ocr@t.com"):
    r = client.post("/auth/signup", json={"email": email, "password": "demo1234"})
    return r.json()["access_token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


# --- /ocr: basic path, previously untested at all ----------------------------

def test_ocr_returns_parsed_receipt(client, db):
    import providers
    providers.set_ocr(FakeOCR(RECEIPT_TEXT))
    tok = _token(client)
    r = client.post(
        "/ocr",
        files={"file": ("receipt.png", b"<image bytes>", "image/png")},
        headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amount"] == 6.90
    assert body["raw_ocr_text"] == RECEIPT_TEXT
    providers.reset_ocr()


# --- size cap: both endpoints proxy to a paid API, both must bound input -----

def test_ocr_rejects_oversized_file(client, db):
    tok = _token(client)
    oversized = b"x" * (main.MAX_IMPORT_BYTES + 1)
    r = client.post(
        "/ocr",
        files={"file": ("big.png", oversized, "image/png")},
        headers=_hdr(tok))
    assert r.status_code == 413


def test_scan_rejects_oversized_file(client, db):
    tok = _token(client)
    oversized = b"x" * (main.MAX_IMPORT_BYTES + 1)
    r = client.post(
        "/scan",
        files={"file": ("big.png", oversized, "image/png")},
        data={"attested": "false"},
        headers=_hdr(tok))
    assert r.status_code == 413


# --- content-type: advisory, but should reject the obvious non-image case ---

def test_ocr_rejects_non_image_content_type(client, db):
    tok = _token(client)
    r = client.post(
        "/ocr",
        files={"file": ("statement.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        headers=_hdr(tok))
    assert r.status_code == 400


def test_scan_rejects_non_image_content_type(client, db):
    tok = _token(client)
    r = client.post(
        "/scan",
        files={"file": ("statement.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        data={"attested": "false"},
        headers=_hdr(tok))
    assert r.status_code == 400