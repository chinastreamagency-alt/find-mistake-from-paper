"""Referral system routes - stats, link, earnings."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db, User, Referral, REFERRAL_COMMISSION_RATE
from app.auth import get_current_user

router = APIRouter(prefix="/api/referral", tags=["referral"])


@router.get("/stats")
def get_referral_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 推荐了多少人
    total_referred = db.query(User).filter(User.referred_by == user.id).count()

    # 总佣金
    total_commission = db.query(func.coalesce(func.sum(Referral.commission_amount), 0)).filter(
        Referral.referrer_id == user.id
    ).scalar()

    # 待结算佣金
    pending_commission = db.query(func.coalesce(func.sum(Referral.commission_amount), 0)).filter(
        Referral.referrer_id == user.id,
        Referral.status == "pending",
    ).scalar()

    # 已结算佣金
    paid_commission = db.query(func.coalesce(func.sum(Referral.commission_amount), 0)).filter(
        Referral.referrer_id == user.id,
        Referral.status == "paid",
    ).scalar()

    # 最近推荐记录
    recent_referrals = db.query(Referral).filter(
        Referral.referrer_id == user.id
    ).order_by(Referral.created_at.desc()).limit(20).all()

    return {
        "referral_code": user.referral_code,
        "commission_rate": int(REFERRAL_COMMISSION_RATE * 100),
        "total_referred": total_referred,
        "total_commission": total_commission,
        "pending_commission": pending_commission,
        "paid_commission": paid_commission,
        "recent": [
            {
                "id": r.id,
                "commission_amount": r.commission_amount,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent_referrals
        ],
    }
