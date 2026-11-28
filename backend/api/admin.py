"""Admin management router for users, subscriptions, and system controls."""

import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.database import get_db
from backend.models.user import User
from backend.models.subscription import SubscriptionOrder
from backend.api.auth import get_current_user
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/admin", tags=["Admin"])


from contextlib import contextmanager
from contextvars import ContextVar

_suppress_rbac_audit: ContextVar[bool] = ContextVar("_suppress_rbac_audit", default=False)


@contextmanager
def suppress_expected_rbac_audit():
    """Suppress synthetic UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT audit logs for expected RBAC self-tests."""
    token = _suppress_rbac_audit.set(True)
    try:
        yield
    finally:
        _suppress_rbac_audit.reset(token)


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Validate that the requesting user has administrative privileges."""
    is_admin = bool(current_user.is_admin)
    if not is_admin:
        if not _suppress_rbac_audit.get():
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
            "is_admin": bool(u.is_admin),
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


class AdminRoleUpdateRequest(BaseModel):
    is_admin: bool


@router.post("/users/{user_id}/set-admin")
async def set_user_admin_status(
    user_id: str,
    payload: AdminRoleUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin grants or revokes administrative privileges for a platform user."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.is_admin = payload.is_admin
    db.add(target_user)
    await db.commit()

    log_security_event(
        event_type="ADMIN_ROLE_UPDATED",
        severity="INFO",
        ip_address="internal",
        user_id=str(admin.id),
        details={
            "admin_email": admin.email,
            "target_user": target_user.email,
            "is_admin": payload.is_admin,
        },
    )

    return {
        "message": f"User {target_user.email} admin privileges set to {payload.is_admin}.",
        "user_id": str(target_user.id),
        "is_admin": target_user.is_admin,
    }


class AdminAcknowledgeAlertsRequest(BaseModel):
    alert_id: str | None = None
    action: str = "ACKNOWLEDGE"  # ACKNOWLEDGE, RESOLVE
    mark_all: bool = False


class AdminBroadcastNoticeRequest(BaseModel):
    title: str
    message: str
    priority: str = "INFO"


@router.get("/alerts-hub")
async def get_admin_alerts_hub(
    category: str | None = None,
    severity: str | None = None,
    unseen_only: bool = False,
    status_filter: str | None = None,
    search: str | None = None,
    limit: int = 80,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Strictly Admin-Only Surveillance Inbox:
    Combines persistent deduplicated security threats, system failures, Celery crashes,
    Fyers feed interruptions, captured application ERROR/WARNING logs, and Sentinel status.
    """
    from backend.services.admin_alerts_service import fetch_admin_alerts_hub_summary
    from backend.services.sentinel import sentinel_service

    hub_data = await fetch_admin_alerts_hub_summary(
        db,
        category=category,
        severity=severity,
        unseen_only=unseen_only,
        status_filter=status_filter,
        search=search,
        limit=limit,
    )
    await db.commit()
    hub_data["sentinel_summary"] = sentinel_service.get_health_summary()
    return hub_data


@router.post("/alerts-hub/mark-seen")
async def mark_admin_alerts_seen(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Clear the red unseen badge on the Admin Control / Threats tab when opened by admin."""
    from backend.models.admin_alert_event import AdminAlertEvent

    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(AdminAlertEvent).where(AdminAlertEvent.is_seen == False))).scalars().all()
    for r in rows:
        r.is_seen = True
        r.seen_at = now
    await db.commit()
    return {"success": True, "unseen_count": 0}


@router.post("/alerts-hub/acknowledge")
async def acknowledge_admin_alerts(
    payload: AdminAcknowledgeAlertsRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge or resolve one or all admin threat/failure alerts."""
    from backend.models.admin_alert_event import AdminAlertEvent

    now = datetime.now(timezone.utc)
    target_status = "RESOLVED" if payload.action.upper() == "RESOLVE" else "ACKNOWLEDGED"

    if payload.mark_all:
        rows = (await db.execute(select(AdminAlertEvent))).scalars().all()
    elif payload.alert_id:
        try:
            a_uuid = uuid.UUID(str(payload.alert_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid alert_id UUID")
        rows = (await db.execute(select(AdminAlertEvent).where(AdminAlertEvent.id == a_uuid))).scalars().all()
    else:
        rows = []

    updated = 0
    for r in rows:
        r.is_seen = True
        r.seen_at = r.seen_at or now
        r.is_read = True
        if target_status == "RESOLVED":
            r.status = "RESOLVED"
            r.resolved_at = now
            r.resolved_by = admin.email
        elif (r.status or "OPEN") == "OPEN":
            r.status = "ACKNOWLEDGED"
            r.acknowledged_at = now
            r.acknowledged_by = admin.email
        updated += 1

    await db.commit()
    if target_status == "RESOLVED" and updated > 0:
        try:
            from backend.services.sentinel import sentinel_service
            sentinel_service._security_log_watermark = now
        except Exception:
            pass
    return {"success": True, "updated": updated, "status": target_status}


@router.post("/broadcast-notice")
async def admin_broadcast_system_notice(
    payload: AdminBroadcastNoticeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Publish an important system announcement into every active user's 🔔 Notifications tab."""
    from backend.services.notification_service import broadcast_system_notice_to_users

    clean_title = (payload.title or "").strip()
    clean_msg = (payload.message or "").strip()
    if not clean_title or not clean_msg:
        raise HTTPException(status_code=400, detail="Title and message are required")
    prio = payload.priority.upper() if payload.priority.upper() in {"INFO", "WARNING", "CRITICAL", "HIGH"} else "INFO"

    sent_count = await broadcast_system_notice_to_users(
        db,
        title=clean_title,
        message=clean_msg,
        priority=prio,
        category="SYSTEM_NOTICE",
        metadata={"sent_by": admin.email, "link": "/alerts", "open_tab": "INBOX"},
        auto_commit=True,
    )
    log_security_event(
        event_type="ADMIN_SYSTEM_NOTICE_BROADCAST",
        severity="INFO",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "title": clean_title, "recipients": sent_count},
    )
    return {"success": True, "recipients": sent_count}

