"""
Presence API router for real-time live active user counting and surveillance.
Provides endpoints for heartbeat, leave beacon, active count, and detailed active users list.
Runs 100% in-memory via Redis with ZERO PostgreSQL queries.
"""

from fastapi import APIRouter, Request, Depends, status
from pydantic import BaseModel, Field
from typing import Optional, Any
import json

from backend.services.presence import presence_service
from backend.core.logging_config import get_logger
from backend.models.user import User
from backend.api.admin import require_admin

logger = get_logger(__name__)

router = APIRouter()


class PresencePayload(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128, description="Unique client session identifier")
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role: Optional[str] = None
    path: Optional[str] = None
    device: Optional[str] = None


@router.post("/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat(payload: PresencePayload):
    """
    Record or refresh a client session heartbeat.
    Passes optional user and device metadata to Redis in-memory storage (0 DB queries).
    Returns the current number of active users online.
    """
    meta = {
        "user_id": payload.user_id,
        "user_name": payload.user_name,
        "user_email": payload.user_email,
        "role": payload.role or "GUEST",
        "path": payload.path or "/dashboard",
        "device": payload.device or "Desktop",
    }
    count = await presence_service.record_heartbeat(payload.session_id, meta)
    return {"count": count, "status": "active"}


@router.post("/leave", status_code=status.HTTP_200_OK)
async def leave(request: Request):
    """
    Record that a client session has left (closed tab, hidden, or moved to mobile recent apps).
    Supports both standard JSON body and navigator.sendBeacon payloads.
    Pure in-memory Redis removal (0 DB queries).
    """
    session_id: Optional[str] = None
    try:
        body = await request.body()
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
                session_id = data.get("session_id")
            except Exception:
                session_id = body.decode("utf-8").strip()
    except Exception as exc:
        logger.debug(f"[Presence] Error reading leave payload: {exc}")

    if not session_id:
        session_id = request.query_params.get("session_id")

    if session_id:
        session_id = str(session_id)[:128]
        count = await presence_service.record_leave(session_id)
        return {"count": count, "status": "left"}

    count = await presence_service.get_active_count()
    return {"count": count, "status": "noop"}


@router.get("/count", status_code=status.HTTP_200_OK)
async def get_count():
    """
    Get the current active users count.
    Fast in-memory Redis lookup (0 DB queries).
    """
    count = await presence_service.get_active_count()
    return {"count": count}


@router.get("/users", status_code=status.HTTP_200_OK)
async def get_live_users(admin: User = Depends(require_admin)):
    """
    Get detailed list of all live active users currently on the system.
    STRICTLY RESTRICTED TO ADMINS.
    Reads 100% from in-memory Redis with ZERO PostgreSQL database queries.
    """
    return await presence_service.get_live_users()
