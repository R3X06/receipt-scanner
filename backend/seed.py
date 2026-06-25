"""
Seed script — builds the demo account on the unified double-entry ledger and
fills it with realistic income, expenses, and savings so the dashboard, charts,
goals, pace tracking, and AI features have something to show.

Run from the backend folder with the venv active:
    python seed.py

Uses your local DATABASE_URL (SQLite) by default. To seed the LIVE Railway
Postgres instead, set DATABASE_URL to Railway's *public* connection string
first, then run it.

Re-running is safe and repeatable: it wipes the demo account's ledger entries
(income / expenses / transfers) and re-seeds a fresh set. The accounts,
categories, and goals are created once and left in place.
"""

import random
from datetime import date, datetime, timedelta

from database import SessionLocal, engine, Base
import models
import auth
import ledger

DEMO_EMAIL = "demo@demo.com"
DEMO_PASSWORD = "demo1234"
DEMO_CURRENCY = "SGD"

MONTHS_BACK = 4
EXPENSES_PER_MONTH = 11
MONTHLY_INCOME = 4200.0          # net salary, paid on the 1st of each month
MONTHLY_SAVINGS_DEPOSIT = 600.0  # moved from wallet into savings each month

# Categories mirror exactly what signup() creates; `kind` drives the
# essential-vs-discretionary split that feeds the emergency-fund coverage.
CATEGORIES = {
    "Food & Drink": "essential", "Transport": "essential",
    "Utilities": "essential", "Health": "essential",
    "Shopping": "discretionary", "Entertainment": "discretionary",
    "Other": None, "Uncategorized": None,
}

# (merchant, category, currency, min_amount, max_amount)
SAMPLES = [
    ("Starbucks",          "Food & Drink",  "SGD",  6, 12),
    ("McDonald's",         "Food & Drink",  "SGD",  8, 18),
    ("Ya Kun Kaya Toast",  "Food & Drink",  "SGD",  5, 14),
    ("Din Tai Fung",       "Food & Drink",  "SGD", 25, 60),
    ("Mamak Stall",        "Food & Drink",  "MYR", 12, 35),
    ("Grab",               "Transport",     "SGD",  8, 25),
    ("SMRT",               "Transport",     "SGD",  2, 5),
    ("Shell",              "Transport",     "SGD", 40, 80),
    ("Uniqlo",             "Shopping",      "SGD", 30, 120),
    ("Lazada",             "Shopping",      "SGD", 15, 90),
    ("Apple Store",        "Shopping",      "USD", 50, 400),
    ("Amazon UK",          "Shopping",      "GBP", 15, 70),
    ("Watsons",            "Health",        "SGD", 10, 45),
    ("Guardian Pharmacy",  "Health",        "SGD",  8, 60),
    ("Golden Village",     "Entertainment", "SGD", 13, 30),
    ("Spotify",            "Entertainment", "USD", 10, 12),
    ("Netflix",            "Entertainment", "SGD", 15, 23),
    ("Singtel",            "Utilities",     "SGD", 40, 90),
    ("SP Group",           "Utilities",     "SGD", 60, 150),
    ("Carrefour",          "Food & Drink",  "EUR", 20, 60),
]

# Non-emergency goals so the savings card + pace tracking have content.
# (name, target_amount, months_until_deadline)
SAMPLE_GOALS = [
    ("Japan trip", 3000.0, 8),
    ("New laptop", 1800.0, 5),
]


def month_first(months_ago):
    """First day of the month `months_ago` months before the current month."""
    today = date.today().replace(day=1)
    y, m = today.year, today.month - months_ago
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def random_day_in(d_first):
    """A random day within the month of `d_first`, never later than today."""
    if d_first.month == 12:
        nxt = date(d_first.year + 1, 1, 1)
    else:
        nxt = date(d_first.year, d_first.month + 1, 1)
    last = (nxt - timedelta(days=1)).day
    day = random.randint(1, last)
    chosen = date(d_first.year, d_first.month, day)
    return min(chosen, date.today())


def _at(d):
    """A datetime for occurred_at so the wallet reconciliation orders cleanly."""
    return datetime(d.year, d.month, d.day, 12, 0, 0)


def get_or_create_user(db):
    user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
    if user:
        print(f"Demo user already exists: {DEMO_EMAIL}")
        return user
    user = models.User(
        email=DEMO_EMAIL,
        hashed_password=auth.hash_password(DEMO_PASSWORD),
        primary_currency=DEMO_CURRENCY,
        savings_strategy="proportional",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return user


def ensure_structure(db, user):
    """Spending + Savings accounts, the category set, the emergency fund, and a
    couple of sample goals — created once, mirroring a real signup."""
    spend = ledger.spending_account(db, user.id)
    if not spend:
        spend = models.Account(user_id=user.id, type="spending", name="Spending")
        db.add(spend)
    sav = ledger.savings_account(db, user.id)
    if not sav:
        sav = models.Account(user_id=user.id, type="savings", name="Savings")
        db.add(sav)
    db.commit()

    have = {c.name for c in db.query(models.Category).filter(
        models.Category.user_id == user.id).all()}
    for name, kind in CATEGORIES.items():
        if name not in have:
            db.add(models.Category(user_id=user.id, name=name, kind=kind))
    db.commit()

    # emergency fund (singleton, participates in the remainder split). Give it a
    # senior reserve floor so it holds a visible balance in the demo and shows
    # off the reserve mechanic; clamped to its derived target by the engine.
    emergency = ledger._ensure_emergency(db, user)
    if not emergency.reserve:
        emergency.reserve = 800.0
        emergency.coverage_months = emergency.coverage_months or 6
        db.commit()

    # sample goals with deadlines so pace tracking shows "need X/mo"
    existing_goals = {g.name for g in db.query(models.Goal).filter(
        models.Goal.user_id == user.id).all()}
    rank = 1
    for name, target, months_out in SAMPLE_GOALS:
        if name in existing_goals:
            continue
        deadline = (date.today().replace(day=1)
                    + timedelta(days=int(months_out * 30.4))).isoformat()
        db.add(models.Goal(
            user_id=user.id, name=name, target_amount=target,
            deadline=deadline, priority=rank, is_emergency=False,
            in_distribution=True,
        ))
        rank += 1
    db.commit()

    return ledger.spending_account(db, user.id), ledger.savings_account(db, user.id)


def wipe_entries(db, user):
    deleted = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id).delete()
    db.commit()
    if deleted:
        print(f"Cleared {deleted} existing ledger entries")


def seed_entries(db, user, spend, sav):
    income_n = expense_n = deposit_n = 0

    for months_ago in range(MONTHS_BACK - 1, -1, -1):
        first = month_first(months_ago)

        # --- salary in (World -> Spending) on the 1st ---
        ledger.post_entry(
            db, user, amount=MONTHLY_INCOME, currency=DEMO_CURRENCY,
            from_account_id=None, to_account_id=spend.id,
            date=first.isoformat(), occurred_at=_at(first),
            counterparty="Monthly salary",
        )
        income_n += 1

        # --- expenses out (Spending -> World) spread through the month ---
        for _ in range(EXPENSES_PER_MONTH):
            merchant, category, currency, lo, hi = random.choice(SAMPLES)
            amount = round(random.uniform(lo, hi), 2)
            d = random_day_in(first)
            ledger.post_entry(
                db, user, amount=amount, currency=currency,
                from_account_id=spend.id, to_account_id=None,
                date=d.isoformat(), occurred_at=_at(d),
                category=category, counterparty=merchant,
                wallet_linked=True, parsed_ok=True,
            )
            expense_n += 1

        # --- monthly transfer to savings (Spending -> Savings) on the 5th ---
        dep_day = min(date(first.year, first.month, 5), date.today())
        ledger.post_entry(
            db, user, amount=MONTHLY_SAVINGS_DEPOSIT, currency=DEMO_CURRENCY,
            from_account_id=spend.id, to_account_id=sav.id,
            date=dep_day.isoformat(), occurred_at=_at(dep_day),
            note="Monthly savings",
        )
        deposit_n += 1

    db.commit()
    return income_n, expense_n, deposit_n


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = get_or_create_user(db)
        spend, sav = ensure_structure(db, user)
        wipe_entries(db, user)
        income_n, expense_n, deposit_n = seed_entries(db, user, spend, sav)

        bal = ledger.account_balances(db, user.id)
        goals = ledger.goals_view(db, user)
        print(f"Seeded {income_n} income, {expense_n} expenses, {deposit_n} deposits")
        print(f"  wallet  ~ {DEMO_CURRENCY} {round(bal.get(spend.id, 0.0), 2):,.2f}")
        print(f"  savings ~ {DEMO_CURRENCY} {round(bal.get(sav.id, 0.0), 2):,.2f}")
        print(f"  goals   : {', '.join(g['name'] for g in goals['goals'])}")
        print(f"Done — log in with {DEMO_EMAIL} / {DEMO_PASSWORD} to see the populated dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()