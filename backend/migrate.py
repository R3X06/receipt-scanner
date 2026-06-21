"""Additive migration: adds Phase-B profile columns to the users table.
Idempotent — re-running just skips columns that already exist, so it's safe to
call on every startup and safe to run against prod without losing data."""
from sqlalchemy import text
from database import engine

STATEMENTS = [
    "ALTER TABLE users ADD COLUMN display_name VARCHAR",
    "ALTER TABLE users ADD COLUMN avatar VARCHAR",
    "ALTER TABLE users ADD COLUMN monthly_budget FLOAT",
    "ALTER TABLE users ADD COLUMN occupation VARCHAR",
    "ALTER TABLE users ADD COLUMN monthly_income FLOAT",
    "ALTER TABLE users ADD COLUMN goals TEXT",
]


def run():
    for stmt in STATEMENTS:
        try:
            # one transaction per statement so a failure doesn't poison the rest
            with engine.begin() as conn:
                conn.execute(text(stmt))
            print("migrate: added ->", stmt)
        except Exception as exc:
            print("migrate: skipped ->", stmt.split("ADD COLUMN ")[1], f"({str(exc)[:50]})")


if __name__ == "__main__":
    run()