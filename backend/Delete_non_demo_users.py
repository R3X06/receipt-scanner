"""One-off cleanup: delete every user account except the demo account
(seed.py's DEMO_EMAIL), and everything that belongs to them.

SAFETY: dry-run by default — lists what would be deleted and does nothing.
Pass --confirm to actually delete. Runs as a single transaction: SessionLocal
only autocommits on an explicit .commit() at the very end, so if anything
fails partway through, nothing is written — see database.py.

Deletion order matters and is NOT arbitrary: it follows the FK graph in
models.py child-before-parent (import_candidates references both
import_batches and ledger_entries; accounts are referenced by ledger_entries
via from/to_account_id). Getting this order wrong raises an IntegrityError in
Postgres rather than silently corrupting anything, but the transaction wrapper
means even a wrong order just rolls back cleanly.

Usage:
    python delete_non_demo_users.py              # dry run (default, safe)
    python delete_non_demo_users.py --confirm     # actually deletes

This respects whatever DATABASE_URL is set in your environment — it targets
your LOCAL db.sqlite unless you explicitly export the Railway/production
DATABASE_URL first. Check which one is active (echo $env:DATABASE_URL in
PowerShell) before passing --confirm.
"""
import argparse
import sys

from sqlalchemy.exc import OperationalError, ProgrammingError

import database
import models
from seed import DEMO_EMAIL


def _display_url(url: str) -> str:
    """DATABASE_URL for a Postgres connection embeds a password — mask it
    before printing, in case this output ever gets pasted/screenshotted."""
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true",
                        help="Actually delete. Without this flag, only prints what would happen.")
    args = parser.parse_args()

    print(f"Target database: {_display_url(database.DATABASE_URL)}")
    if ":memory:" in database.DATABASE_URL:
        # This is exactly what happens if a leftover `$env:DATABASE_URL` from an
        # earlier `pytest` run is still set in the current shell session — an
        # in-memory DB is fresh and schema-less on every connection, so this
        # would either crash with "no such table" or silently run against an
        # empty throwaway DB instead of your real one. Neither is ever what you
        # want when running this script, so refuse outright rather than guess.
        print("\nDATABASE_URL points at an in-memory SQLite database — refusing to run.\n"
             "This is almost always a leftover `$env:DATABASE_URL` from a test run "
             "still set in this shell session. Check with `echo $env:DATABASE_URL`, "
             "clear it with `Remove-Item Env:\\DATABASE_URL`, or open a fresh terminal.")
        sys.exit(1)

    db = database.SessionLocal()
    try:
        try:
            demo = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        except (OperationalError, ProgrammingError) as e:
            # "no such table" (sqlite) / relation does not exist (postgres) — the
            # schema was never created against this DB. Happens if DATABASE_URL
            # points at a fresh file/database main.py's create_all()+migrate.run()
            # has never run against, distinct from the in-memory case caught above.
            print(f"\nQuery failed: {e.orig if hasattr(e, 'orig') else e}\n"
                 f"This DB has no schema — the 'users' table doesn't exist yet. "
                 f"Either DATABASE_URL points somewhere unexpected, or this is a "
                 f"fresh database main.py has never started against. Run the app "
                 f"once against it first (which creates the schema), or double "
                 f"check DATABASE_URL.")
            sys.exit(1)
        if not demo:
            print(f"No demo user found at {DEMO_EMAIL} — refusing to run with nothing to "
                 f"protect. Run seed.py first if you meant to keep the demo account, or "
                 f"double check DATABASE_URL is pointing where you think it is.")
            sys.exit(1)

        targets = db.query(models.User).filter(models.User.id != demo.id).all()
        if not targets:
            print("No non-demo users found. Nothing to do.")
            return

        print(f"Demo account preserved: {DEMO_EMAIL} (id={demo.id})")
        print(f"\n{len(targets)} account(s) will be PERMANENTLY deleted:")
        for u in targets:
            n_entries = db.query(models.LedgerEntry).filter_by(user_id=u.id).count()
            n_accounts = db.query(models.Account).filter_by(user_id=u.id).count()
            n_batches = db.query(models.ImportBatch).filter_by(user_id=u.id).count()
            print(f"  - {u.email} (id={u.id}): {n_entries} ledger entries, "
                 f"{n_accounts} accounts, {n_batches} import batches")

        if not args.confirm:
            print("\nDry run only — nothing deleted. Re-run with --confirm to actually delete.")
            return

        target_ids = [u.id for u in targets]

        db.query(models.ImportCandidate).filter(
            models.ImportCandidate.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.ImportBatch).filter(
            models.ImportBatch.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.LedgerEntry).filter(
            models.LedgerEntry.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.Account).filter(
            models.Account.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.Category).filter(
            models.Category.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.Goal).filter(
            models.Goal.user_id.in_(target_ids)).delete(synchronize_session=False)
        db.query(models.User).filter(
            models.User.id.in_(target_ids)).delete(synchronize_session=False)

        db.commit()
        print(f"\nDeleted {len(targets)} account(s) and all their data. {DEMO_EMAIL} preserved.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()