"""
Seed script — creates a demo account and fills it with varied sample expenses
so the dashboard, charts, and AI features have realistic data to show off.

Run from the backend folder with the venv active:
    python seed.py

By default it uses your local DATABASE_URL (SQLite). To seed the LIVE Railway
Postgres, set DATABASE_URL to Railway's *public* connection string first
(see the notes Claude gave you), then run it.

Re-running is safe: it wipes the demo account's expenses and re-seeds a fresh set.
"""

import random
from datetime import date, timedelta

from database import SessionLocal, engine, Base
import models
import auth
import fx

DEMO_EMAIL = "demo@demo.com"
DEMO_PASSWORD = "demo1234"
DEMO_CURRENCY = "SGD"

NUM_EXPENSES = 45
MONTHS_BACK = 4

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


def random_date_within(months_back):
    return date.today() - timedelta(days=random.randint(0, months_back * 30))


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        if not user:
            user = models.User(
                email=DEMO_EMAIL,
                hashed_password=auth.hash_password(DEMO_PASSWORD),
                primary_currency=DEMO_CURRENCY,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        else:
            print(f"Demo user already exists: {DEMO_EMAIL}")

        # Clear existing demo expenses for a clean, repeatable seed.
        deleted = (
            db.query(models.Expense)
            .filter(models.Expense.user_id == user.id)
            .delete()
        )
        db.commit()
        if deleted:
            print(f"Cleared {deleted} existing demo expenses")

        # Cache FX results within this run so we don't re-hit the API for the
        # same date + currency pair.
        fx_cache = {}

        created = 0
        for _ in range(NUM_EXPENSES):
            merchant, category, currency, lo, hi = random.choice(SAMPLES)
            amount = round(random.uniform(lo, hi), 2)
            date_str = random_date_within(MONTHS_BACK).isoformat()

            key = (date_str, currency)
            if key not in fx_cache:
                fx_cache[key] = fx.convert_to_base(
                    amount=1.0,
                    currency=currency,
                    base_currency=user.primary_currency,
                    receipt_date_str=date_str,
                )
            conv = fx_cache[key]

            db.add(models.Expense(
                user_id=user.id,
                amount=amount,
                merchant=merchant,
                date=date_str,
                category=category,
                currency=currency,
                amount_base=round(amount * conv["fx_rate"], 2),
                base_currency=conv["base_currency"],
                fx_rate=conv["fx_rate"],
                fx_date=conv["fx_date"],
                raw_ocr_text="",
                parsed_ok=True,
            ))
            created += 1

        db.commit()
        print(f"Seeded {created} expenses for {DEMO_EMAIL}")
        print("Done — log in with the demo credentials to see the populated dashboard.")
    finally:
        db.close()


if __name__ == "__main__":
    main()