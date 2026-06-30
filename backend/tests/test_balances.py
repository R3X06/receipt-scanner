"""Tier 2 — balance derivation (ledger.account_balances / net_worth).

Balances are never stored; they are folded from the entry log. These tests seed
the log directly and assert the fold. NULL on an account side = "the World".
"""
import ledger


def test_income_raises_wallet(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id)
    bal = ledger.account_balances(db, user.id)
    assert round(bal[spend.id], 2) == 1000.00


def test_expense_lowers_wallet(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id)
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=None)
    bal = ledger.account_balances(db, user.id)
    assert round(bal[spend.id], 2) == 700.00


def test_unlinked_expense_leaves_all_balances_untouched(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id)
    make_entry(user, amount=400, from_account_id=spend.id, to_account_id=None,
               wallet_linked=False)           # paid from untracked money
    bal = ledger.account_balances(db, user.id)
    assert round(bal[spend.id], 2) == 1000.00  # the unlinked expense did nothing


def test_transfer_moves_between_accounts(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    sav = make_account(user, "savings")
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id)
    make_entry(user, amount=250, from_account_id=spend.id, to_account_id=sav.id)
    bal = ledger.account_balances(db, user.id)
    assert round(bal[spend.id], 2) == 750.00
    assert round(bal[sav.id], 2) == 250.00


def test_net_worth_income_expense_and_neutral_transfer(db, user, make_account, make_entry):
    spend = make_account(user, "spending")
    sav = make_account(user, "savings")
    make_entry(user, amount=1000, from_account_id=None, to_account_id=spend.id)
    assert ledger.net_worth(db, user) == 1000.00
    make_entry(user, amount=200, from_account_id=spend.id, to_account_id=None)  # expense
    assert ledger.net_worth(db, user) == 800.00
    make_entry(user, amount=300, from_account_id=spend.id, to_account_id=sav.id)  # transfer
    assert ledger.net_worth(db, user) == 800.00   # transfer is net-worth neutral
    