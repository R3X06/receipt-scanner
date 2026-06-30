"""Tier 2 — the monthly cash-flow statement (ledger.cashflow), the advisory layer.

Key semantics under test: an inferred opening balance is NOT income; an unlinked
expense is excluded from advisory spending; savings transfers net; the savings
rate is surplus/income; and only the requested month is counted.
"""
import ledger

MONTH = "2026-06"


def _setup(make_account, user):
    spend = make_account(user, "spending")
    sav = make_account(user, "savings")
    return spend, sav


def test_income_counted_but_inferred_opening_balance_is_not(db, user, make_account, make_entry):
    spend, _ = _setup(make_account, user)
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id,
               date="2026-06-01")                                   # real income
    make_entry(user, amount=500, from_account_id=None, to_account_id=spend.id,
               date="2026-06-01", inferred=True)                    # opening balance
    cf = ledger.cashflow(db, user, month=MONTH)
    assert cf["income"] == 1000.00     # the 500 opening balance is excluded


def test_linked_expense_counted_unlinked_excluded(db, user, make_account, make_entry):
    spend, _ = _setup(make_account, user)
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=None,
               date="2026-06-10", wallet_linked=True)
    make_entry(user, amount=100, from_account_id=spend.id, to_account_id=None,
               date="2026-06-11", wallet_linked=False)              # untracked money
    cf = ledger.cashflow(db, user, month=MONTH)
    assert cf["spending"] == 300.00    # unlinked 100 not in advisory spending


def test_savings_transfers_net(db, user, make_account, make_entry):
    spend, sav = _setup(make_account, user)
    make_entry(user, amount=200, from_account_id=spend.id, to_account_id=sav.id,
               date="2026-06-12")                                   # to savings
    make_entry(user, amount=50, from_account_id=sav.id, to_account_id=spend.id,
               date="2026-06-13")                                   # from savings
    make_entry(user, amount=80, from_account_id=None, to_account_id=sav.id,
               date="2026-06-14")                                   # external -> savings
    cf = ledger.cashflow(db, user, month=MONTH)
    assert cf["to_savings_net"] == 150.00       # 200 - 50
    assert cf["external_to_savings"] == 80.00


def test_savings_rate_is_surplus_over_income(db, user, make_account, make_entry):
    spend, _ = _setup(make_account, user)
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id,
               date="2026-06-01")
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=None,
               date="2026-06-10")
    cf = ledger.cashflow(db, user, month=MONTH)
    assert cf["surplus"] == 700.00
    assert cf["savings_rate"] == 0.7            # (1000 - 300) / 1000


def test_only_requested_month_is_counted(db, user, make_account, make_entry):
    spend, _ = _setup(make_account, user)
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id,
               date="2026-06-01")               # in month
    make_entry(user, amount=999, from_account_id=None, to_account_id=spend.id,
               date="2026-05-31")               # previous month -> excluded
    cf = ledger.cashflow(db, user, month=MONTH)
    assert cf["income"] == 1000.00