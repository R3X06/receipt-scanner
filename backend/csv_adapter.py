"""CSV bank-statement adapter — the first IngestionAdapter (design lock §5).

Turns a bank's CSV export into `CandidateTxn` DTOs, fully deterministically:
no LLM touches amounts or dates (Property A). Handles the two common layouts —
a single *signed* amount column, or separate *debit/credit* columns — plus the
usual currency symbols, thousands separators, parenthesised negatives, and
trailing DR/CR markers.

Column mapping is auto-inferred from the header row by default (scanning past
any account-info preamble lines), or supplied explicitly. SG slash-dates are
read day-first.

Import DAG: csv_adapter -> ingestion (for CandidateTxn). The pipeline does not
import adapters, so there is no cycle.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime

from ingestion import CandidateTxn


_DAYFIRST_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y",
)
_MONTHFIRST_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%m/%d/%Y", "%m-%d-%Y",
    "%m/%d/%y", "%m-%d-%y",
    "%b %d %Y", "%B %d %Y", "%b %d, %Y",
)

# header keywords (lowercased substring match, except amount which is stricter)
_DATE_KEYS = ("value date", "transaction date", "posting date", "txn date", "date")
_DEBIT_KEYS = ("debit", "withdrawal", "paid out", "money out", "money_out")
_CREDIT_KEYS = ("credit", "deposit", "paid in", "money in", "money_in")
_DESC_KEYS = ("description", "details", "particulars", "narrative",
              "transaction ref1", "remarks", "reference")
_REF_KEYS = ("reference no", "transaction ref", "ref no", "transaction id", "txn ref")


@dataclass
class ColumnMapping:
    date: int | None = None
    amount: int | None = None           # single signed-amount column
    debit: int | None = None            # OR a debit/credit pair
    credit: int | None = None
    description: int | None = None
    ref: int | None = None

    @property
    def usable(self) -> bool:
        return self.date is not None and (
            self.amount is not None or self.debit is not None or self.credit is not None)


def _match(header, keys):
    for i, cell in enumerate(header):
        c = (cell or "").strip().lower()
        if c and any(k == c or k in c for k in keys):
            return i
    return None


def _match_amount(header):
    """Stricter than substring so 'Withdrawal Amount' isn't mistaken for the
    single signed-amount column."""
    for i, cell in enumerate(header):
        c = (cell or "").strip().lower()
        if c == "amount" or c.startswith("amount") or "transaction amount" in c:
            return i
    return None


def infer_mapping(header) -> ColumnMapping:
    debit = _match(header, _DEBIT_KEYS)
    credit = _match(header, _CREDIT_KEYS)
    # only use the single-amount column when there is no debit/credit pair
    amount = None if (debit is not None or credit is not None) else _match_amount(header)
    return ColumnMapping(
        date=_match(header, _DATE_KEYS),
        amount=amount,
        debit=debit,
        credit=credit,
        description=_match(header, _DESC_KEYS),
        ref=_match(header, _REF_KEYS),
    )


# ----------------------------------------------------------- deterministic parse
_PAREN = re.compile(r"^\((.*)\)$")


def parse_amount(s):
    """Bank-amount string -> signed float (negative = outflow), or None.

    Handles parenthesised negatives, trailing DR/CR, currency symbols/codes,
    and thousands separators. Purely deterministic — never an LLM (Property A).
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None

    neg = False
    m = _PAREN.match(s)
    if m:                                   # (123.45) -> negative
        neg = True
        s = m.group(1).strip()

    up = s.upper()
    if up.endswith("CR"):
        s = s[:-2].strip()
    elif up.endswith("DR"):
        neg = True
        s = s[:-2].strip()

    if s.lstrip().startswith("-"):
        neg = True
    s = re.sub(r"[^\d.]", "", s)             # drop symbols, codes, commas, spaces, signs
    if s in ("", "."):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def parse_date(s, *, dayfirst=True):
    """Bank-date string -> ISO 'YYYY-MM-DD', or None if no known format fits."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in (_DAYFIRST_FORMATS if dayfirst else _MONTHFIRST_FORMATS):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class CsvAdapter:
    """IngestionAdapter for bank CSV exports."""
    source_type = "csv"
    reveal_counterparty_label = True        # merchant descriptors, not PII identifiers

    def __init__(self, mapping: ColumnMapping | None = None, *, dayfirst: bool = True):
        self._mapping = mapping
        self._dayfirst = dayfirst

    def parse(self, raw: bytes) -> list[CandidateTxn]:
        text = (raw.decode("utf-8-sig", errors="replace")
                if isinstance(raw, (bytes, bytearray)) else str(raw))
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            return []

        return rows_to_candidates(rows, mapping=self._mapping, dayfirst=self._dayfirst)


def rows_to_candidates(rows, *, mapping: ColumnMapping | None = None, dayfirst=True):
    """Turn tabular rows (from CSV or an extracted PDF table) into CandidateTxns.

    Resolves a column mapping (explicit, or inferred by scanning the first rows
    for a header past any preamble), then maps each data row. Shared by the CSV
    and PDF adapters so both get identical amount/date/direction handling.
    """
    mapping, start = _resolve_mapping(rows, mapping)
    if mapping is None or not mapping.usable:
        return []
    out: list[CandidateTxn] = []
    for row in rows[start:]:
        if not any((c or "").strip() for c in row):
            continue                             # blank line
        txn = row_to_candidate(row, mapping, dayfirst=dayfirst)
        if txn is not None:
            out.append(txn)
    return out


def _resolve_mapping(rows, explicit):
    if explicit is not None:
        return explicit, 1                       # explicit mapping: row 0 is the header
    for idx, row in enumerate(rows[:15]):        # skip any account-info preamble
        m = infer_mapping(row)
        if m.usable:
            return m, idx + 1
    return None, 0


def row_to_candidate(row, m: ColumnMapping, *, dayfirst=True, confidence=None):
    def cell(i):
        return row[i] if (i is not None and i < len(row)) else None

    if m.debit is not None or m.credit is not None:
        dv = parse_amount(cell(m.debit))
        cv = parse_amount(cell(m.credit))
        if dv:
            signed = -abs(dv)
        elif cv:
            signed = abs(cv)
        else:
            signed = None
    else:
        signed = parse_amount(cell(m.amount))

    if not signed:                               # blank / zero / unparseable -> not a txn
        return None

    desc = (cell(m.description) or "").strip() or None
    ref = (cell(m.ref) or "").strip() or None
    return CandidateTxn(
        amount=abs(signed),
        direction="out" if signed < 0 else "in",
        date=parse_date(cell(m.date), dayfirst=dayfirst),
        currency=None,                           # account-currency export; pipeline defaults to user's base
        counterparty_raw=desc,
        source_ref=ref,
        confidence=confidence,
    )