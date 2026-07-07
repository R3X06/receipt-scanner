from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from database import engine, get_db, Base
import models
import auth
import ocr
import providers
import fx
import ai
import email_utils
import os
import ledger
import ingestion
import imports_service
import csv_adapter
import paynow_adapter
import pdf_adapter
import types
from datetime import datetime, timedelta
from clock import utcnow
from logging_config import setup_logging, logger

setup_logging()

Base.metadata.create_all(bind=engine)

import migrate  # noqa: E402  -- must follow create_all so tables exist
migrate.run()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development").strip().lower()


def _docs_urls_for(environment: str) -> dict:
    """Swagger UI (/docs), ReDoc (/redoc), and the raw schema (/openapi.json)
    are default recon targets for any scanner probing a discovered API — they
    hand over every endpoint, field, and validation rule for free. Off in
    production; on everywhere else, so local/dev work is unaffected."""
    if environment == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


app = FastAPI(**_docs_urls_for(ENVIRONMENT))

app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(fx.FXUnavailableError)
async def _fx_unavailable_handler(request, exc):
    # A cross-currency rate could not be obtained; refuse the write loudly
    # rather than persisting a silently-wrong base amount.
    return JSONResponse(
        status_code=503,
        content={"detail": "Exchange rate temporarily unavailable — please try again shortly."},
    )

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    email: EmailStr                      # RFC-valid format (not deliverability)
    password: str

    @field_validator("password")
    @classmethod
    def _password_bounds(cls, v: str) -> str:
        # Gate 1, Decision 1.2: min 8 / max 128, enforced at signup only.
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters.")
        return v


class LoginRequest(BaseModel):
    email: str                           # kept permissive: login only verifies
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _password_bounds(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters.")
        return v


class AskRequest(BaseModel):
    question: str

class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    primary_currency: Optional[str] = None
    monthly_budget: Optional[float] = None
    occupation: Optional[str] = None
    goals: Optional[str] = None
    feature_pace_tracking: Optional[bool] = None
    feature_pay_yourself_first: Optional[bool] = None
    savings_strategy: Optional[str] = None
    pyf_percent: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup")
@auth.limiter.limit("10/hour")
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = models.User(
        email=body.email,
        hashed_password=auth.hash_password(body.password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(models.Account(user_id=user.id, type="spending", name="Spending"))
    db.add(models.Account(user_id=user.id, type="savings", name="Savings"))
    for name, kind in {"Food & Drink": "essential", "Transport": "essential",
                       "Utilities": "essential", "Health": "essential",
                       "Shopping": "discretionary", "Entertainment": "discretionary",
                       "Other": None, "Uncategorized": None}.items():
        db.add(models.Category(user_id=user.id, name=name, kind=kind))
    # emergency fund participates in the remainder split by default (uniform across
    # signup and the lazy-ensure path; users can opt out via /goals/emergency)
    db.add(models.Goal(user_id=user.id, name="Emergency fund", is_emergency=True,
                       in_distribution=True, coverage_months=6, priority=0))
    # Email verification: generate + store only the hash, email the raw token.
    # Best-effort — a broken email provider must not block account creation.
    verify_token = auth.generate_token()
    user.verification_token_hash = auth.hash_token(verify_token)
    user.verification_token_expires = utcnow() + timedelta(hours=24)
    db.commit()
    email_utils.send_verification_email(user.email, verify_token)
    token = auth.create_token({"sub": user.id, "ver": user.token_version or 0})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/login")
@auth.limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not auth.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # Gate 1, Decision 1.1: transparently upgrade legacy bcrypt hashes to Argon2id
    # on successful login. Old users migrate silently; no forced password reset.
    if auth.needs_rehash(user.hashed_password):
        user.hashed_password = auth.hash_password(body.password)
        db.commit()
    token = auth.create_token({"sub": user.id, "ver": user.token_version or 0})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/verify-email")
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_hash = auth.hash_token(body.token)
    user = db.query(models.User).filter(models.User.verification_token_hash == token_hash).first()
    if not user or not user.verification_token_expires or user.verification_token_expires < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.email_verified = True
    user.verification_token_hash = None
    user.verification_token_expires = None
    db.commit()
    return {"detail": "Email verified"}


@app.post("/auth/resend-verification")
def resend_verification(db: Session = Depends(get_db),
                        current_user: models.User = Depends(auth.get_current_user)):
    if current_user.email_verified:
        return {"detail": "Email already verified"}
    verify_token = auth.generate_token()
    current_user.verification_token_hash = auth.hash_token(verify_token)
    current_user.verification_token_expires = utcnow() + timedelta(hours=24)
    db.commit()
    email_utils.send_verification_email(current_user.email, verify_token)
    return {"detail": "Verification email sent"}


@app.post("/auth/forgot-password")
@auth.limiter.limit("3/hour")
def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    # Always return the same response whether or not the email is registered —
    # a different response would let an attacker enumerate accounts.
    generic = {"detail": "If that email is registered, a reset link has been sent."}
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        return generic
    reset_token = auth.generate_token()
    user.reset_token_hash = auth.hash_token(reset_token)
    user.reset_token_expires = utcnow() + timedelta(minutes=30)
    db.commit()
    email_utils.send_password_reset_email(user.email, reset_token)
    return generic


@app.post("/auth/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = auth.hash_token(body.token)
    user = db.query(models.User).filter(models.User.reset_token_hash == token_hash).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user.hashed_password = auth.hash_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    # Invalidate every JWT issued before this reset (see auth.get_current_user).
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return {"detail": "Password reset. Please log in again."}

def _user_payload(u: models.User):
    return {
        "id": u.id,
        "email": u.email,
        "email_verified": bool(u.email_verified),
        "display_name": u.display_name or "",
        "avatar": u.avatar or "",
        "primary_currency": u.primary_currency or "SGD",
        "monthly_budget": u.monthly_budget,
        "occupation": u.occupation,
        "goals": u.goals or "",
        "feature_pace_tracking": bool(u.feature_pace_tracking) if u.feature_pace_tracking is not None else True,
        "feature_pay_yourself_first": bool(u.feature_pay_yourself_first) if u.feature_pay_yourself_first is not None else True,
        "savings_strategy": (u.savings_strategy or "proportional"),
        "pyf_percent": u.pyf_percent,
    }


@app.get("/auth/me")
def me(current_user: models.User = Depends(auth.get_current_user)):
    return _user_payload(current_user)


@app.put("/users/me")
def update_me(
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    if "savings_strategy" in data:
        s = (data.get("savings_strategy") or "proportional").lower()
        data["savings_strategy"] = s if s in ("waterfall", "proportional", "even") else "proportional"
    for field in ("display_name", "avatar", "primary_currency", "monthly_budget",
                  "occupation", "goals",
                  "feature_pace_tracking", "feature_pay_yourself_first",
                  "savings_strategy", "pyf_percent"):
        if field in data:
            setattr(current_user, field, data[field])
    db.commit()
    db.refresh(current_user)
    return _user_payload(current_user)


def _reject_non_image(file: UploadFile):
    """Advisory only — Content-Type is client-supplied and trivially spoofed,
    so this is not a security boundary (Vision will just fail gracefully on
    non-image bytes regardless, via parsed_ok). It's here to reject obviously
    wrong uploads before spending a paid Vision API call on them."""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")


@app.post("/ocr")
@auth.limiter.limit("30/hour")
async def scan_receipt(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user)
):
    _reject_non_image(file)
    contents = await file.read()
    if len(contents) > MAX_IMPORT_BYTES:      # parity with /scan below
        raise HTTPException(status_code=413, detail="File too large.")
    base_currency = current_user.primary_currency or "SGD"
    raw_text = providers.get_ocr().extract_text(contents)
    parsed = ocr.parse_receipt(raw_text, base_currency=base_currency)

    return {
        "merchant": parsed["merchant"],
        "amount": parsed["amount"],
        "date": parsed["date"],
        "category": "Uncategorized",
        "currency": parsed["currency"],
        "raw_ocr_text": raw_text,
        "parsed_ok": parsed["parsed_ok"],
    }

@app.post("/scan")
@auth.limiter.limit("30/hour")
async def scan_image(
    request: Request,
    file: UploadFile = File(...),
    attested: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """One OCR pass, then route: a PayNow screenshot -> the import pipeline
    (staging + review); anything else -> a receipt draft (the instant-expense
    flow). Classifying the text we already OCR'd avoids a second OCR call."""
    _reject_non_image(file)
    contents = await file.read()
    if len(contents) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="File too large.")
    raw_text = providers.get_ocr().extract_text(contents)

    if paynow_adapter.looks_like_paynow(raw_text):
        if not attested:                       # Property M: importing third-party data
            raise HTTPException(status_code=400,
                                detail="You must attest that you are authorised to import this transfer.")
        txn = paynow_adapter.extract_paynow(raw_text)
        if not txn:
            raise HTTPException(status_code=422,
                                detail="This looks like a PayNow transfer but no amount could be read.")
        window_start = utcnow() - timedelta(hours=1)   # Property L: rate cap
        recent = db.query(models.ImportBatch).filter(
            models.ImportBatch.user_id == current_user.id,
            models.ImportBatch.imported_at >= window_start).count()
        if recent >= MAX_IMPORTS_PER_HOUR:
            raise HTTPException(status_code=429, detail="Too many imports — please wait a bit and retry.")
        batch = ingestion.ingest(
            db, current_user,
            _PreparsedAdapter(paynow_adapter.PayNowAdapter(), [txn]),
            contents, attested=attested)
        return {"kind": "paynow", "batch": _batch_view(db, batch)}

    # receipt draft — reuse the /ocr logic on the text we already have
    base_currency = current_user.primary_currency or "SGD"
    parsed = ocr.parse_receipt(raw_text, base_currency=base_currency)
    return {
        "kind": "receipt",
        "merchant": parsed["merchant"], "amount": parsed["amount"],
        "date": parsed["date"], "category": "Uncategorized",
        "currency": parsed["currency"], "raw_ocr_text": raw_text,
        "parsed_ok": parsed["parsed_ok"],
    }

@app.post("/ai/ask")
def ai_ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="Please enter a question.")

    expenses = _ledger_expenses_for_ai(db, current_user)

    base_currency = current_user.primary_currency or "SGD"
    try:
        answer = ai.answer_question(body.question.strip(), expenses, base_currency)
    except Exception:
        logger.warning("ai_ask_failed", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="The AI service is unavailable. Check your OpenAI key and credit, then try again."
        )
    return {"answer": answer}

@app.post("/ai/insights")
def ai_insights(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expenses = _ledger_expenses_for_ai(db, current_user)

    base_currency = current_user.primary_currency or "SGD"
    profile = {
        "goals": current_user.goals,
        "monthly_income": ledger.monthly_income_avg(db, current_user),
        "monthly_budget": current_user.monthly_budget,
        "occupation": current_user.occupation,
    }
    try:
        insights = ai.generate_insights(expenses, base_currency, profile=profile)
    except Exception:
        logger.warning("ai_insights_failed", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="The AI service is unavailable. Check your OpenAI key and credit, then try again."
        )
    return {"insights": insights}

class CategorizeRequest(BaseModel):
    merchant: Optional[str] = ""
    raw_text: Optional[str] = ""


@app.post("/ai/categorize")
def ai_categorize(
    body: CategorizeRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    return {"category": ai.suggest_category(body.merchant, body.raw_text)}

class ExtractRequest(BaseModel):
    raw_text: Optional[str] = ""


@app.post("/ai/extract")
def ai_extract(
    body: ExtractRequest,
    current_user: models.User = Depends(auth.get_current_user)
):
    return ai.extract_fields(body.raw_text)

@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return {
        "accounts": ledger.list_accounts(db, current_user),
        "net_worth": ledger.net_worth(db, current_user),
        "currency": current_user.primary_currency or "SGD",
    }


@app.get("/ledger/cashflow")
def ledger_cashflow(month: Optional[str] = None, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    return ledger.cashflow(db, current_user, month)

class LedgerExpenseRequest(BaseModel):
    amount: float
    merchant: Optional[str] = ""
    date: Optional[str] = None
    category: Optional[str] = "Uncategorized"
    currency: Optional[str] = None
    from_account_id: Optional[str] = None    # None = Spending; or a goal id (paid from savings)
    note: Optional[str] = None
    raw_ocr_text: Optional[str] = ""
    parsed_ok: Optional[bool] = True
    occurred_at: Optional[str] = None        # precise event time (ISO); orders the wallet
    wallet_linked: Optional[bool] = True     # false = expense-only (paid from untracked money)


class LedgerIncomeRequest(BaseModel):
    amount: float
    source: Optional[str] = ""
    date: Optional[str] = None
    currency: Optional[str] = None
    occurred_at: Optional[str] = None


def _own_account(db, user, account_id):
    return db.query(models.Account).filter(
        models.Account.id == account_id, models.Account.user_id == user.id
    ).first()


@app.post("/ledger/expense")
def ledger_expense(body: LedgerExpenseRequest, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_user)):
    spend = ledger.spending_account(db, current_user.id)
    if not spend:
        raise HTTPException(status_code=400, detail="No wallet account found.")
    frm = body.from_account_id or spend.id
    if not _own_account(db, current_user, frm):
        raise HTTPException(status_code=400, detail="Invalid source account")
    e = ledger.post_entry(
        db, current_user, amount=body.amount, currency=body.currency,
        from_account_id=frm, to_account_id=None, date=body.date,
        occurred_at=_parse_occurred(body.occurred_at),
        category=body.category, counterparty=body.merchant, note=body.note,
        raw_ocr_text=body.raw_ocr_text, parsed_ok=body.parsed_ok,
        wallet_linked=body.wallet_linked if body.wallet_linked is not None else True,
    )
    db.commit()
    db.refresh(e)
    return e


@app.post("/ledger/income")
def ledger_income(body: LedgerIncomeRequest, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_user)):
    spend = ledger.spending_account(db, current_user.id)
    if not spend:
        raise HTTPException(status_code=400, detail="No wallet account found.")
    e = ledger.post_entry(
        db, current_user, amount=body.amount, currency=body.currency,
        from_account_id=None, to_account_id=spend.id, date=body.date,
        occurred_at=_parse_occurred(body.occurred_at),
        counterparty=body.source,
    )
    db.commit()
    db.refresh(e)
    # pay-yourself-first: suggest (not force) how much to move to savings now
    pyf = None
    if current_user.feature_pay_yourself_first and current_user.pyf_percent:
        base = current_user.primary_currency or "SGD"
        conv = providers.get_fx().convert_to_base(amount=body.amount, currency=body.currency or base,
                                  base_currency=base, receipt_date_str=body.date)
        pyf = round(conv["amount_base"] * (current_user.pyf_percent / 100.0), 2)
    return {"id": e.id, "pay_yourself_first_suggested": pyf}


@app.get("/ledger/entries")
def ledger_entries(limit: int = 1000, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_user)):
    accs = {a.id: a for a in db.query(models.Account).filter(
        models.Account.user_id == current_user.id).all()}
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == current_user.id
    ).order_by(models.LedgerEntry.created_at.desc()).limit(limit).all()
    out = []
    for e in rows:
        frm, to = accs.get(e.from_account_id), accs.get(e.to_account_id)
        kind = "income" if e.from_account_id is None else ("expense" if e.to_account_id is None else "transfer")
        out.append({
            "id": e.id, "kind": kind, "date": e.date, "fx_date": e.fx_date,
            "amount": e.amount, "currency": e.currency, "amount_base": e.amount_base,
            "category": e.category, "counterparty": e.counterparty, "note": e.note,
            "from_account_id": e.from_account_id, "to_account_id": e.to_account_id,
            "from": frm.name if frm else None, "to": to.name if to else None,
            "from_type": frm.type if frm else None, "to_type": to.type if to else None,
        })
    return {"entries": out}


@app.delete("/ledger/entries/{entry_id}")
def delete_entry(entry_id: str, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.get_current_user)):
    e = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.id == entry_id, models.LedgerEntry.user_id == current_user.id
    ).first()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    db.delete(e)
    db.commit()
    return {"ok": True, "id": entry_id}

class LedgerEntryUpdate(BaseModel):
    amount: Optional[float] = None
    merchant: Optional[str] = None
    date: Optional[str] = None
    category: Optional[str] = None
    currency: Optional[str] = None
    from_account_id: Optional[str] = None
    note: Optional[str] = None


@app.put("/ledger/entries/{entry_id}")
def update_entry(entry_id: str, body: LedgerEntryUpdate, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.get_current_user)):
    e = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.id == entry_id, models.LedgerEntry.user_id == current_user.id
    ).first()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    base = current_user.primary_currency or "SGD"
    if body.amount is not None or body.currency is not None or body.date is not None:
        amount = body.amount if body.amount is not None else e.amount
        currency = body.currency or e.currency or base
        date = body.date if body.date is not None else e.date
        conv = providers.get_fx().convert_to_base(amount=amount, currency=currency, base_currency=base, receipt_date_str=date)
        e.amount, e.currency, e.date = amount, currency, date
        e.amount_base = conv["amount_base"]
        e.base_currency = conv["base_currency"]
        e.fx_rate = conv["fx_rate"]
        e.fx_date = conv["fx_date"]
    if body.merchant is not None:
        e.counterparty = body.merchant
    if body.category is not None:
        e.category = body.category
    if body.from_account_id is not None:
        # Gate 2: a client-supplied account id must belong to the caller before
        # it can be referenced. Mirrors the /ledger/expense ownership check.
        if not _own_account(db, current_user, body.from_account_id):
            raise HTTPException(status_code=400, detail="Invalid source account")
        e.from_account_id = body.from_account_id
    if body.note is not None:
        e.note = body.note
    db.commit()
    db.refresh(e)
    return e

def _ledger_expenses_for_ai(db, user):
    rows = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.user_id == user.id,
        models.LedgerEntry.to_account_id.is_(None),   # outflow = an expense
    ).order_by(models.LedgerEntry.created_at.desc()).all()
    return [
        types.SimpleNamespace(
            amount=e.amount, amount_base=e.amount_base, currency=e.currency,
            category=e.category, merchant=e.counterparty or "Unknown",
            fx_date=e.fx_date, date=e.date,
        )
        for e in rows
    ]

@app.get("/categories")
def get_categories(db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_user)):
    cats = db.query(models.Category).filter(
        models.Category.user_id == current_user.id).order_by(models.Category.name).all()
    return {"categories": [{"id": c.id, "name": c.name, "kind": c.kind} for c in cats]}


class CategoryUpdateRequest(BaseModel):
    updates: list   # [{"name": "Food & Drink", "kind": "essential" | "discretionary" | null}]


@app.put("/categories")
def update_categories(body: CategoryUpdateRequest, db: Session = Depends(get_db),
                      current_user: models.User = Depends(auth.get_current_user)):
    by_name = {c.name: c for c in db.query(models.Category).filter(
        models.Category.user_id == current_user.id).all()}
    for u in body.updates:
        c = by_name.get(u.get("name"))
        if c:
            c.kind = u.get("kind")
    db.commit()
    return {"ok": True}

# ============== Phase 2: savings-as-wallet, goals-as-config, reconciliation ==============

def _parse_occurred(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "").strip())
    except (ValueError, TypeError):
        pass
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _get_or_create_savings(db, user):
    sav = ledger.savings_account(db, user.id)
    if not sav:
        sav = models.Account(user_id=user.id, type="savings", name="Savings")
        db.add(sav)
        db.commit()
        db.refresh(sav)
    return sav


class SavingsDepositRequest(BaseModel):
    amount: float
    currency: Optional[str] = None
    source: Optional[str] = "surplus"        # 'surplus' (from Spending) | 'external' (from World)
    date: Optional[str] = None
    occurred_at: Optional[str] = None
    note: Optional[str] = None


@app.post("/ledger/savings/deposit")
def savings_deposit(body: SavingsDepositRequest, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    if not body.amount or body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")
    sav = _get_or_create_savings(db, current_user)
    base = current_user.primary_currency or "SGD"
    conv = providers.get_fx().convert_to_base(amount=body.amount, currency=body.currency or base,
                              base_currency=base, receipt_date_str=body.date)
    amt_base = conv["amount_base"]
    frm = None
    if body.source != "external":                        # 'surplus' = moved out of the wallet
        spend = ledger.spending_account(db, current_user.id)
        if not spend:
            raise HTTPException(status_code=400, detail="No wallet account")
        wallet_bal = round(ledger.account_balances(db, current_user.id).get(spend.id, 0.0), 2)
        if amt_base > wallet_bal + 1e-6:
            raise HTTPException(status_code=400,
                                detail=f"Not enough in wallet — available {base} {wallet_bal:,.2f}.")
        frm = spend.id
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=frm, to_account_id=sav.id, date=body.date,
                          occurred_at=_parse_occurred(body.occurred_at), note=body.note)
    db.commit()
    db.refresh(e)
    bal = ledger.account_balances(db, current_user.id)
    spend = ledger.spending_account(db, current_user.id)
    return {"id": e.id, "source": body.source,
            "wallet_balance": round(bal.get(spend.id, 0.0), 2) if spend else None,
            "savings_balance": round(bal.get(sav.id, 0.0), 2)}


class SavingsWithdrawRequest(BaseModel):
    amount: float
    currency: Optional[str] = None
    to: Optional[str] = "spending"           # 'spending' | 'world'
    date: Optional[str] = None
    occurred_at: Optional[str] = None
    note: Optional[str] = None


@app.post("/ledger/savings/withdraw")
def savings_withdraw(body: SavingsWithdrawRequest, db: Session = Depends(get_db),
                     current_user: models.User = Depends(auth.get_current_user)):
    if not body.amount or body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive.")
    sav = _get_or_create_savings(db, current_user)
    base = current_user.primary_currency or "SGD"
    conv = providers.get_fx().convert_to_base(amount=body.amount, currency=body.currency or base,
                              base_currency=base, receipt_date_str=body.date)
    amt_base = conv["amount_base"]
    sav_bal = round(ledger.account_balances(db, current_user.id).get(sav.id, 0.0), 2)
    if amt_base > sav_bal + 1e-6:
        raise HTTPException(status_code=400,
                            detail=f"Not enough in savings — available {base} {sav_bal:,.2f}.")
    to_id = None
    if body.to != "world":
        spend = ledger.spending_account(db, current_user.id)
        to_id = spend.id if spend else None
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=sav.id, to_account_id=to_id, date=body.date,
                          occurred_at=_parse_occurred(body.occurred_at), note=body.note)
    db.commit()
    db.refresh(e)
    bal = ledger.account_balances(db, current_user.id)
    spend = ledger.spending_account(db, current_user.id)
    return {"id": e.id, "to": body.to,
            "wallet_balance": round(bal.get(spend.id, 0.0), 2) if spend else None,
            "savings_balance": round(bal.get(sav.id, 0.0), 2)}


class OpeningBalanceRequest(BaseModel):
    amount: float
    currency: Optional[str] = None
    date: Optional[str] = None
    occurred_at: Optional[str] = None


@app.post("/ledger/opening-balance")
def opening_balance(body: OpeningBalanceRequest, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    spend = ledger.spending_account(db, current_user.id)
    if not spend:
        raise HTTPException(status_code=400, detail="No spending account")
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=None, to_account_id=spend.id, date=body.date,
                          occurred_at=_parse_occurred(body.occurred_at),
                          counterparty="Opening balance", inferred=True)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


@app.get("/ledger/reconciliation")
def ledger_reconciliation(db: Session = Depends(get_db),
                          current_user: models.User = Depends(auth.get_current_user)):
    return ledger.wallet_reconciliation(db, current_user)


class WalletLinkRequest(BaseModel):
    wallet_linked: bool


@app.post("/ledger/entries/{entry_id}/wallet-link")
def set_wallet_link(entry_id: str, body: WalletLinkRequest, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    e = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.id == entry_id,
        models.LedgerEntry.user_id == current_user.id,
    ).first()
    if not e:
        raise HTTPException(status_code=404, detail="Entry not found")
    if e.to_account_id is not None:
        raise HTTPException(status_code=400, detail="Only expenses can be unlinked")
    e.wallet_linked = bool(body.wallet_linked)
    db.commit()
    db.refresh(e)
    return {"id": e.id, "wallet_linked": e.wallet_linked}


class GoalConfigRequest(BaseModel):
    name: str
    target_amount: Optional[float] = None
    deadline: Optional[str] = None
    priority: Optional[int] = 0
    is_emergency: Optional[bool] = False
    in_distribution: Optional[bool] = True
    reserve: Optional[float] = None               # guaranteed floor, funded before the remainder split


def _clamp_reserve(reserve, target):
    r = max(reserve or 0.0, 0.0)
    if target is not None:
        r = min(r, max(target, 0.0))
    return round(r, 2) if r else None


def _own_goal(db, user, goal_id):
    return db.query(models.Goal).filter(
        models.Goal.id == goal_id, models.Goal.user_id == user.id
    ).first()


@app.get("/goals")
def get_goals(db: Session = Depends(get_db),
              current_user: models.User = Depends(auth.get_current_user)):
    return ledger.goals_view(db, current_user)


class GoalReorderRequest(BaseModel):
    order: list   # goal ids, top-first; index becomes the priority rank (1 = most senior)


@app.post("/goals/reorder")
def reorder_goals(body: GoalReorderRequest, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_user)):
    owned = {g.id: g for g in db.query(models.Goal).filter(
        models.Goal.user_id == current_user.id).all()}
    rank = 1
    for gid in body.order:
        g = owned.get(gid)
        if g:
            g.priority = rank
            rank += 1
    db.commit()
    return ledger.goals_view(db, current_user)


@app.post("/goals")
def create_goal_config(body: GoalConfigRequest, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    g = models.Goal(
        user_id=current_user.id, name=body.name, target_amount=body.target_amount,
        deadline=body.deadline, priority=body.priority or 0,
        is_emergency=False,  # the emergency fund is managed via /goals/emergency, never the normal form
        in_distribution=body.in_distribution is not False,
        reserve=_clamp_reserve(body.reserve, body.target_amount),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return {"id": g.id}


@app.put("/goals/{goal_id}")
def update_goal_config(goal_id: str, body: GoalConfigRequest, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    g = _own_goal(db, current_user, goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found")
    g.name = body.name
    g.deadline = body.deadline
    g.priority = body.priority or 0
    # don't let the normal form flip emergency status; emergency target stays derived
    if not g.is_emergency:
        g.target_amount = body.target_amount
        g.in_distribution = body.in_distribution is not False
    g.reserve = _clamp_reserve(body.reserve, g.target_amount if g.is_emergency else body.target_amount)
    db.commit()
    db.refresh(g)
    return {"id": g.id}


class EmergencyConfigRequest(BaseModel):
    in_distribution: Optional[bool] = None       # toggle: participate in the remainder split
    coverage_months: Optional[int] = None        # 3 / 6 / 12 -> target = months x essential monthly spend
    reserve: Optional[float] = None              # optional senior floor (your choice, like any goal)


@app.post("/goals/emergency")
def configure_emergency(body: EmergencyConfigRequest, db: Session = Depends(get_db),
                        current_user: models.User = Depends(auth.get_current_user)):
    g = ledger._ensure_emergency(db, current_user)
    if body.in_distribution is not None:
        g.in_distribution = bool(body.in_distribution)
    if body.coverage_months is not None:
        g.coverage_months = max(1, int(body.coverage_months))
    if body.reserve is not None:
        g.reserve = max(body.reserve, 0.0) if body.reserve else None
    db.commit()
    return ledger.goals_view(db, current_user)


@app.delete("/goals/{goal_id}")
def delete_goal_config(goal_id: str, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    g = _own_goal(db, current_user, goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(g)
    db.commit()
    return {"ok": True}

# ============================================================================
# Imports: bulk/scan ingestion — upload -> review -> post (design lock §1-§3)
# Every handler is get_owned-scoped (Property K). Candidates never expose the
# raw hash or any raw text (J1/J2).
# ============================================================================

MAX_IMPORT_BYTES = 5 * 1024 * 1024        # Property L: reject oversized uploads
MAX_IMPORT_ROWS = 5000                    # Property L: reject huge batches (denial-of-wallet)
MAX_IMPORTS_PER_HOUR = 10                 # Property L: per-user rate cap


class CandidateEdit(BaseModel):
    category: Optional[str] = None
    counterparty_label: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[str] = None
    direction: Optional[str] = None
    currency: Optional[str] = None


def _candidate_view(c: models.ImportCandidate):
    # Deliberately omits counterparty_hash and any raw text (J1/J2).
    return {
        "id": c.id, "batch_id": c.batch_id,
        "date": c.date, "amount": c.amount, "currency": c.currency,
        "direction": c.direction, "category": c.category,
        "counterparty_label": c.counterparty_label,
        "counterparty_masked": c.counterparty_masked,
        "status": c.status, "review_flag": c.review_flag,
        "source_ref": c.source_ref, "posted_entry_id": c.posted_entry_id,
    }


def _batch_view(db, batch: models.ImportBatch, *, include_candidates=True):
    out = {
        "id": batch.id, "source_type": batch.source_type, "status": batch.status,
        "attested": batch.attested, "imported_at": str(batch.imported_at),
        "count_total": batch.count_total, "count_posted": batch.count_posted,
        "count_duplicate": batch.count_duplicate, "count_rejected": batch.count_rejected,
    }
    if include_candidates:
        cands = db.query(models.ImportCandidate).filter_by(
            batch_id=batch.id).order_by(models.ImportCandidate.date).all()
        out["candidates"] = [_candidate_view(c) for c in cands]
    return out


@app.post("/imports")
async def create_import(
    file: UploadFile = File(...),
    source_type: str = Form("csv"),
    attested: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if not attested:                       # Property M: authorisation attestation required
        raise HTTPException(status_code=400,
                            detail="You must attest that you are authorised to import this data.")
    if source_type not in ("csv", "paynow", "pdf"):
        raise HTTPException(status_code=400, detail=f"Unsupported source_type '{source_type}'.")

    # Property L: rate cap over the trailing hour
    window_start = utcnow() - timedelta(hours=1)
    recent = db.query(models.ImportBatch).filter(
        models.ImportBatch.user_id == current_user.id,
        models.ImportBatch.imported_at >= window_start,
    ).count()
    if recent >= MAX_IMPORTS_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many imports — please wait a bit and retry.")

    raw = await file.read()
    if len(raw) > MAX_IMPORT_BYTES:        # Property L: size cap
        raise HTTPException(status_code=413, detail="File too large.")

    if source_type == "csv":
        adapter = csv_adapter.CsvAdapter()
        parsed = adapter.parse(raw)
        if len(parsed) > MAX_IMPORT_ROWS:  # Property L: row cap (denial-of-wallet)
            raise HTTPException(status_code=413,
                                detail=f"Too many rows ({len(parsed)}); limit is {MAX_IMPORT_ROWS}.")
        empty_detail = "No transactions could be parsed from this file."
    elif source_type == "pdf":
        adapter = pdf_adapter.PdfAdapter()
        parsed = adapter.parse(raw)
        if len(parsed) > MAX_IMPORT_ROWS:  # Property L: row cap
            raise HTTPException(status_code=413,
                                detail=f"Too many rows ({len(parsed)}); limit is {MAX_IMPORT_ROWS}.")
        empty_detail = ("No transactions could be read from this PDF. "
                        "If it's a scanned image or an unusual layout, try the CSV export instead.")
    else:                                  # paynow: OCR a transfer screenshot
        adapter = paynow_adapter.PayNowAdapter()
        parsed = adapter.parse(raw)        # OCR happens once here
        empty_detail = "Could not read a PayNow transfer from this screenshot."

    if not parsed:
        raise HTTPException(status_code=422, detail=empty_detail)

    # raw bytes are not persisted; they die with this request (Property J1)
    batch = ingestion.ingest(db, current_user, _PreparsedAdapter(adapter, parsed), raw,
                             attested=attested)
    logger.info("import_created", extra={"batch_id": batch.id, "source": source_type,
                                         "rows": batch.count_total,
                                         "duplicates": batch.count_duplicate})
    return _batch_view(db, batch)


class _PreparsedAdapter:
    """Reuse the already-parsed rows (so we don't parse twice) while presenting
    the real adapter's source_type / label policy to the pipeline."""
    def __init__(self, inner, parsed):
        self.source_type = inner.source_type
        self.reveal_counterparty_label = inner.reveal_counterparty_label
        self._parsed = parsed

    def parse(self, raw):
        return self._parsed


@app.get("/imports/{batch_id}")
def get_import(batch_id: str, db: Session = Depends(get_db),
               current_user: models.User = Depends(auth.get_current_user)):
    batch = auth.get_owned(db, models.ImportBatch, batch_id, current_user)
    return _batch_view(db, batch)


@app.patch("/imports/candidates/{candidate_id}")
def edit_candidate(candidate_id: str, body: CandidateEdit,
                   db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_user)):
    c = auth.get_owned(db, models.ImportCandidate, candidate_id, current_user)
    c = imports_service.apply_edit(
        db, current_user, c,
        category=body.category, counterparty_label=body.counterparty_label,
        amount=body.amount, date=body.date, direction=body.direction,
        currency=body.currency)
    return _candidate_view(c)


@app.post("/imports/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, db: Session = Depends(get_db),
                     current_user: models.User = Depends(auth.get_current_user)):
    c = auth.get_owned(db, models.ImportCandidate, candidate_id, current_user)
    if c.status in ("confirmed",):
        raise HTTPException(status_code=409, detail="Cannot reject an already-posted candidate.")
    c.status, c.review_flag = "rejected", None
    db.commit()
    return _candidate_view(c)


@app.post("/imports/{batch_id}/confirm")
def confirm_import(batch_id: str, db: Session = Depends(get_db),
                   current_user: models.User = Depends(auth.get_current_user)):
    batch = auth.get_owned(db, models.ImportBatch, batch_id, current_user)
    result = imports_service.post_batch(db, current_user, batch)
    logger.info("import_confirmed", extra={"batch_id": batch.id, **result})
    return {**result, "batch": _batch_view(db, batch, include_candidates=False)}


@app.delete("/imports/{batch_id}")
def delete_import(batch_id: str, db: Session = Depends(get_db),
                  current_user: models.User = Depends(auth.get_current_user)):
    batch = auth.get_owned(db, models.ImportBatch, batch_id, current_user)
    result = imports_service.delete_import(db, current_user, batch)
    logger.info("import_deleted", extra=result)
    return {"ok": True, **result}