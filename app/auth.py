"""Authentication routes - register, login, user info."""

import os
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db, User, generate_referral_code

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.environ.get("JWT_SECRET", "dev-secret-change-in-production-k8s7d2m")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str = ""
    referral_code: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "无效的登录凭证")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "用户不存在")
    return user


def get_optional_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    """Return user if logged in, None otherwise."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return get_current_user(authorization, db)
    except HTTPException:
        return None


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(400, "该邮箱已注册")

    if len(req.password) < 6:
        raise HTTPException(400, "密码至少6位")

    referred_by = None
    if req.referral_code:
        referrer = db.query(User).filter(User.referral_code == req.referral_code.upper()).first()
        if referrer:
            referred_by = referrer.id

    user = User(
        email=req.email,
        password_hash=pwd_context.hash(req.password),
        name=req.name,
        referred_by=referred_by,
        credits=3,  # 新用户赠送3次免费分析
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {
        "token": token,
        "user": _user_dict(user),
    }


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not pwd_context.verify(req.password, user.password_hash):
        raise HTTPException(401, "邮箱或密码错误")

    token = create_token(user.id)
    return {
        "token": token,
        "user": _user_dict(user),
    }


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {"user": _user_dict(user)}


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "referral_code": user.referral_code,
        "credits": user.credits,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
