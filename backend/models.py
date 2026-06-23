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
    # ledger
    accounts = relationship("Account", back_populates="owner")
    ledger_entries = relationship("LedgerEntry", back_populates="owner")
    categories = relationship("Category", back_populates="owner")
    goal_configs = relationship("Goal", back_populates="owner")


# ============== THE LEDGER (new foundation) ==============

class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    type = Column(String, nullable=False)            # 'spending' | 'savings' | 'goal'(legacy)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=True)     # legacy goal-account fields (unused for spending/savings)
    deadline = Column(String, nullable=True)
    priority = Column(Integer, default=0)
    is_emergency = Column(Boolean, default=False)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="accounts")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(String)                            # transaction date, ISO (calendar day)
    occurred_at = Column(DateTime, default=datetime.utcnow)  # precise event time; orders the running wallet
    amount = Column(Float, nullable=False)           # original
    currency = Column(String)
    amount_base = Column(Float)
    base_currency = Column(String)
    fx_rate = Column(Float)
    fx_date = Column(String)
    # NULL on either side means "the World" — inflow if from is NULL, outflow if to is NULL
    from_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    to_account_id = Column(String, ForeignKey("accounts.id"), nullable=True)
    wallet_linked = Column(Boolean, default=True)    # expense draws the wallet & surplus when true; unlinked -> expense-only
    inferred = Column(Boolean, default=False)        # non-real income (e.g. opening balance); excluded from income x expense
    category = Column(String, nullable=True)         # expenses
    counterparty = Column(String, nullable=True)     # merchant (expense) / origin (income)
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


class Goal(Base):
    """A goal is a *derived claim* over the savings balance, not an account.
    It holds no money; its current allocation is recomputed from the savings
    pool + these config fields. Forced goals reserve a fixed amount (senior);
    algorithmic goals share the remainder via the chosen strategy (junior)."""
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=True)        # optional goal size
    deadline = Column(String, nullable=True)            # ISO date
    priority = Column(Integer, default=0)               # lower = senior (filled first, cut last)
    is_emergency = Column(Boolean, default=False)       # marks the emergency reserve
    funding_type = Column(String, default="algorithmic")  # 'forced' | 'algorithmic'
    forced_amount = Column(Float, nullable=True)        # reserved amount when funding_type == 'forced'
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="goal_configs")