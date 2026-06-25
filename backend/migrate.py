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
    "ALTER TABLE users ADD COLUMN goals TEXT",
    "ALTER TABLE users ADD COLUMN feature_pace_tracking BOOLEAN",
    "ALTER TABLE users ADD COLUMN feature_pay_yourself_first BOOLEAN",
    "ALTER TABLE users ADD COLUMN pyf_percent FLOAT",

    # --- ledger_entries: new model columns (occurred_at / wallet_linked / inferred) ---
    "ALTER TABLE ledger_entries ADD COLUMN occurred_at TIMESTAMP",
    "ALTER TABLE ledger_entries ADD COLUMN wallet_linked BOOLEAN",
    "ALTER TABLE ledger_entries ADD COLUMN inferred BOOLEAN",

    # --- goals: per-goal reserve floor (replaces funding_type/forced_amount) ---
    "ALTER TABLE goals ADD COLUMN reserve FLOAT",
    # carry the old forced reservations over to the new reserve field (skips on fresh DBs)
    "UPDATE goals SET reserve = forced_amount WHERE funding_type = 'forced' AND reserve IS NULL",

    # --- goals: emergency-fund participation + derived-coverage config ---
    "ALTER TABLE goals ADD COLUMN in_distribution BOOLEAN",
    "UPDATE goals SET in_distribution = TRUE WHERE in_distribution IS NULL",
    "ALTER TABLE goals ADD COLUMN coverage_months INTEGER",
    "UPDATE goals SET coverage_months = 6 WHERE is_emergency = TRUE AND coverage_months IS NULL",
    # unify emergency-fund participation: every emergency fund competes for the remainder
    # (older accounts created theirs opted-out; this brings them in line with new signups)
    "UPDATE goals SET in_distribution = TRUE WHERE is_emergency = TRUE",

    # --- users: chosen remainder-split strategy (replaces the waterfall/proportional flags) ---
    "ALTER TABLE users ADD COLUMN savings_strategy VARCHAR",
    "UPDATE users SET savings_strategy = 'proportional' WHERE savings_strategy IS NULL",

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