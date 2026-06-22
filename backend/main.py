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

Base.metadata.create_all(bind=engine)

import migrate
migrate.run()
import backfill_ledger
backfill_ledger.backfill()

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


class ExpenseRequest(BaseModel):
    amount: float
    merchant: str
    date: str
    category: Optional[str] = "Uncategorized"
    currency: Optional[str] = "SGD"
    raw_ocr_text: Optional[str] = ""
    parsed_ok: Optional[bool] = True
    funding_source: Optional[str] = "unaccounted"

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


@app.post("/expenses")
def create_expense(
    body: ExpenseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    base_currency = current_user.primary_currency or fx.DEFAULT_BASE_CURRENCY
    conversion = fx.convert_to_base(
        amount=body.amount,
        currency=body.currency,
        base_currency=base_currency,
        receipt_date_str=body.date,
    )

    expense = models.Expense(
        user_id=current_user.id,
        amount=body.amount,
        merchant=body.merchant,
        date=body.date,
        category=body.category,
        currency=body.currency,
        amount_base=conversion["amount_base"],
        base_currency=conversion["base_currency"],
        fx_rate=conversion["fx_rate"],
        fx_date=conversion["fx_date"],
        raw_ocr_text=body.raw_ocr_text,
        parsed_ok=body.parsed_ok,
        funding_source=body.funding_source or "unaccounted",
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense

@app.put("/expenses/{expense_id}")
def update_expense(
    expense_id: str,
    body: ExpenseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.user_id == current_user.id,
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")

    base_currency = current_user.primary_currency or fx.DEFAULT_BASE_CURRENCY
    conversion = fx.convert_to_base(
        amount=body.amount,
        currency=body.currency,
        base_currency=base_currency,
        receipt_date_str=body.date,
    )

    expense.amount = body.amount
    expense.merchant = body.merchant
    expense.date = body.date
    expense.category = body.category
    expense.currency = body.currency
    expense.amount_base = conversion["amount_base"]
    expense.base_currency = conversion["base_currency"]
    expense.fx_rate = conversion["fx_rate"]
    expense.fx_date = conversion["fx_date"]
    expense.funding_source = body.funding_source or "unaccounted"
    # raw_ocr_text / parsed_ok deliberately preserved — keep the scan provenance

    db.commit()
    db.refresh(expense)
    return expense


@app.delete("/expenses/{expense_id}")
def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expense = db.query(models.Expense).filter(
        models.Expense.id == expense_id,
        models.Expense.user_id == current_user.id,
    ).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    db.delete(expense)
    db.commit()
    return {"ok": True, "id": expense_id}


@app.get("/expenses")
def get_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    query = db.query(models.Expense).filter(
        models.Expense.user_id == current_user.id
    )
    if category:
        query = query.filter(models.Expense.category == category)
    if start_date:
        query = query.filter(models.Expense.fx_date >= start_date)
    if end_date:
        query = query.filter(models.Expense.fx_date <= end_date)

    expenses = query.order_by(models.Expense.created_at.desc()).all()
    return expenses


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

class SavingsRequest(BaseModel):
    direction: str                 # 'in' | 'out'
    amount: float
    currency: Optional[str] = None
    note: Optional[str] = ""
    date: Optional[str] = None


@app.post("/savings")
def create_saving(
    body: SavingsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if body.direction not in ("in", "out"):
        raise HTTPException(status_code=400, detail="direction must be 'in' or 'out'")
    if body.amount is None or body.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    base_currency = current_user.primary_currency or fx.DEFAULT_BASE_CURRENCY
    currency = body.currency or base_currency
    conversion = fx.convert_to_base(
        amount=body.amount,
        currency=currency,
        base_currency=base_currency,
        receipt_date_str=body.date,
    )

    txn = models.SavingsTransaction(
        user_id=current_user.id,
        direction=body.direction,
        amount=body.amount,
        currency=currency,
        amount_base=conversion["amount_base"],
        base_currency=conversion["base_currency"],
        fx_rate=conversion["fx_rate"],
        fx_date=conversion["fx_date"],
        note=body.note or "",
        date=body.date or "",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn


@app.get("/savings")
def list_savings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    txns = db.query(models.SavingsTransaction).filter(
        models.SavingsTransaction.user_id == current_user.id
    ).order_by(models.SavingsTransaction.created_at.desc()).all()

    def base_amt(t):
        return t.amount_base if t.amount_base is not None else t.amount

    total_in = sum(base_amt(t) for t in txns if t.direction == "in")
    total_out = sum(base_amt(t) for t in txns if t.direction == "out")

    return {
        "transactions": txns,
        "balance": round(total_in - total_out, 2),
        "total_in": round(total_in, 2),
        "total_out": round(total_out, 2),
        "currency": current_user.primary_currency or "SGD",
    }


@app.delete("/savings/{txn_id}")
def delete_saving(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    txn = db.query(models.SavingsTransaction).filter(
        models.SavingsTransaction.id == txn_id,
        models.SavingsTransaction.user_id == current_user.id,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Savings transaction not found")
    db.delete(txn)
    db.commit()
    return {"ok": True, "id": txn_id}

class GoalRequest(BaseModel):
    name: str
    target_amount: Optional[float] = None
    deadline: Optional[str] = None
    priority: Optional[int] = 0
    is_emergency: Optional[bool] = False


@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return {
        "accounts": ledger.list_accounts(db, current_user),
        "net_worth": ledger.net_worth(db, current_user),
        "currency": current_user.primary_currency or "SGD",
    }


@app.post("/accounts")
def create_goal(body: GoalRequest, db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    acc = models.Account(
        user_id=current_user.id, type="goal", name=body.name,
        target_amount=body.target_amount, deadline=body.deadline,
        priority=body.priority or 0, is_emergency=bool(body.is_emergency),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@app.put("/accounts/{account_id}")
def update_goal(account_id: str, body: GoalRequest, db: Session = Depends(get_db),
                current_user: models.User = Depends(auth.get_current_user)):
    acc = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == current_user.id,
        models.Account.type == "goal",
    ).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Goal not found")
    acc.name = body.name
    acc.target_amount = body.target_amount
    acc.deadline = body.deadline
    acc.priority = body.priority or 0
    acc.is_emergency = bool(body.is_emergency)
    db.commit()
    db.refresh(acc)
    return acc


@app.delete("/accounts/{account_id}")
def archive_goal(account_id: str, db: Session = Depends(get_db),
                 current_user: models.User = Depends(auth.get_current_user)):
    acc = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == current_user.id,
        models.Account.type == "goal",
    ).first()
    if not acc:
        raise HTTPException(status_code=404, detail="Goal not found")
    bal = ledger.account_balances(db, current_user.id).get(acc.id, 0.0)
    if round(bal, 2) != 0:
        raise HTTPException(status_code=400, detail="Empty the goal before deleting it (move its balance first).")
    acc.archived = True
    db.commit()
    return {"ok": True, "id": account_id}


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


class LedgerIncomeRequest(BaseModel):
    amount: float
    source: Optional[str] = ""
    date: Optional[str] = None
    currency: Optional[str] = None


class AllocateRequest(BaseModel):
    amount: float
    currency: Optional[str] = None
    source: Optional[str] = "surplus"        # 'surplus' (from Spending) | 'external' (from World)
    strategy: Optional[str] = "manual"       # 'manual' | 'waterfall' | 'proportional' | 'even'
    splits: Optional[list] = None            # manual: [{"goal_id": "...", "amount": 123}]
    date: Optional[str] = None
    note: Optional[str] = None


class WithdrawRequest(BaseModel):
    goal_id: str
    amount: float
    to: Optional[str] = "spending"           # 'spending' (back to spendable) | 'world' (spent directly)
    date: Optional[str] = None
    note: Optional[str] = None
    currency: Optional[str] = None


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
        category=body.category, counterparty=body.merchant, note=body.note,
        raw_ocr_text=body.raw_ocr_text, parsed_ok=body.parsed_ok,
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


@app.post("/ledger/allocate")
def ledger_allocate(body: AllocateRequest, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    spend = ledger.spending_account(db, current_user.id)
    base = current_user.primary_currency or "SGD"
    # surplus comes out of Spending; external money comes from the World (None)
    frm = (spend.id if spend else None) if body.source != "external" else None
    if body.source != "external" and not spend:
        raise HTTPException(status_code=400, detail="No spending account")

    if body.strategy == "manual":
        if not body.splits:
            raise HTTPException(status_code=400, detail="Provide splits for a manual allocation")
        pairs = [(s["goal_id"], float(s["amount"])) for s in body.splits]
        currency = body.currency or base
    else:
        conv = fx.convert_to_base(amount=body.amount, currency=body.currency or base,
                                  base_currency=base, receipt_date_str=body.date)
        goals = [a for a in ledger.list_accounts(db, current_user) if a["type"] == "goal"]
        pairs = ledger.allocate(conv["amount_base"], body.strategy, goals)
        currency = base

    if not pairs:
        raise HTTPException(status_code=400, detail="Nothing to allocate — do you have any goals?")

    batch = models.gen_uuid()
    result = []
    for goal_id, amt in pairs:
        g = _own_account(db, current_user, goal_id)
        if not g or g.type != "goal":
            raise HTTPException(status_code=400, detail=f"Invalid goal: {goal_id}")
        ledger.post_entry(db, current_user, amount=amt, currency=currency,
                          from_account_id=frm, to_account_id=goal_id, date=body.date,
                          note=body.note, allocation_strategy=body.strategy, batch_id=batch)
        result.append({"goal_id": goal_id, "amount": amt})
    db.commit()
    return {"ok": True, "batch_id": batch, "source": body.source, "strategy": body.strategy, "allocations": result}


@app.post("/ledger/withdraw")
def ledger_withdraw(body: WithdrawRequest, db: Session = Depends(get_db),
                    current_user: models.User = Depends(auth.get_current_user)):
    goal = _own_account(db, current_user, body.goal_id)
    if not goal or goal.type != "goal":
        raise HTTPException(status_code=404, detail="Goal not found")
    spend = ledger.spending_account(db, current_user.id)
    to_id = None if body.to == "world" else (spend.id if spend else None)
    e = ledger.post_entry(db, current_user, amount=body.amount, currency=body.currency,
                          from_account_id=goal.id, to_account_id=to_id,
                          date=body.date, note=body.note)
    db.commit()
    db.refresh(e)
    return e


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