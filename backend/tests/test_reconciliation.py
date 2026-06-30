"""Tier 2 — wallet reconciliation (ledger.wallet_reconciliation).

The running Spending balance is ordered by occurred_at, and the deepest dip below
zero is reported as the shortfall. The headline invariant: re-ordering events in
time (a backdated entry) changes the running balance and therefore the shortfall.
"""
from datetime import datetime

import ledger


def test_running_balance_dips_below_zero_is_the_shortfall(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=100, from_account_id=None, to_account_id=spend.id,
               occurred_at=datetime(2026, 6, 1))
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=None,
               occurred_at=datetime(2026, 6, 2))          # spends past the balance
    rec = ledger.wallet_reconciliation(db, user)
    assert rec["shortfall"] == 200.00                     # dipped to -200
    assert round(rec["balance"], 2) == -200.00


def test_backdated_income_reorders_and_removes_shortfall(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=100, from_account_id=None, to_account_id=spend.id,
               occurred_at=datetime(2026, 6, 1))
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=None,
               occurred_at=datetime(2026, 6, 2))
    assert ledger.wallet_reconciliation(db, user)["shortfall"] == 200.00
    # an income event dated EARLIER than everything else changes the ordering
    make_entry(user, amount=500, from_account_id=None, to_account_id=spend.id,
               occurred_at=datetime(2026, 5, 1))
    rec = ledger.wallet_reconciliation(db, user)
    assert rec["shortfall"] == 0.00                        # never goes negative now
    assert round(rec["balance"], 2) == 300.00


def test_unlinked_expense_never_touches_reconciliation(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=100, from_account_id=None, to_account_id=spend.id,
               occurred_at=datetime(2026, 6, 1))
    make_entry(user, amount=9999, from_account_id=spend.id, to_account_id=None,
               wallet_linked=False, occurred_at=datetime(2026, 6, 2))  # ignored
    rec = ledger.wallet_reconciliation(db, user)
    assert rec["shortfall"] == 0.00
    assert round(rec["balance"], 2) == 100.00