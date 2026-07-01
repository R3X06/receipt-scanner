"""PDF bank-statement adapter (design lock §5) — third IngestionAdapter.

Turns a bank's PDF statement into `CandidateTxn` DTOs, fully deterministically
(Property A). Two strategies, in order of reliability:

  1. **Table extraction** (primary) — pdfplumber pulls ruled tables; the rows go
     through the *same* `csv_adapter.rows_to_candidates` logic as a CSV, so
     column mapping / amount / date / direction handling is identical and
     already tested.
  2. **Text-line fallback** (borderless statements) — for each line that starts
     with a date and ends with an amount, emit a low-confidence candidate.
     Text layout loses the debit/credit column, so direction defaults to 'out'
     (the common case) and confidence is low, flagging the row for review.

Honest scope: digitally-generated statements parse well; scanned/image PDFs
(no text layer) and exotic layouts won't — those fall back to the CSV export.

Import DAG: pdf_adapter -> csv_adapter (shared row logic + parsers), ingestion
(CandidateTxn). No cycle.
"""
from __future__ import annotations

import io
import re

import pdfplumber

import csv_adapter
from ingestion import CandidateTxn


_LEADING_DATE = re.compile(
    r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})")
# an amount token, optionally signed / parenthesised / currency-prefixed / DR-CR-suffixed
_AMOUNT_TOKEN = re.compile(r"\(?-?(?:SGD|S\$|\$)?\s?\d[\d,]*\.\d{2}\)?(?:\s?(?:DR|CR))?", re.I)


class PdfAdapter:
    """IngestionAdapter for PDF bank statements."""
    source_type = "pdf"
    reveal_counterparty_label = True             # statement descriptors, not PII identifiers

    def __init__(self, mapping=None, *, dayfirst: bool = True):
        self._mapping = mapping
        self._dayfirst = dayfirst

    def parse(self, raw: bytes) -> list[CandidateTxn]:
        if not isinstance(raw, (bytes, bytearray)):
            return []
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                table_rows, text = _extract(pdf)
        except Exception:                        # not a readable PDF
            return []

        # 1) table path — reuse the CSV row logic verbatim
        if table_rows:
            cands = csv_adapter.rows_to_candidates(
                table_rows, mapping=self._mapping, dayfirst=self._dayfirst)
            if cands:
                return cands

        # 2) text-line fallback (low confidence)
        return _parse_text_lines(text, dayfirst=self._dayfirst)


def _extract(pdf):
    """Return (concatenated_table_rows, full_text)."""
    rows: list[list] = []
    texts: list[str] = []
    for page in pdf.pages:
        for table in (page.extract_tables() or []):
            for r in table:
                rows.append([(c or "").replace("\n", " ").strip() for c in r])
        texts.append(page.extract_text() or "")
    return rows, "\n".join(texts)


def _parse_text_lines(text, *, dayfirst=True):
    out: list[CandidateTxn] = []
    for line in (text or "").splitlines():
        dm = _LEADING_DATE.match(line)
        if not dm:
            continue
        date = csv_adapter.parse_date(dm.group(1), dayfirst=dayfirst)
        tokens = _AMOUNT_TOKEN.findall(line)
        if not tokens:
            continue
        # if two+ amounts, the last is usually a running balance -> use the prior
        txn_token = tokens[-2] if len(tokens) >= 2 else tokens[-1]
        signed = csv_adapter.parse_amount(txn_token)
        if not signed:
            continue
        # description = text between the date and the first amount token
        first_amt = line.find(tokens[0], dm.end())
        desc = line[dm.end():first_amt].strip(" \t-|") if first_amt > 0 else ""
        out.append(CandidateTxn(
            amount=abs(signed),
            direction="out" if signed < 0 else "in",   # unsigned -> assume outflow (review)
            date=date,
            currency=None,
            counterparty_raw=desc or None,
            source_ref=None,
            confidence=0.4,                            # low: text layout lost the debit/credit column
        ))
    return out