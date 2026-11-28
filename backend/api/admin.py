"""Admin management router for users, subscriptions, and system controls."""

import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.config import settings
from backend.core.database import get_db
from backend.models.user import User
from backend.models.subscription import SubscriptionOrder
from backend.api.auth import get_current_user
from backend.core.auth import (
    create_stepup_token,
    verify_stepup_token,
    invalidate_user_auth_cache,
    verify_password,
)
from backend.core.audit_logger import log_security_event
from backend.core.encryption import encrypt_secret, decrypt_secret
from backend.core.totp_mfa import (
    generate_totp_secret,
    get_otpauth_uri,
    format_secret_blocks,
    generate_qr_svg_data_uri,
    verify_totp_code,
    generate_recovery_codes,
    consume_recovery_code,
)

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


async def require_admin_stepup(
    request: Request,
    admin: User = Depends(require_admin),
) -> User:
    """
    Require short-lived TOTP step-up verification for sensitive Admin actions ONLY when
    the acting administrator has enrolled TOTP MFA (`totp_enabled == True`).
    This guarantees zero lockout before enrollment while locking down enrolled admin accounts.
    """
    if not bool(getattr(admin, "totp_enabled", False)):
        return admin

    stepup_tok = request.headers.get("X-Admin-StepUp-Token")
    if stepup_tok and verify_stepup_token(stepup_tok, admin.id):
        return admin

    direct_code = request.headers.get("X-Admin-TOTP")
    if direct_code:
        secret = decrypt_secret(getattr(admin, "totp_secret_encrypted", None))
        if verify_totp_code(secret, direct_code):
            return admin

    log_security_event(
        event_type="ADMIN_STEPUP_REQUIRED",
        severity="INFO",
        ip_address=request.client.host if request.client else "unknown",
        user_id=str(admin.id),
        details={"email": admin.email, "path": request.url.path},
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Authenticator step-up verification required for this administrative action.",
        headers={"X-StepUp-Required": "totp"},
    )


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
            "totp_enabled": bool(getattr(u, "totp_enabled", False)),
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
    admin: User = Depends(require_admin_stepup),
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
    admin: User = Depends(require_admin_stepup),
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
    admin: User = Depends(require_admin_stepup),
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
    admin: User = Depends(require_admin_stepup),
    db: AsyncSession = Depends(get_db),
):
    """Admin grants or revokes administrative privileges with sole-admin & self-lockout protection."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if not payload.is_admin:
        if str(target_user.id) == str(admin.id):
            raise HTTPException(
                status_code=400,
                detail="Switch to your new personal admin account before revoking admin privileges from this account.",
            )
        admin_rows = (
            await db.execute(select(User).where(User.is_admin == True, User.is_active == True))
        ).scalars().all()
        if len(admin_rows) <= 1 and target_user.is_admin:
            raise HTTPException(
                status_code=400,
                detail="Cannot revoke privileges from the last remaining platform administrator.",
            )
        # Immediately invalidate legacy JWT sessions of demoted admin account
        target_user.token_version = int(getattr(target_user, "token_version", 1) or 1) + 1
        invalidate_user_auth_cache(target_user.id)

    target_user.is_admin = payload.is_admin
    if payload.is_admin:
        target_user.subscription_tier = "PRO"
        target_user.pro_status = "APPROVED"
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


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: str,
    admin: User = Depends(require_admin_stepup),
    db: AsyncSession = Depends(get_db),
):
    """Force-invalidate all active JWT cookies/tokens for a user by bumping token_version."""
    try:
        u_uuid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(select(User).where(User.id == u_uuid))
    target_user = result.scalars().first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.token_version = int(getattr(target_user, "token_version", 1) or 1) + 1
    invalidate_user_auth_cache(target_user.id)
    db.add(target_user)
    await db.commit()

    log_security_event(
        event_type="USER_SESSIONS_REVOKED",
        severity="INFO",
        ip_address="internal",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "target_user": target_user.email, "token_version": target_user.token_version},
    )
    return {
        "success": True,
        "message": f"All active sessions terminated for {target_user.email}.",
        "token_version": target_user.token_version,
    }


class MfaEnrollConfirmRequest(BaseModel):
    setup_token: str
    code: str


class MfaCodeRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    password: str
    code: str


@router.get("/mfa/status")
async def get_admin_mfa_status(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Inspect current admin's TOTP Authenticator MFA enrollment & admin ownership count."""
    import json as _json

    admin_rows = (
        await db.execute(select(User).where(User.is_admin == True, User.is_active == True))
    ).scalars().all()
    raw_hashes = getattr(admin, "totp_recovery_hashes", None) or "[]"
    try:
        recovery_remaining = len(_json.loads(raw_hashes))
    except Exception:
        recovery_remaining = 0

    return {
        "email": admin.email,
        "totp_enabled": bool(getattr(admin, "totp_enabled", False)),
        "recovery_codes_remaining": recovery_remaining,
        "active_admin_count": len(admin_rows),
        "admin_emails": [a.email for a in admin_rows],
    }


@router.post("/mfa/enroll/start")
async def start_admin_mfa_enrollment(
    admin: User = Depends(require_admin),
):
    """
    Generate an authenticator TOTP secret + offline SVG QR code without requiring email delivery.
    Secret is only activated once `confirm` verifies a live 6-digit authenticator code.
    """
    secret = generate_totp_secret()
    uri = get_otpauth_uri(secret, admin.email, issuer="StockAI Admin")
    qr_svg = generate_qr_svg_data_uri(uri)
    setup_payload = {
        "sub": str(admin.id),
        "scope": "mfa_setup",
        "sec": encrypt_secret(secret),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    setup_token = jwt.encode(setup_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return {
        "setup_token": setup_token,
        "otpauth_uri": uri,
        "manual_secret": format_secret_blocks(secret),
        "qr_svg": qr_svg,
    }


@router.post("/mfa/enroll/confirm")
async def confirm_admin_mfa_enrollment(
    payload: MfaEnrollConfirmRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Verify live 6-digit Authenticator code to activate TOTP MFA and issue single-use recovery codes."""
    try:
        claims = jwt.decode(payload.setup_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if claims.get("scope") != "mfa_setup" or str(claims.get("sub")) != str(admin.id):
            raise HTTPException(status_code=400, detail="Invalid or expired MFA setup session.")
        secret = decrypt_secret(claims.get("sec"))
    except JWTError:
        raise HTTPException(status_code=400, detail="MFA setup session expired. Please generate a fresh QR code.")

    if not verify_totp_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Authenticator code did not match. Check device clock and retry.")

    plain_recovery, hashed_recovery_json = generate_recovery_codes(8)
    result = await db.execute(select(User).where(User.id == admin.id))
    db_admin = result.scalar_one_or_none() or admin

    db_admin.totp_secret_encrypted = encrypt_secret(secret)
    db_admin.totp_enabled = True
    db_admin.totp_recovery_hashes = hashed_recovery_json
    db.add(db_admin)
    await db.commit()
    invalidate_user_auth_cache(db_admin.id)

    log_security_event(
        event_type="ADMIN_TOTP_MFA_ENABLED",
        severity="INFO",
        ip_address="internal",
        user_id=str(db_admin.id),
        details={"email": db_admin.email},
    )
    return {
        "enabled": True,
        "recovery_codes": plain_recovery,
        "message": "Authenticator MFA enabled cleanly. Save these 8 single-use recovery codes in a safe place.",
    }


@router.post("/mfa/step-up")
async def verify_admin_stepup(
    payload: MfaCodeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Issue a 10-minute step-up authorization token after validating Authenticator TOTP (or recovery code)."""
    if not bool(getattr(admin, "totp_enabled", False)):
        return {"stepup_token": create_stepup_token(str(admin.id)), "expires_in": 600}

    secret = decrypt_secret(getattr(admin, "totp_secret_encrypted", None))
    ok = verify_totp_code(secret, payload.code)
    used_rec = False
    if not ok:
        used_rec, updated_hashes = consume_recovery_code(getattr(admin, "totp_recovery_hashes", None), payload.code)
        if used_rec:
            result = await db.execute(select(User).where(User.id == admin.id))
            db_admin = result.scalar_one_or_none()
            if db_admin:
                db_admin.totp_recovery_hashes = updated_hashes
                db.add(db_admin)
                await db.commit()

    if not ok and not used_rec:
        log_security_event(
            event_type="ADMIN_STEPUP_FAILED",
            severity="WARNING",
            ip_address="internal",
            user_id=str(admin.id),
            details={"email": admin.email},
        )
        raise HTTPException(status_code=401, detail="Invalid authenticator or recovery code.")

    return {"stepup_token": create_stepup_token(str(admin.id)), "expires_in": 600}


@router.post("/mfa/disable")
async def disable_admin_mfa(
    payload: MfaDisableRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Disable Admin TOTP MFA cleanly after verifying current password and live TOTP/recovery code."""
    if not verify_password(payload.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect account password.")

    if bool(getattr(admin, "totp_enabled", False)):
        secret = decrypt_secret(getattr(admin, "totp_secret_encrypted", None))
        ok = verify_totp_code(secret, payload.code)
        if not ok:
            ok, _ = consume_recovery_code(getattr(admin, "totp_recovery_hashes", None), payload.code)
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid authenticator or recovery code.")

    result = await db.execute(select(User).where(User.id == admin.id))
    db_admin = result.scalar_one_or_none() or admin
    db_admin.totp_enabled = False
    db_admin.totp_secret_encrypted = None
    db_admin.totp_recovery_hashes = None
    db.add(db_admin)
    await db.commit()
    invalidate_user_auth_cache(db_admin.id)

    log_security_event(
        event_type="ADMIN_TOTP_MFA_DISABLED",
        severity="INFO",
        ip_address="internal",
        user_id=str(db_admin.id),
        details={"email": db_admin.email},
    )
    return {"enabled": False, "message": "Admin TOTP MFA disabled."}


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
    from backend.services.sentinel import sentinel_service

    if target_status == "RESOLVED" and (updated > 0 or payload.mark_all):
        try:
            from backend.models.sentinel_incident import SentinelIncident
            from backend.models.settings import SystemSettings

            resolved_titles = {getattr(r, "title", None) for r in rows if getattr(r, "title", None)}
            try:
                inc_stmt = select(SentinelIncident).where(SentinelIncident.status != "RESOLVED")
                if not payload.mark_all and resolved_titles:
                    inc_stmt = inc_stmt.where(SentinelIncident.title.in_(resolved_titles))
                inc_rows = (await db.execute(inc_stmt)).scalars().all()
                for s_inc in inc_rows:
                    s_inc.status = "RESOLVED"
                    s_inc.resolved_at = now
                    s_inc.resolved_by = admin.email
                if inc_rows:
                    await db.commit()
            except Exception:
                pass

            remaining_rows = (
                await db.execute(
                    select(AdminAlertEvent).where(AdminAlertEvent.status != "RESOLVED")
                )
            ).scalars().all()
            remaining_sec = sum(
                1
                for rem in remaining_rows
                if (rem.category in ("SECURITY_THREAT", "SYSTEM_FAILURE", "CELERY_FAILURE"))
            )
            sentinel_service.sync_security_health_after_resolve(remaining_sec)

            if remaining_sec <= 0:
                try:
                    wm = (
                        await db.execute(
                            select(SystemSettings).where(SystemSettings.key == "sentinel_security_watermark")
                        )
                    ).scalars().first()
                    if wm:
                        wm.value = now.isoformat()
                    else:
                        db.add(
                            SystemSettings(
                                key="sentinel_security_watermark",
                                value=now.isoformat(),
                                value_type="string",
                                description="Sentinel security audit log resolved watermark",
                            )
                        )
                    await db.commit()
                except Exception:
                    pass
        except Exception:
            pass
    return {
        "success": True,
        "updated": updated,
        "status": target_status,
        "sentinel_summary": sentinel_service.get_health_summary(),
    }


@router.post("/broadcast-notice")
async def admin_broadcast_system_notice(
    payload: AdminBroadcastNoticeRequest,
    admin: User = Depends(require_admin_stepup),
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


@router.get("/dr/status")
async def get_disaster_recovery_status(admin: User = Depends(require_admin)):
    """Inspect Alembic schema migration sync, snapshots, and latest DR restore drill."""
    from backend.core.backup_dr import get_dr_status
    return await get_dr_status()


@router.post("/dr/backup")
async def create_dr_snapshot(admin: User = Depends(require_admin_stepup)):
    """Trigger an immediate portable database backup snapshot with SHA-256 verification."""
    from backend.core.backup_dr import create_database_snapshot, verify_backup_snapshot

    snapshot = await create_database_snapshot(include_candles=False)
    verify = verify_backup_snapshot(snapshot["path"])
    log_security_event(
        event_type="ADMIN_DR_BACKUP_CREATED",
        severity="INFO",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "filename": snapshot["filename"], "rows": snapshot["total_rows"]},
    )
    return {"snapshot": snapshot, "verification": verify}


@router.post("/dr/verify")
async def run_dr_verification_drill(admin: User = Depends(require_admin_stepup)):
    """Execute a non-destructive Disaster Recovery restore drill against an isolated sandbox DB."""
    from backend.core.backup_dr import (
        list_snapshots,
        create_database_snapshot,
        run_restore_drill,
        record_verified_drill,
    )

    snapshots = list_snapshots()
    if not snapshots:
        created = await create_database_snapshot(include_candles=False)
        target_path = created["path"]
    else:
        target_path = snapshots[0]["path"]

    drill = await run_restore_drill(target_path)
    record_verified_drill(drill)
    log_security_event(
        event_type="ADMIN_DR_DRILL_PASSED",
        severity="INFO",
        user_id=str(admin.id),
        details={"admin_email": admin.email, "filename": drill["filename"], "restored_rows": drill["restored_rows"]},
    )
    return drill

