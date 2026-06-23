from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import engine, get_db, Base
import models
import auth
import ocr
import fx
import ai
import os
import ledger
import types
from datetime import datetime

Base.metadata.create_all(bind=engine)

import migrate
migrate.run()
#import backfill_ledger
#backfill_ledger.backfill()

app = FastAPI()

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AskRequest(BaseModel):
    question: str

class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    avatar: Optional[str] = None
    primary_currency: Optional[str] = None
    monthly_budget: Optional[float] = None
    occupation: Optional[str] = None
    monthly_income: Optional[float] = None
    goals: Optional[str] = None
    feature_essential_tagging: Optional[bool] = None
    feature_pace_tracking: Optional[bool] = None
    feature_pay_yourself_first: Optional[bool] = None
    feature_priority_waterfall: Optional[bool] = None
    feature_proportional_allocation: Optional[bool] = None
    pyf_percent: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/signup")
def signup(body: SignupRequest, db: Session = Depends(get_db)):
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
    db.commit()
    token = auth.create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not auth.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

def _user_payload(u: models.User):
    return {
        "id": u.id,
        "email": u.email,
        "display_name": u.display_name or "",
        "avatar": u.avatar or "",
        "primary_currency": u.primary_currency or "SGD",
        "monthly_budget": u.monthly_budget,
        "occupation": u.occupation,
        "monthly_income": u.monthly_income,
        "goals": u.goals or "",
        "feature_essential_tagging": bool(u.feature_essential_tagging) if u.feature_essential_tagging is not None else True,
        "feature_pace_tracking": bool(u.feature_pace_tracking) if u.feature_pace_tracking is not None else True,
        "feature_pay_yourself_first": bool(u.feature_pay_yourself_first) if u.feature_pay_yourself_first is not None else True,
        "feature_priority_waterfall": bool(u.feature_priority_waterfall) if u.feature_priority_waterfall is not None else True,
        "feature_proportional_allocation": bool(u.feature_proportional_allocation) if u.feature_proportional_allocation is not None else True,
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
    for field in ("display_name", "avatar", "primary_currency", "monthly_budget",
                  "occupation", "monthly_income", "goals",
                  "feature_essential_tagging", "feature_pace_tracking",
                  "feature_pay_yourself_first", "feature_priority_waterfall",
                  "feature_proportional_allocation", "pyf_percent"):
        if field in data:
            setattr(current_user, field, data[field])
    db.commit()
    db.refresh(current_user)
    return _user_payload(current_user)


@app.post("/ocr")
async def scan_receipt(
    file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_user)
):
    contents = await file.read()
    base_currency = current_user.primary_currency or "SGD"
    raw_text = ocr.extract_text_from_image(contents)
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
    except Exception as exc:
        print(f"AI ask failed: {exc}")
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
        "monthly_income": current_user.monthly_income,
        "monthly_budget": current_user.monthly_budget,
        "occupation": current_user.occupation,
    }
    try:
        insights = ai.generate_insights(expenses, base_currency, profile=profile)
    except Exception as exc:
        print(f"AI insights failed: {exc}")
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
        raise HTTPException(status_code=400, detail="No spending account — run the ledger backfill.")
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
        raise HTTPException(status_code=400, detail="No spending account — run the ledger backfill.")
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
        conv = fx.convert_to_base(amount=body.amount, currency=body.currency or base,
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
        conv = fx.convert_to_base(amount=amount, currency=currency, base_currency=base, receipt_date_str=date)
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
    sav = _get_or_create_savings(db, current_user)
    frm = None
    if body.source != "external":
        spend = ledger.spending_account(db, current_user.id)
        if not spend:
            raise HTTPException(status_code=400, detail="No spending account")
        frm = spend.id
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=frm, to_account_id=sav.id, date=body.date,
                          occurred_at=_parse_occurred(body.occurred_at), note=body.note)
    db.commit()
    db.refresh(e)
    return {"id": e.id, "source": body.source}


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
    sav = _get_or_create_savings(db, current_user)
    to_id = None
    if body.to != "world":
        spend = ledger.spending_account(db, current_user.id)
        to_id = spend.id if spend else None
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=sav.id, to_account_id=to_id, date=body.date,
                          occurred_at=_parse_occurred(body.occurred_at), note=body.note)
    db.commit()
    db.refresh(e)
    return {"id": e.id, "to": body.to}


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
    funding_type: Optional[str] = "algorithmic"   # 'forced' | 'algorithmic'
    forced_amount: Optional[float] = None


def _own_goal(db, user, goal_id):
    return db.query(models.Goal).filter(
        models.Goal.id == goal_id, models.Goal.user_id == user.id
    ).first()


@app.get("/goals")
def get_goals(db: Session = Depends(get_db),
              current_user: models.User = Depends(auth.get_current_user)):
    return ledger.goals_view(db, current_user)


@app.post("/goals")
def create_goal_config(body: GoalConfigRequest, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    g = models.Goal(
        user_id=current_user.id, name=body.name, target_amount=body.target_amount,
        deadline=body.deadline, priority=body.priority or 0,
        is_emergency=bool(body.is_emergency),
        funding_type=body.funding_type or "algorithmic", forced_amount=body.forced_amount,
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
    g.target_amount = body.target_amount
    g.deadline = body.deadline
    g.priority = body.priority or 0
    g.is_emergency = bool(body.is_emergency)
    g.funding_type = body.funding_type or "algorithmic"
    g.forced_amount = body.forced_amount
    db.commit()
    db.refresh(g)
    return {"id": g.id}


@app.delete("/goals/{goal_id}")
def delete_goal_config(goal_id: str, db: Session = Depends(get_db),
                       current_user: models.User = Depends(auth.get_current_user)):
    g = _own_goal(db, current_user, goal_id)
    if not g:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(g)
    db.commit()
    return {"ok": True}