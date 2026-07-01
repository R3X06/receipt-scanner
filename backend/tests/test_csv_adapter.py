"""CSV adapter gate — deterministic parsing of bank exports into CandidateTxn,
both common layouts, robust amount/date handling, header auto-detection, and an
end-to-end pass through the ingestion pipeline.
"""
import models
import ingestion
from csv_adapter import CsvAdapter, ColumnMapping, parse_amount, parse_date, infer_mapping


# --- amount parsing ----------------------------------------------------------

def test_parse_amount_variants():
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("S$1,234.56") == 1234.56
    assert parse_amount("-50.00") == -50.0
    assert parse_amount("(50.00)") == -50.0
    assert parse_amount("50.00 CR") == 50.0
    assert parse_amount("50.00 DR") == -50.0
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount("n/a") is None


def test_parse_date_dayfirst():
    assert parse_date("10/06/2026") == "2026-06-10"      # SG day-first
    assert parse_date("2026-06-10") == "2026-06-10"
    assert parse_date("10 Jun 2026") == "2026-06-10"
    assert parse_date("garbage") is None


def test_parse_date_monthfirst_when_requested():
    assert parse_date("06/10/2026", dayfirst=False) == "2026-06-10"


# --- header inference --------------------------------------------------------

def test_infer_prefers_debit_credit_over_amount_substring():
    m = infer_mapping(["Date", "Description", "Withdrawal Amount", "Deposit Amount", "Balance"])
    assert m.debit is not None and m.credit is not None
    assert m.amount is None                              # not fooled by '...Amount'
    assert m.usable


def test_infer_single_amount_column():
    m = infer_mapping(["Transaction Date", "Details", "Amount"])
    assert m.amount == 2 and m.debit is None and m.usable


# --- layouts -----------------------------------------------------------------

def test_signed_amount_layout():
    csv_text = (
        "Date,Description,Amount\n"
        "10/06/2026,Kopitiam,-12.50\n"
        "01/06/2026,Salary,4000.00\n"
    )
    txns = CsvAdapter().parse(csv_text.encode())
    assert len(txns) == 2
    out, inc = txns
    assert out.direction == "out" and out.amount == 12.50 and out.date == "2026-06-10"
    assert out.counterparty_raw == "Kopitiam"
    assert inc.direction == "in" and inc.amount == 4000.0


def test_debit_credit_layout():
    csv_text = (
        "Transaction Date,Details,Withdrawal,Deposit\n"
        "10/06/2026,NTUC,45.20,\n"
        "02/06/2026,Refund,,15.00\n"
    )
    txns = CsvAdapter().parse(csv_text.encode())
    assert [t.direction for t in txns] == ["out", "in"]
    assert [t.amount for t in txns] == [45.20, 15.00]


def test_preamble_lines_before_header_are_skipped():
    csv_text = (
        "Account: 123-456-789\n"
        "Statement period: Jun 2026\n"
        "\n"
        "Date,Description,Amount\n"
        "10/06/2026,Grab,-9.90\n"
    )
    txns = CsvAdapter().parse(csv_text.encode())
    assert len(txns) == 1 and txns[0].amount == 9.90


def test_explicit_mapping_and_ref_becomes_source_ref():
    csv_text = (
        "d,desc,amt,r\n"
        "2026-06-10,Shop,-5.00,TXN-001\n"
    )
    m = ColumnMapping(date=0, description=1, amount=2, ref=3)
    txns = CsvAdapter(mapping=m).parse(csv_text.encode())
    assert txns[0].source_ref == "TXN-001"
    assert txns[0].amount == 5.0 and txns[0].direction == "out"


def test_zero_and_blank_rows_skipped():
    csv_text = (
        "Date,Description,Amount\n"
        "10/06/2026,Zero,0.00\n"
        "\n"
        "11/06/2026,Real,-3.00\n"
    )
    txns = CsvAdapter().parse(csv_text.encode())
    assert len(txns) == 1 and txns[0].counterparty_raw == "Real"


def test_adapter_satisfies_port():
    assert isinstance(CsvAdapter(), ingestion.IngestionAdapter)


# --- end to end through the pipeline -----------------------------------------

def test_csv_through_pipeline_stages_candidates(db, user):
    csv_text = (
        "Date,Description,Amount,Reference No\n"
        "10/06/2026,Kopitiam,-12.50,A1\n"
        "01/06/2026,Salary,4000.00,B2\n"
    ).encode()
    batch = ingestion.ingest(db, user, CsvAdapter(), csv_text)
    assert batch.count_total == 2
    cands = db.query(models.ImportCandidate).filter_by(batch_id=batch.id).all()
    assert {c.direction for c in cands} == {"out", "in"}
    assert all(c.status == "pending" for c in cands)
    # merchant descriptor revealed as a provisional label (reveal_label=True)
    kopi = next(c for c in cands if c.amount == 12.50)
    assert kopi.counterparty_label == "Kopitiam"
    assert kopi.source_ref == "A1"


def test_reupload_same_file_flags_or_skips_on_second_pass(db, user):
    csv_text = (
        "Date,Description,Amount,Reference No\n"
        "10/06/2026,Kopitiam,-12.50,A1\n"
    ).encode()
    # First pass stages a clean candidate; simulate it having been posted by
    # writing its keys into the ledger (what the post gate will do).
    b1 = ingestion.ingest(db, user, CsvAdapter(), csv_text)
    c = db.query(models.ImportCandidate).filter_by(batch_id=b1.id).one()
    db.add(models.LedgerEntry(
        user_id=user.id, amount=c.amount, amount_base=c.amount, currency="SGD",
        base_currency="SGD", date=c.date,
        idempotency_key=c.idempotency_key, source_key=f"csv:{c.source_ref}"))
    db.commit()

    # Second upload of the same file -> exact native key already posted -> skip.
    b2 = ingestion.ingest(db, user, CsvAdapter(), csv_text)
    c2 = db.query(models.ImportCandidate).filter_by(batch_id=b2.id).one()
    assert c2.status == "duplicate"
    assert c2.review_flag == "exact_duplicate"
    assert b2.count_duplicate == 1