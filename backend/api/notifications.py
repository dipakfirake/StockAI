from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.notification import Notification
from backend.core.auth import get_current_user
from backend.models.user import User

router = APIRouter()

@router.get("/")
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all notifications for the current user."""
    stmt = select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.created_at.desc()).limit(50)
    notifs = (await db.execute(stmt)).scalars().all()
    return {"notifications": notifs}

@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read."""
    stmt = select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id)
    notif = (await db.execute(stmt)).scalar_one_or_none()
    if notif:
        notif.is_read = True
        await db.commit()
    return {"success": True}
