from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from database import engine, get_db, Base
import models
import auth
import ocr

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
    currency: Optional[str] = "USD"

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
    return {"id": current_user.id, "email": current_user.email}

@app.post("/expenses")
def create_expense(
    body: ExpenseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expense = models.Expense(
        user_id=current_user.id,
        amount=body.amount,
        merchant=body.merchant,
        date=body.date,
        category=body.category,
        currency=body.currency,
        parsed_ok=True
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense

@app.get("/expenses")
def get_expenses(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    expenses = db.query(models.Expense).filter(
        models.Expense.user_id == current_user.id
    ).order_by(models.Expense.created_at.desc()).all()
    return expenses

@app.post("/ocr")
async def scan_receipt(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    contents = await file.read()
    raw_text = ocr.extract_text_from_image(contents)
    parsed = ocr.parse_receipt(raw_text)

    expense = models.Expense(
        user_id=current_user.id,
        amount=parsed["amount"],
        merchant=parsed["merchant"],
        date=parsed["date"],
        category="Uncategorized",
        currency=parsed["currency"],
        raw_ocr_text=raw_text,
        parsed_ok=parsed["parsed_ok"]
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return {
        "expense": expense,
        "raw_text": raw_text,
        "parsed_ok": parsed["parsed_ok"]
    }