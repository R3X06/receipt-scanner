from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.sqlite import TEXT
from sqlalchemy.orm import relationship
from database import Base
import uuid
from datetime import datetime


def gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    primary_currency = Column(String, default="SGD")
    display_name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    monthly_budget = Column(Float, nullable=True)
    occupation = Column(String, nullable=True)
    monthly_income = Column(Float, nullable=True)
    goals = Column(TEXT, default="")
    # --- feature toggles (all default on; user can switch off) ---
    feature_essential_tagging = Column(Boolean, default=True)
    feature_pace_tracking = Column(Boolean, default=True)
    feature_pay_yourself_first = Column(Boolean, default=True)
    feature_priority_waterfall = Column(Boolean, default=True)
    feature_proportional_allocation = Column(Boolean, default=True)
    pyf_percent = Column(Float, nullable=True)   # pay-yourself-first: % of logged income to auto-allocate
    created_at = Column(DateTime, default=datetime.utcnow)

    # legacy (kept until cutover)
    expenses = relationship("Expense", back_populates="owner")
    savings = relationship("SavingsTransaction", back_populates="owner")
    income = relationship("IncomeTransaction", back_populates="owner")
    # ledger
    accounts = relationship("Account", back_populates="owner")
    ledger_entries = relationship("LedgerEntry", back_populates="owner")
    categories = relationship("Category", back_populates="owner")


# ============== THE LEDGER (new foundation) ==============

class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)            # 'spending' | 'goal'
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=True)     # goals only
    deadline = Column(String, nullable=True)         # goals only, ISO date
    priority = Column(Integer, default=0)            # waterfall order (lower fills first)
    is_emergency = Column(Boolean, default=False)    # marks the emergency fund
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="accounts")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(String)                            # transaction date, ISO
    amount = Column(Float, nullable=False)           # original
    currency = Column(String)
    amount_base = Column(Float)
    base_currency = Column(String)
    fx_rate = Column(Float)
    fx_date = Column(String)
    # NULL on either side means "the World" — inflow if from is NULL, outflow if to is NULL
    from_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    to_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    category = Column(String, nullable=True)         # expenses
    counterparty = Column(String, nullable=True)     # merchant (expense) / source (income)
    note = Column(String, nullable=True)
    raw_ocr_text = Column(TEXT, default="")
    parsed_ok = Column(Boolean, nullable=True)
    allocation_strategy = Column(String, nullable=True)   # 'manual'|'waterfall'|'proportional'|'pyf'
    batch_id = Column(String, nullable=True)              # groups entries from one allocation event
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="ledger_entries")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=True)             # 'essential' | 'discretionary' | None
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="categories")


# ============== LEGACY TABLES (read until cutover, dropped after) ==============

class Expense(Base):
    __tablename__ = "expenses"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    merchant = Column(String, default="Unknown")
    date = Column(String)
    category = Column(String, default="Uncategorized")
    currency = Column(String, default="USD")
    amount_base = Column(Float)
    base_currency = Column(String)
    fx_rate = Column(Float)
    fx_date = Column(String)
    raw_ocr_text = Column(TEXT, default="")
    parsed_ok = Column(Boolean, default=False)
    funding_source = Column(String, default="unaccounted")
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="expenses")


class SavingsTransaction(Base):
    __tablename__ = "savings_transactions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    direction = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String)
    amount_base = Column(Float)
    base_currency = Column(String)
    fx_rate = Column(Float)
    fx_date = Column(String)
    note = Column(String, default="")
    date = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="savings")


class IncomeTransaction(Base):
    __tablename__ = "income_transactions"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String)
    amount_base = Column(Float)
    base_currency = Column(String)
    fx_rate = Column(Float)
    fx_date = Column(String)
    source = Column(String, default="")
    date = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="income")