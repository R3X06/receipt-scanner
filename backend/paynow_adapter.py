"""PayNow screenshot adapter (design lock §5) — the second IngestionAdapter.

Takes a screenshot of a PayNow transfer confirmation, runs it through the OCR
provider seam, and extracts the transfer fields with plain regex — no LLM ever
touches the OCR text, so the text stays a closed injection surface (Property A;
and the counterparty is de-identified downstream because
`reveal_counterparty_label = False`, Property J2).

A screenshot is one transfer, so `parse` returns a 0- or 1-element list. The
transaction reference becomes the source-native dedup key (§2), which is what
makes two screenshots of the same transfer collapse to one.

Import DAG: paynow_adapter -> ingestion (CandidateTxn), csv_adapter (parse_date),
providers (OCR). The pipeline imports no adapters, so there is no cycle.
"""
from __future__ import annotations

import re

import providers
import csv_adapter
from ingestion import CandidateTxn


# --- currency-anchored amounts (SGD; PayNow is domestic) ---------------------
_AMOUNT_PREFIX = re.compile(r"(?:SGD|S\$|\$)\s*([0-9][0-9,]*\.\d{2})", re.I)
_AMOUNT_SUFFIX = re.compile(r"([0-9][0-9,]*\.\d{2})\s*SGD", re.I)

_OUT_RE = re.compile(r"paid to|sent to|transfer to|transferred to|debited|you paid|you sent", re.I)
_IN_RE = re.compile(r"received|credited|money in", re.I)

_REF_RE = re.compile(
    r"(?:transaction\s*(?:reference|ref|id)|reference(?:\s*(?:no|number))?|ref)"
    r"\s*(?:no\.?|number)?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-]{4,})", re.I)

_TO_RE = re.compile(r"(?:paid to|transfer(?:red)? to|sent to|\bto\b)\s*[:\-]?\s*"
                    r"([A-Z][A-Za-z][A-Za-z .,'/&-]{1,38})")
_MOBILE_RE = re.compile(r"(\+?65[\s-]?\d{4}[\s-]?\d{4}|\b\d{8}\b)")

_DATE_TXT = re.compile(r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b")
_DATE_NUM = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


def _extract_amount(text):
    vals = [float(m.group(1).replace(",", "")) for m in _AMOUNT_PREFIX.finditer(text)]
    vals += [float(m.group(1).replace(",", "")) for m in _AMOUNT_SUFFIX.finditer(text)]
    return max(vals) if vals else None          # the transfer amount is the prominent one


def _extract_direction(text):
    if _OUT_RE.search(text):
        return "out"
    if _IN_RE.search(text):
        return "in"
    return "out"                                # PayNow confirmations are usually outgoing


def _extract_reference(text):
    m = _REF_RE.search(text)
    return m.group(1) if m else None


def _extract_counterparty(text):
    # Prefer the mobile identifier: it yields a stable dedup hash and a useful
    # masked display ('***4821'), while the recipient's name — the sensitive
    # PII — is dropped entirely (reveal_counterparty_label=False, J2).
    m = _MOBILE_RE.search(text)
    if m:
        return m.group(1)
    m = _TO_RE.search(text)
    if m:
        name = m.group(1).strip(" .,-")
        if name and not name.isdigit():
            return name
    return None


def _extract_date(text):
    m = _DATE_TXT.search(text)
    if m:
        d = csv_adapter.parse_date(m.group(1))
        if d:
            return d
    m = _DATE_NUM.search(text)
    if m:
        d = csv_adapter.parse_date(m.group(1).replace("-", "/"))
        if d:
            return d
    return None


def _confidence(*, date, ref, counterparty_raw) -> float:
    """Cheap completeness proxy for a PayNow parse — Vision doesn't expose a
    numeric OCR confidence, so this counts how many of the optional fields
    (date, reference, counterparty) were successfully read. Amount is required
    to reach this point at all, so it isn't scored here. This flags badly
    incomplete parses for review; it cannot detect a single misread character
    within a field that was otherwise found."""
    score = 0.55
    if date:
        score += 0.15
    if ref:
        score += 0.15
    if counterparty_raw:
        score += 0.15
    return round(score, 2)


def extract_paynow(text: str) -> CandidateTxn | None:
    """Deterministically pull one transfer out of OCR'd PayNow text, or None if
    no amount is present (nothing worth staging)."""
    amount = _extract_amount(text or "")
    if not amount or amount <= 0:
        return None
    date = _extract_date(text)
    ref = _extract_reference(text)
    counterparty = _extract_counterparty(text)
    return CandidateTxn(
        amount=amount,
        direction=_extract_direction(text),
        date=date,
        currency="SGD",
        counterparty_raw=counterparty,
        source_ref=ref,
        confidence=_confidence(date=date, ref=ref, counterparty_raw=counterparty),
    )

_PAYNOW_MARKERS = re.compile(
    r"pay\s?now|paylah|transfer(?:red)?\s+(?:to|successful)|paid\s+to|sent\s+to|"
    r"received\s+from|transaction\s+reference|duitnow", re.I)

def looks_like_paynow(text: str) -> bool:
    """Cheap classifier for the /scan router: does this OCR'd image read like a
    PayNow transfer rather than a receipt? A single strong marker is enough;
    receipts almost never contain 'PayNow' or 'Transaction Reference'."""
    return bool(_PAYNOW_MARKERS.search(text or ""))

class PayNowAdapter:
    """IngestionAdapter for PayNow transfer screenshots."""
    source_type = "paynow"
    reveal_counterparty_label = False           # recipient identity is PII (J2)

    def __init__(self, ocr_provider=None):
        self._ocr = ocr_provider                # default resolved at parse time

    def parse(self, raw: bytes) -> list[CandidateTxn]:
        ocr = self._ocr or providers.get_ocr()
        text = (ocr.extract_text(raw)
                if isinstance(raw, (bytes, bytearray)) else str(raw))
        txn = extract_paynow(text)
        return [txn] if txn else []