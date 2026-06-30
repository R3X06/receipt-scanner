"""Shared test fixtures.

Each test gets an isolated in-memory SQLite database (StaticPool so the single
in-memory connection persists for the test's lifetime). We seed the ledger log
directly via factories — bypassing post_entry — so derivation tests need no FX
and no network. DATABASE_URL is pinned to an in-memory URL before `database` is
imported, so importing the app never touches the local receipt_scanner.db file.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite://")  # app engine = throwaway in-memory


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user(db):
    u = models.User(email="t@t.com", hashed_password="x",
                    primary_currency="SGD", savings_strategy="proportional")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# --------------------------------------------------------------------------
# factories — return callables so a test can build several of each
# --------------------------------------------------------------------------
@pytest.fixture
def make_account(db):
    def _make(owner, acc_type, name=None, **kw):
        a = models.Account(user_id=owner.id, type=acc_type,
                           name=name or acc_type.title(), **kw)
        db.add(a)
        db.commit()
        db.refresh(a)
        return a
    return _make


@pytest.fixture
def make_category(db):
    def _make(owner, name, kind=None):
        c = models.Category(user_id=owner.id, name=name, kind=kind)
        db.add(c)
        db.commit()
        db.refresh(c)
        return c
    return _make


@pytest.fixture
def make_entry(db):
    def _make(owner, *, amount, from_account_id=None, to_account_id=None,
              amount_base=None, date=None, occurred_at=None, category=None,
              counterparty=None, wallet_linked=True, inferred=False,
              currency="SGD"):
        kw = dict(
            user_id=owner.id, amount=amount,
            amount_base=amount if amount_base is None else amount_base,
            currency=currency, base_currency="SGD",
            from_account_id=from_account_id, to_account_id=to_account_id,
            date=date or "", fx_date=date,
            category=category, counterparty=counterparty,
            wallet_linked=wallet_linked, inferred=inferred,
        )
        if occurred_at is not None:
            kw["occurred_at"] = occurred_at
        e = models.LedgerEntry(**kw)
        db.add(e)
        db.commit()
        db.refresh(e)
        return e
    return _make


@pytest.fixture
def make_goal(db):
    def _make(owner, name="Goal", **kw):
        g = models.Goal(user_id=owner.id, name=name, **kw)
        db.add(g)
        db.commit()
        db.refresh(g)
        return g
    return _make


# --------------------------------------------------------------------------
# fake providers — deterministic, network-free. Installed via the registry.
# --------------------------------------------------------------------------
class FakeFX:
    """Identity conversion, plus one non-trivial pair so conversion is exercised."""
    RATES = {("USD", "SGD"): 1.35}

    def convert_to_base(self, *, amount, currency, base_currency, receipt_date_str):
        currency = (currency or base_currency or "SGD").upper()
        base_currency = (base_currency or "SGD").upper()
        rate = 1.0 if currency == base_currency else self.RATES.get((currency, base_currency), 1.0)
        return {
            "amount_base": round(amount * rate, 2),
            "base_currency": base_currency,
            "fx_rate": rate,
            "fx_date": receipt_date_str or "2026-06-01",
        }


class FakeOCR:
    def __init__(self, text="TOTAL 12.34"):
        self._text = text

    def extract_text(self, image_bytes: bytes) -> str:
        return self._text


@pytest.fixture
def fake_fx():
    import providers
    providers.set_fx(FakeFX())
    yield
    providers.reset_fx()


@pytest.fixture
def fake_ocr():
    import providers
    providers.set_ocr(FakeOCR())
    yield
    providers.reset_ocr()


@pytest.fixture
def client(db, fake_fx, fake_ocr):
    """FastAPI TestClient wired to the in-memory test session and fake providers.
    Overriding get_db routes every endpoint (and get_current_user) through the
    same session the test seeds, so setup and request handlers share state."""
    from fastapi.testclient import TestClient
    import main
    from database import get_db

    def _override_get_db():
        yield db

    main.app.dependency_overrides[get_db] = _override_get_db
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()