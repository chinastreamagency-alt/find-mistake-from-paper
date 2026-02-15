"""Database models and setup using SQLAlchemy + SQLite."""

import uuid
import secrets
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = "sqlite:///./data.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def generate_referral_code():
    return secrets.token_urlsafe(6)[:8].upper()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, default="")
    referral_code = Column(String, unique=True, default=generate_referral_code)
    referred_by = Column(String, ForeignKey("users.id"), nullable=True)
    credits = Column(Integer, default=0)  # 剩余分析次数
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    payments = relationship("Payment", back_populates="user", foreign_keys="Payment.user_id")
    referrals_made = relationship("Referral", back_populates="referrer", foreign_keys="Referral.referrer_id")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    stripe_session_id = Column(String, nullable=True)
    stripe_payment_intent = Column(String, nullable=True)
    amount = Column(Integer, nullable=False)  # 金额(分)
    currency = Column(String, default="usd")
    credits_purchased = Column(Integer, default=0)
    status = Column(String, default="pending")  # pending, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="payments", foreign_keys=[user_id])


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    referrer_id = Column(String, ForeignKey("users.id"), nullable=False)
    referee_id = Column(String, ForeignKey("users.id"), nullable=False)
    payment_id = Column(String, ForeignKey("payments.id"), nullable=True)
    commission_amount = Column(Integer, default=0)  # 佣金(分)
    status = Column(String, default="pending")  # pending, paid
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    referrer = relationship("User", back_populates="referrals_made", foreign_keys=[referrer_id])


# 定价方案
PRICING_PLANS = [
    {
        "id": "basic",
        "name": "基础版",
        "name_en": "Basic",
        "price": 990,  # $9.90
        "credits": 10,
        "description": "10 次论文分析",
    },
    {
        "id": "pro",
        "name": "专业版",
        "name_en": "Pro",
        "price": 2990,  # $29.90
        "credits": 50,
        "description": "50 次论文分析",
        "popular": True,
    },
    {
        "id": "unlimited",
        "name": "无限版",
        "name_en": "Unlimited",
        "price": 9990,  # $99.90
        "credits": 999,
        "description": "999 次论文分析",
    },
]

REFERRAL_COMMISSION_RATE = 0.20  # 20% 返佣


def init_db():
    Base.metadata.create_all(bind=engine)
