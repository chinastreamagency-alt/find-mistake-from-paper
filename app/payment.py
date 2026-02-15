"""Stripe payment routes - checkout, webhook, pricing."""

import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db, User, Payment, Referral, PRICING_PLANS, REFERRAL_COMMISSION_RATE
from app.auth import get_current_user

router = APIRouter(prefix="/api/payment", tags=["payment"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


class CheckoutRequest(BaseModel):
    plan_id: str


@router.get("/plans")
def get_plans():
    return {"plans": PRICING_PLANS}


@router.post("/create-checkout")
def create_checkout(req: CheckoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not stripe.api_key:
        raise HTTPException(500, "支付未配置，请联系管理员设置 STRIPE_SECRET_KEY")

    plan = next((p for p in PRICING_PLANS if p["id"] == req.plan_id), None)
    if not plan:
        raise HTTPException(400, "无效的套餐")

    # 创建支付记录
    payment = Payment(
        user_id=user.id,
        amount=plan["price"],
        credits_purchased=plan["credits"],
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"学术诚信检查器 - {plan['name']} ({plan['name_en']})",
                        "description": plan["description"],
                    },
                    "unit_amount": plan["price"],
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{BASE_URL}/?payment=success",
            cancel_url=f"{BASE_URL}/?payment=cancel",
            metadata={
                "payment_id": payment.id,
                "user_id": user.id,
                "plan_id": plan["id"],
            },
        )

        payment.stripe_session_id = session.id
        db.commit()

        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        raise HTTPException(500, f"创建支付失败: {str(e)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            raise HTTPException(400, "Webhook 签名验证失败")
    else:
        import json
        event = json.loads(payload)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        payment_id = metadata.get("payment_id")
        user_id = metadata.get("user_id")

        if payment_id:
            payment = db.query(Payment).filter(Payment.id == payment_id).first()
            if payment and payment.status == "pending":
                payment.status = "completed"
                payment.stripe_payment_intent = session.get("payment_intent")

                # 增加用户 credits
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.credits += payment.credits_purchased

                    # 处理推荐返佣
                    if user.referred_by:
                        commission = int(payment.amount * REFERRAL_COMMISSION_RATE)
                        referral = Referral(
                            referrer_id=user.referred_by,
                            referee_id=user.id,
                            payment_id=payment.id,
                            commission_amount=commission,
                            status="pending",
                        )
                        db.add(referral)

                        # 给推荐人奖励 credits（每100分佣金奖1次分析）
                        referrer = db.query(User).filter(User.id == user.referred_by).first()
                        if referrer:
                            bonus_credits = max(1, commission // 100)
                            referrer.credits += bonus_credits

                db.commit()

    return {"received": True}
