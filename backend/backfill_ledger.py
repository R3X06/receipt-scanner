"""One-time backfill: rewrites existing expenses, income, and savings into the
unified ledger. Non-destructive (legacy tables are left intact) and idempotent
(skips users who already have ledger rows). Run once locally, once against prod."""
from database import SessionLocal, engine, Base
import models
import migrate

# Bring the schema up to date before reading/writing — creates the new ledger
# tables and adds the new user columns if they're missing (the same thing
# uvicorn does on startup).
Base.metadata.create_all(bind=engine)
migrate.run()

# default essential/discretionary tags — edit freely afterwards in the app
DEFAULT_CATEGORY_KINDS = {
    "Food & Drink": "essential",
    "Transport": "essential",
    "Utilities": "essential",
    "Health": "essential",
    "Shopping": "discretionary",
    "Entertainment": "discretionary",
    "Other": None,
    "Uncategorized": None,
}


def backfill():
    db = SessionLocal()
    try:
        for user in db.query(models.User).all():
            already = db.query(models.LedgerEntry).filter(models.LedgerEntry.user_id == user.id).count()
            if already:
                print(f"skip {user.email}: {already} ledger entries already exist")
                continue

            # 1. one Spending account
            spending = models.Account(user_id=user.id, type="spending", name="Spending")
            db.add(spending)
            db.flush()  # populate spending.id

            # 2. seed categories with their essential/discretionary tag
            for name, kind in DEFAULT_CATEGORY_KINDS.items():
                db.add(models.Category(user_id=user.id, name=name, kind=kind))

            # 3. a 'General savings' goal only if the user had any savings activity
            savings_txns = db.query(models.SavingsTransaction).filter(
                models.SavingsTransaction.user_id == user.id).all()
            general = None
            if savings_txns:
                general = models.Account(user_id=user.id, type="goal", name="General savings")
                db.add(general)
                db.flush()

            # 4. expenses -> outflow. paid-from-savings rows leave the savings goal; the rest leave Spending.
            for e in db.query(models.Expense).filter(models.Expense.user_id == user.id).all():
                src = general.id if (e.funding_source == "savings" and general) else spending.id
                db.add(models.LedgerEntry(
                    user_id=user.id, date=e.date, amount=e.amount, currency=e.currency,
                    amount_base=e.amount_base, base_currency=e.base_currency,
                    fx_rate=e.fx_rate, fx_date=e.fx_date,
                    from_account_id=src, to_account_id=None,
                    category=e.category, counterparty=e.merchant,
                    raw_ocr_text=e.raw_ocr_text, parsed_ok=e.parsed_ok,
                ))

            # 5. income -> inflow into Spending
            for i in db.query(models.IncomeTransaction).filter(models.IncomeTransaction.user_id == user.id).all():
                db.add(models.LedgerEntry(
                    user_id=user.id, date=i.date, amount=i.amount, currency=i.currency,
                    amount_base=i.amount_base, base_currency=i.base_currency,
                    fx_rate=i.fx_rate, fx_date=i.fx_date,
                    from_account_id=None, to_account_id=spending.id,
                    counterparty=i.source,
                ))

            # 6. savings: deposits enter the goal, withdrawals leave it. Treated as World<->goal
            #    so the goal balance is preserved exactly (surplus/external split isn't known historically).
            for s in savings_txns:
                frm, to = (None, general.id) if s.direction == "in" else (general.id, None)
                db.add(models.LedgerEntry(
                    user_id=user.id, date=s.date, amount=s.amount, currency=s.currency,
                    amount_base=s.amount_base, base_currency=s.base_currency,
                    fx_rate=s.fx_rate, fx_date=s.fx_date,
                    from_account_id=frm, to_account_id=to, note=s.note,
                ))

            db.commit()
            print(f"backfilled {user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()