"""
Presence API router for real-time live active user counting.
Provides endpoints for heartbeat, leave beacon, and current active count.
"""

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, Field
from typing import Optional
import json

from backend.services.presence import presence_service
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


class PresencePayload(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128, description="Unique client session identifier")


@router.post("/heartbeat", status_code=status.HTTP_200_OK)
async def heartbeat(payload: PresencePayload):
    """
    Record or refresh a client session heartbeat.
    Returns the current number of active users online.
    """
    count = await presence_service.record_heartbeat(payload.session_id)
    return {"count": count, "status": "active"}


@router.post("/leave", status_code=status.HTTP_200_OK)
async def leave(request: Request):
    """
    Record that a client session has left (closed tab, hidden, or moved to mobile recent apps).
    Supports both standard JSON body and navigator.sendBeacon payloads.
    """
    session_id: Optional[str] = None
    try:
        # First attempt JSON body parsing
        body = await request.body()
        if body:
            try:
                data = json.loads(body.decode("utf-8"))
                session_id = data.get("session_id")
            except Exception:
                # If body was sent as plain string
                session_id = body.decode("utf-8").strip()
    except Exception as exc:
        logger.debug(f"[Presence] Error reading leave payload: {exc}")

    if not session_id:
        # Fallback to query param if any
        session_id = request.query_params.get("session_id")

    if session_id:
        # Sanitize session_id length
        session_id = str(session_id)[:128]
        count = await presence_service.record_leave(session_id)
        return {"count": count, "status": "left"}

    count = await presence_service.get_active_count()
    return {"count": count, "status": "noop"}


@router.get("/count", status_code=status.HTTP_200_OK)
async def get_count():
    """
    Get the current active users count.
    """
    count = await presence_service.get_active_count()
    return {"count": count}
