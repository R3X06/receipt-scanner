from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey
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
    created_at = Column(DateTime, default=datetime.utcnow)

    expenses = relationship("Expense", back_populates="owner")


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
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="expenses")