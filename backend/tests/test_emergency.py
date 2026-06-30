"""Tier 2 — the emergency fund and its denominator.

The emergency fund is a singleton whose target is *derived* (coverage_months x
average essential monthly spend), never stored. essential_monthly_spend averages
only essential-tagged categories, over the months that actually have spend.
"""
import ledger


def _essentials(make_category, make_entry, user):
    make_category(user, "Food", kind="essential")
    make_category(user, "Fun", kind="discretionary")
    # essential spend: 100 in May, 200 in June -> average 150 across 2 months
    make_entry(user, amount=100, from_account_id=None, to_account_id=None,
               category="Food", date="2026-05-15")
    make_entry(user, amount=200, from_account_id=None, to_account_id=None,
               category="Food", date="2026-06-15")
    # discretionary spend is excluded from the essential average
    make_entry(user, amount=500, from_account_id=None, to_account_id=None,
               category="Fun", date="2026-06-20")


def test_essential_monthly_spend_averages_only_essentials(db, user, make_category, make_entry):
    _essentials(make_category, make_entry, user)
    assert round(ledger.essential_monthly_spend(db, user), 2) == 150.00


def test_ensure_emergency_creates_singleton_when_absent(db, user):
    import models
    g = ledger._ensure_emergency(db, user)
    assert g.is_emergency is True
    count = db.query(models.Goal).filter(
        models.Goal.user_id == user.id,
        models.Goal.is_emergency == True,   # noqa: E712
    ).count()
    assert count == 1


def test_ensure_emergency_collapses_duplicates(db, user, make_goal):
    import models
    make_goal(user, name="EF1", is_emergency=True, coverage_months=6)
    make_goal(user, name="EF2", is_emergency=True, coverage_months=6)
    ledger._ensure_emergency(db, user)
    remaining = db.query(models.Goal).filter(
        models.Goal.user_id == user.id,
        models.Goal.is_emergency == True,   # noqa: E712
    ).count()
    assert remaining == 1                   # the stray duplicate was demoted


def test_emergency_target_is_derived_not_stored(db, user, make_category, make_entry, make_goal):
    _essentials(make_category, make_entry, user)          # essential avg = 150
    g = make_goal(user, name="Emergency fund", is_emergency=True,
                  coverage_months=6, in_distribution=True, target_amount=None)
    view = ledger.goals_view(db, user)
    ef = next(x for x in view["goals"] if x["is_emergency"])
    assert ef["target_amount"] == 900.00     # 6 months x 150 essential spend
    assert g.target_amount is None           # nothing was stored on the goal rowpython -m pytest