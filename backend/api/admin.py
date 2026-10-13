"""Admin management router for users, subscriptions, and system controls."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.database import get_db
from backend.models.user import User
from backend.models.subscription import SubscriptionOrder
from backend.api.auth import get_current_user
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/admin", tags=["Admin"])


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Validate that the requesting user has administrative privileges."""
    is_admin = bool(current_user.is_admin or current_user.email.lower().strip() == "admin@stockai.com")
    if not is_admin:
        log_security_event(
            event_type="UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT",
            severity="WARNING",
            ip_address="internal",
            user_id=str(current_user.id),
            details={"email": current_user.email, "message": "Non-admin attempted admin access"},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required to access this resource",
        )
    return current_user


@router.get("/users")
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all registered platform users with their subscription and approval status."""
    result = await db.execute(select(User).order_by(desc(User.created_at)))
    users = result.scalars().all()

    return [
        {
            "id": str(u.id),
            "name": u.name,
            "email": u.email,
            "is_admin": bool(u.is_admin or u.email.lower().strip() == "admin@stockai.com"),
            "subscription_tier": u.subscription_tier,
            "pro_status": u.pro_status or "NONE",
            "pro_requested_at": u.pro_requested_at.isoformat() if u.pro_requested_at else None,
            "pro_approved_by": u.pro_approved_by,
            "payment_reference": u.payment_reference,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/{user_id}/approve-pro")
async def approve_pro_membership(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin approves a user's pending PRO membership request."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.subscription_tier = "PRO"
    target_user.pro_status = "APPROVED"
    target_user.pro_approved_by = admin.email
    db.add(target_user)

    # Record order
    order = SubscriptionOrder(
        user_id=target_user.id,
        plan_tier="PRO",
        amount=0.0,
        currency="INR",
        payment_method="ADMIN_MANUAL_APPROVAL",
        payment_reference=f"ADMIN-APR-{admin.name.upper()}",
        status="ADMIN_APPROVED",
        note=f"Approved manually by Admin {admin.email}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(order)
    await db.commit()

    log_security_event(
        event_type="PRO_ADMIN_APPROVED",
        severity="INFO",
        ip_address="internal",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "target_user": target_user.email},
    )

    return {
        "message": f"User {target_user.email} successfully upgraded to PRO tier.",
        "user_id": str(target_user.id),
        "subscription_tier": "PRO",
        "pro_status": "APPROVED",
    }


@router.post("/users/{user_id}/reject-pro")
async def reject_pro_membership(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin rejects a user's pending PRO membership request."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.subscription_tier = "FREE"
    target_user.pro_status = "REJECTED"
    db.add(target_user)
    await db.commit()

    return {
        "message": f"Pro request for user {target_user.email} rejected.",
        "user_id": str(target_user.id),
        "subscription_tier": "FREE",
        "pro_status": "REJECTED",
    }


@router.post("/users/{user_id}/revoke-pro")
async def revoke_pro_membership(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin revokes a user's PRO membership back to FREE."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.subscription_tier = "FREE"
    target_user.pro_status = "NONE"
    db.add(target_user)
    await db.commit()

    log_security_event(
        event_type="PRO_ADMIN_REVOKED",
        severity="INFO",
        ip_address="internal",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "target_user": target_user.email},
    )

    return {
        "message": f"PRO membership for user {target_user.email} has been revoked.",
        "user_id": str(target_user.id),
        "subscription_tier": "FREE",
        "pro_status": "NONE",
    }
