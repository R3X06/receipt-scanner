from sqlalchemy import Column, String, Float, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.sqlite import TEXT
from sqlalchemy.orm import relationship
from database import Base
import uuid
from clock import utcnow


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
    goals = Column(TEXT, default="")
    # --- feature toggles (all default on; user can switch off) ---
    feature_pace_tracking = Column(Boolean, default=True)
    feature_pay_yourself_first = Column(Boolean, default=True)
    pyf_percent = Column(Float, nullable=True)   # pay-yourself-first: % of logged income to auto-allocate
    savings_strategy = Column(String, default="proportional")  # 'waterfall'|'proportional'|'even' — splits the remainder after reserves
    # --- email verification (hash stored, never the raw token; single-use, time-limited) ---
    email_verified = Column(Boolean, default=False)
    verification_token_hash = Column(String, nullable=True)
    verification_token_expires = Column(DateTime, nullable=True)
    # --- password reset (same hash-at-rest / single-use / time-limited pattern) ---
    reset_token_hash = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    # --- session invalidation: bumped on password reset so JWTs issued before
    # the reset stop verifying, even though they haven't expired yet ---
    token_version = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    # ledger
    accounts = relationship("Account", back_populates="owner")
    ledger_entries = relationship("LedgerEntry", back_populates="owner")
    categories = relationship("Category", back_populates="owner")
    goal_configs = relationship("Goal", back_populates="owner")
    import_batches = relationship("ImportBatch", back_populates="owner")
    import_candidates = relationship("ImportCandidate", back_populates="owner")


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
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="accounts")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(String)                            # transaction date, ISO (calendar day)
    occurred_at = Column(DateTime, default=utcnow)  # precise event time; orders the running wallet
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
    idempotency_key = Column(String, index=True, nullable=True)  # import dedup: cross-source CONTENT hash; NULL for pre-import rows
    source_key = Column(String, index=True, nullable=True)        # import dedup: exact source-native key ('csv:REF'); NULL when source had no native id
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="ledger_entries")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=True)             # 'essential' | 'discretionary' | None
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="categories")


class Goal(Base):
    """A goal is a *derived claim* over the savings balance, not an account.
    It holds no money; its current allocation is recomputed from the savings
    pool + these config fields. Every goal may carry an optional `reserve`: a
    floor that is funded off the top before the chosen strategy splits whatever
    remains (each goal then competing for the remainder over target - reserve)."""
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    target_amount = Column(Float, nullable=True)        # optional goal size
    deadline = Column(String, nullable=True)            # ISO date
    priority = Column(Integer, default=0)               # rank: lower = senior (reserve filled first / waterfall first)
    is_emergency = Column(Boolean, default=False)       # marks THE single emergency fund (target derived from essentials)
    in_distribution = Column(Boolean, default=True)      # competes for the remainder; if False, only its reserve is held senior
    coverage_months = Column(Integer, nullable=True)     # emergency only: months of essential spend the target aims to cover
    reserve = Column(Float, nullable=True)              # guaranteed floor, funded before the remainder split (0 <= reserve <= target)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="goal_configs")


# ============== INGESTION STAGING (redesign) ==============
# Pending candidates from bulk/scan imports live HERE, never in the ledger:
# they are *proposals*, not ledger truth, so the immutable LedgerEntry log stays
# pure (design lock §3.5, Property D). Confirmed candidates flow into LedgerEntry
# via the normal append path, tagged with batch_id + idempotency_key.

class ImportBatch(Base):
    """One import event (one uploaded CSV / one scanned screenshot). Holds NO
    durable raw artifact — raw bytes die with the request (Property J1)."""
    __tablename__ = "import_batches"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    source_type = Column(String, nullable=False)         # 'csv' | 'paynow' | ...
    status = Column(String, default="pending")           # 'pending' | 'posted' | 'discarded'
    attested = Column(Boolean, default=False)            # Property M: upload-authorisation consent record
    count_total = Column(Integer, default=0)
    count_posted = Column(Integer, default=0)
    count_duplicate = Column(Integer, default=0)
    count_rejected = Column(Integer, default=0)
    imported_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="import_batches")
    candidates = relationship("ImportCandidate", back_populates="batch")


class ImportCandidate(Base):
    """A single parsed, not-yet-confirmed transaction awaiting human review.
    Carries NO raw counterparty name and NO NRIC/phone-linked identifier
    (Property J2): only a user label, a salted one-way hash for matching, and a
    masked display string. Amounts are parsed deterministically, never produced
    by the LLM (Property A)."""
    __tablename__ = "import_candidates"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    batch_id = Column(String, ForeignKey("import_batches.id"), nullable=False)

    # --- dedup keys (design lock §2) ---
    source_ref = Column(String, nullable=True)           # source-native ID (PayNow txn id / statement ref) — exact, auto-skip
    idempotency_key = Column(String, index=True)         # content hash — cross-source, flags for review

    # --- parsed transaction ---
    date = Column(String, nullable=True)                 # ISO calendar day
    amount = Column(Float, nullable=False)
    currency = Column(String, nullable=True)
    direction = Column(String, nullable=False)           # 'in' | 'out'
    category = Column(String, nullable=True)

    # --- de-identified counterparty (Property J2) ---
    counterparty_label = Column(String, nullable=True)   # user-supplied label
    counterparty_hash = Column(String, nullable=True)    # salted one-way hash (matching only)
    counterparty_masked = Column(String, nullable=True)  # safe display, e.g. 'transfer ***8821'

    confidence = Column(Float, nullable=True)
    status = Column(String, default="pending")           # 'pending' | 'confirmed' | 'rejected' | 'duplicate'
    review_flag = Column(String, nullable=True)          # reviewer signal: 'exact_duplicate' | 'possible_duplicate' | 'fx_failed' | None (extensible)
    posted_entry_id = Column(String, ForeignKey("ledger_entries.id"), nullable=True)  # set on confirm -> provenance link to the posted LedgerEntry
    created_at = Column(DateTime, default=utcnow)

    owner = relationship("User", back_populates="import_candidates")
    batch = relationship("ImportBatch", back_populates="candidates")