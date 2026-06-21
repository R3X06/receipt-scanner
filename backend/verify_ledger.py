from database import SessionLocal
import models


def base_amt(e):
    return e.amount_base if e.amount_base is not None else e.amount


def verify():
    db = SessionLocal()
    try:
        for user in db.query(models.User).all():
            entries = db.query(models.LedgerEntry).filter(models.LedgerEntry.user_id == user.id).all()
            accounts = db.query(models.Account).filter(models.Account.user_id == user.id).all()
            cur = user.primary_currency or "SGD"
            print(f"\n=== {user.email} ===")

            net_worth = 0.0
            for acc in accounts:
                inflow = sum(base_amt(e) for e in entries if e.to_account_id == acc.id)
                outflow = sum(base_amt(e) for e in entries if e.from_account_id == acc.id)
                bal = inflow - outflow
                net_worth += bal
                print(f"  {acc.type:8} {acc.name:18} = {cur} {bal:,.2f}")

            income = sum(base_amt(e) for e in entries if e.from_account_id is None)
            spending = sum(base_amt(e) for e in entries if e.to_account_id is None)
            print(f"  -- income in:   {cur} {income:,.2f}")
            print(f"  -- spending out:{cur} {spending:,.2f}")
            print(f"  -- net worth:   {cur} {net_worth:,.2f}")
    finally:
        db.close()


if __name__ == "__main__":
    verify()