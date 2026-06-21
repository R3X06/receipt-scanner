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

Base.metadata.create_all(bind=engine)

import migrate
migrate.run()

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
    for field in ("display_name", "avatar", "primary_currency", "monthly_budget", "occupation", "monthly_income", "goals"):
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
        parsed_ok=body.parsed_ok
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

    expenses = db.query(models.Expense).filter(
        models.Expense.user_id == current_user.id
    ).order_by(models.Expense.created_at.desc()).all()

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
    expenses = db.query(models.Expense).filter(
        models.Expense.user_id == current_user.id
    ).order_by(models.Expense.created_at.desc()).all()

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

