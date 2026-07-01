"""PDF statement adapter gate — table extraction (reusing the CSV row logic)
and the low-confidence text-line fallback, on PDFs generated at test time.
"""
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.pdfgen import canvas

import models
import ingestion
from pdf_adapter import PdfAdapter, _parse_text_lines


def _table_pdf(data):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    t = Table(data)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    doc.build([t])
    return buf.getvalue()


def _text_pdf(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 18
    c.save()
    return buf.getvalue()


# --- table path (primary) ----------------------------------------------------

def test_table_pdf_signed_amount():
    pdf = _table_pdf([
        ["Date", "Description", "Amount"],
        ["10/06/2026", "Kopitiam", "-12.50"],
        ["01/06/2026", "Salary", "4000.00"],
    ])
    txns = PdfAdapter().parse(pdf)
    assert len(txns) == 2
    out = next(t for t in txns if t.amount == 12.50)
    inc = next(t for t in txns if t.amount == 4000.0)
    assert out.direction == "out" and out.date == "2026-06-10"
    assert out.counterparty_raw == "Kopitiam"
    assert inc.direction == "in"


def test_table_pdf_debit_credit():
    pdf = _table_pdf([
        ["Transaction Date", "Details", "Withdrawal", "Deposit"],
        ["10/06/2026", "NTUC", "45.20", ""],
        ["02/06/2026", "Refund", "", "15.00"],
    ])
    txns = PdfAdapter().parse(pdf)
    assert [t.direction for t in txns] == ["out", "in"]
    assert [t.amount for t in txns] == [45.20, 15.00]


# --- text-line fallback ------------------------------------------------------

def test_text_line_parser_unit():
    text = (
        "ACME BANK STATEMENT\n"
        "10/06/2026 Kopitiam -12.50\n"
        "01/06/2026 Salary 4,000.00 5,000.00\n"   # amount + running balance
        "not a transaction line\n"
    )
    txns = _parse_text_lines(text)
    assert len(txns) == 2
    assert txns[0].amount == 12.50 and txns[0].direction == "out"
    assert txns[0].confidence == 0.4                # low-confidence fallback
    # second line: prior-of-two amounts is the txn (4000), balance (5000) ignored
    assert txns[1].amount == 4000.0


def test_text_pdf_falls_back_to_lines():
    pdf = _text_pdf([
        "MY BANK e-Statement",
        "10/06/2026 Grab -9.90",
        "11/06/2026 Payroll 3000.00",
    ])
    txns = PdfAdapter().parse(pdf)
    assert len(txns) == 2
    assert all(t.confidence == 0.4 for t in txns)   # no ruled table -> line fallback


# --- robustness --------------------------------------------------------------

def test_non_pdf_returns_empty():
    assert PdfAdapter().parse(b"this is not a pdf") == []
    assert PdfAdapter().parse("not bytes") == []


def test_adapter_satisfies_port():
    assert isinstance(PdfAdapter(), ingestion.IngestionAdapter)


# --- end to end through the pipeline -----------------------------------------

def test_pdf_through_pipeline(db, user):
    pdf = _table_pdf([
        ["Date", "Description", "Amount"],
        ["10/06/2026", "Kopitiam", "-12.50"],
    ])
    batch = ingestion.ingest(db, user, PdfAdapter(), pdf)
    assert batch.count_total == 1
    c = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).one()
    assert c.amount == 12.50 and c.direction == "out"
    assert c.counterparty_label == "Kopitiam"       # statement descriptor revealed (reveal_label=True)