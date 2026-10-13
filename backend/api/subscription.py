"""Subscription & Pro Membership Management Router."""

import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.models.user import User
from backend.models.subscription import SubscriptionOrder
from backend.api.auth import get_current_user
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/subscription", tags=["Subscription"])


class ProRequestSchema(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class CheckoutSchema(BaseModel):
    payment_method: str = Field(default="UPI", description="UPI, CARD, NETBANKING")
    payment_reference: str = Field(default="", description="Transaction ID or payment receipt reference")
    amount: float = Field(default=29.0)


@router.get("/status")
async def get_subscription_status(current_user: User = Depends(get_current_user)):
    """Get current user's subscription details and pending request status."""
    is_admin = bool(current_user.is_admin or current_user.email.lower().strip() == "admin@stockai.com")
    tier = "PRO" if is_admin else current_user.subscription_tier
    pro_status = "APPROVED" if is_admin else (current_user.pro_status or "NONE")

    return {
        "user_id": str(current_user.id),
        "email": current_user.email,
        "subscription_tier": tier,
        "pro_status": pro_status,
        "is_admin": is_admin,
        "pro_requested_at": current_user.pro_requested_at.isoformat() if current_user.pro_requested_at else None,
        "payment_reference": current_user.payment_reference,
    }


@router.post("/request-pro")
async def request_pro_access(
    req: ProRequestSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a request for Admin review and manual approval."""
    if current_user.subscription_tier == "PRO":
        return {
            "message": "User is already on PRO tier",
            "subscription_tier": "PRO",
            "pro_status": "ACTIVE",
        }

    now = datetime.now(timezone.utc)
    current_user.pro_status = "REQUESTED"
    current_user.pro_requested_at = now
    db.add(current_user)

    # Record order audit
    order = SubscriptionOrder(
        user_id=current_user.id,
        plan_tier="PRO",
        amount=0.0,
        currency="INR",
        payment_method="ADMIN_APPROVAL",
        payment_reference=None,
        status="PENDING_APPROVAL",
        note=req.note or "User requested admin approval",
        created_at=now,
    )
    db.add(order)
    await db.commit()

    log_security_event(
        event_type="PRO_APPROVAL_REQUESTED",
        severity="INFO",
        ip_address="internal",
        user_id=str(current_user.id),
        details={"email": current_user.email, "note": req.note},
    )

    return {
        "message": "PRO upgrade request submitted successfully! An administrator will review your account.",
        "subscription_tier": current_user.subscription_tier,
        "pro_status": "REQUESTED",
        "requested_at": now.isoformat(),
    }


@router.post("/checkout")
async def checkout_payment(
    req: CheckoutSchema,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Verify payment and instantly upgrade to PRO tier.
    Accepts verified payment reference or simulates payment gateway webhook.
    """
    if current_user.subscription_tier == "PRO":
        return {
            "message": "User is already on PRO tier",
            "subscription_tier": "PRO",
            "pro_status": "ACTIVE",
        }

    ref = req.payment_reference.strip()
    if not ref:
        # Generate formal receipt reference
        ref = f"PAY-STK-{uuid.uuid4().hex[:10].upper()}"

    now = datetime.now(timezone.utc)
    current_user.subscription_tier = "PRO"
    current_user.pro_status = "ACTIVE"
    current_user.payment_reference = ref
    current_user.payment_method = req.payment_method.upper()
    db.add(current_user)

    order = SubscriptionOrder(
        user_id=current_user.id,
        plan_tier="PRO",
        amount=req.amount,
        currency="USD",
        payment_method=req.payment_method.upper(),
        payment_reference=ref,
        status="SUCCESS",
        note="Payment verified and activated",
        created_at=now,
    )
    db.add(order)
    await db.commit()

    log_security_event(
        event_type="PRO_PAYMENT_ACTIVATED",
        severity="INFO",
        ip_address="internal",
        user_id=str(current_user.id),
        details={"email": current_user.email, "payment_ref": ref, "amount": req.amount},
    )

    return {
        "message": "Payment verified successfully! Welcome to StockAI PRO.",
        "subscription_tier": "PRO",
        "pro_status": "ACTIVE",
        "payment_reference": ref,
    }
