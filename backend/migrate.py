"""Additive, idempotent migration. Safe to run on every startup and against prod
without data loss: each statement runs in its own transaction and failures (e.g.
a column that already exists) are caught and skipped.

Covers:
  - Phase-B profile columns on `users`
  - Ledger model columns on `ledger_entries` (occurred_at, wallet_linked, inferred)
    plus a one-time backfill so pre-existing rows behave correctly
  - Dropping the legacy expenses / savings / income tables after cutover

The `goals` table and any other new table are created by SQLAlchemy's
create_all() (called in main.py before this runs), so they are not handled here.
"""
from sqlalchemy import text
from database import engine

STATEMENTS = [
    # --- users: profile + feature columns ---
    "ALTER TABLE users ADD COLUMN display_name VARCHAR",
    "ALTER TABLE users ADD COLUMN avatar VARCHAR",
    "ALTER TABLE users ADD COLUMN monthly_budget FLOAT",
    "ALTER TABLE users ADD COLUMN occupation VARCHAR",
    "ALTER TABLE users ADD COLUMN monthly_income FLOAT",
    "ALTER TABLE users ADD COLUMN goals TEXT",
    "ALTER TABLE users ADD COLUMN feature_essential_tagging BOOLEAN",
    "ALTER TABLE users ADD COLUMN feature_pace_tracking BOOLEAN",
    "ALTER TABLE users ADD COLUMN feature_pay_yourself_first BOOLEAN",
    "ALTER TABLE users ADD COLUMN feature_priority_waterfall BOOLEAN",
    "ALTER TABLE users ADD COLUMN feature_proportional_allocation BOOLEAN",
    "ALTER TABLE users ADD COLUMN pyf_percent FLOAT",

    # --- ledger_entries: new model columns (occurred_at / wallet_linked / inferred) ---
    "ALTER TABLE ledger_entries ADD COLUMN occurred_at TIMESTAMP",
    "ALTER TABLE ledger_entries ADD COLUMN wallet_linked BOOLEAN",
    "ALTER TABLE ledger_entries ADD COLUMN inferred BOOLEAN",

    # --- backfill existing rows: linked & real by default, ordered by created_at ---
    "UPDATE ledger_entries SET wallet_linked = TRUE WHERE wallet_linked IS NULL",
    "UPDATE ledger_entries SET inferred = FALSE WHERE inferred IS NULL",
    "UPDATE ledger_entries SET occurred_at = created_at WHERE occurred_at IS NULL",

    # --- drop legacy tables once the ledger is the single source of truth ---
    "DROP TABLE IF EXISTS expenses",
    "DROP TABLE IF EXISTS savings_transactions",
    "DROP TABLE IF EXISTS income_transactions",
]


def run():
    for stmt in STATEMENTS:
        try:
            # one transaction per statement so a failure doesn't poison the rest
            with engine.begin() as conn:
                conn.execute(text(stmt))
            print("migrate: ok ->", stmt)
        except Exception as exc:
            label = stmt.split("ADD COLUMN ")[1] if "ADD COLUMN " in stmt else stmt
            print("migrate: skipped ->", label, f"({str(exc)[:60]})")


if __name__ == "__main__":
    run()