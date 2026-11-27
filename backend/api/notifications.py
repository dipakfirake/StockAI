from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.notification import Notification
from backend.models.user import User
from backend.services.notification_service import (
    compute_user_notification_counts,
    serialize_notification,
)

router = APIRouter()


async def _fetch_notifications_payload(
    db: AsyncSession,
    user: User,
    category: str | None = None,
    unread_only: bool = False,
    limit: int = 80,
) -> dict:
    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at), desc(Notification.id))
        .limit(max(1, min(limit, 200)))
    )
    notifs = (await db.execute(stmt)).scalars().all()
    items = []
    for n in notifs:
        ser = serialize_notification(n)
        if category and category.upper() != "ALL" and ser["category"].upper() != category.upper():
            continue
        if unread_only and ser["is_read"]:
            continue
        items.append(ser)

    counts = await compute_user_notification_counts(db, user.id)
    return {
        "notifications": items,
        "unseen_count": counts["unseen_count"],
        "unread_count": counts["unread_count"],
        "unseen_by_category": counts["unseen_by_category"],
    }


@router.get("")
@router.get("/", include_in_schema=False)
async def get_notifications(
    category: str | None = None,
    unread_only: bool = False,
    limit: int = 80,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get persisted notifications (Auto-Sells, Order Fills, System Notices) + unread counts."""
    return await _fetch_notifications_payload(
        db,
        current_user,
        category=category,
        unread_only=unread_only,
        limit=limit,
    )


@router.post("/mark-seen")
async def mark_notifications_seen(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clear the tab/bell red unseen marker when user opens the Notifications tab."""
    now = datetime.now(timezone.utc)
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    rows = (await db.execute(stmt)).scalars().all()
    for n in rows:
        if not bool(getattr(n, "is_seen", False)):
            n.is_seen = True
            n.seen_at = now
    await db.commit()
    counts = await compute_user_notification_counts(db, current_user.id)
    return {"success": True, **counts}


@router.post("/mark-all-read")
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as both seen and read."""
    now = datetime.now(timezone.utc)
    stmt = select(Notification).where(Notification.user_id == current_user.id)
    rows = (await db.execute(stmt)).scalars().all()
    for n in rows:
        if not bool(getattr(n, "is_seen", False)):
            n.is_seen = True
            n.seen_at = now
        if not bool(getattr(n, "is_read", False)):
            n.is_read = True
            n.read_at = now
    await db.commit()
    counts = await compute_user_notification_counts(db, current_user.id)
    return {"success": True, **counts}


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an individual notification as seen + read."""
    now = datetime.now(timezone.utc)
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    )
    notif = (await db.execute(stmt)).scalar_one_or_none()
    if notif:
        notif.is_seen = True
        notif.seen_at = notif.seen_at or now
        notif.is_read = True
        notif.read_at = now
        await db.commit()
    counts = await compute_user_notification_counts(db, current_user.id)
    return {"success": True, **counts}
