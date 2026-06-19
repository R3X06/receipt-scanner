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

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


@app.get("/auth/me")
def me(current_user: models.User = Depends(auth.get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "primary_currency": current_user.primary_currency or "SGD",
    }


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
    raw_text = ocr.extract_text_from_image(contents)
    parsed = ocr.parse_receipt(raw_text)

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
    try:
        insights = ai.generate_insights(expenses, base_currency)
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

