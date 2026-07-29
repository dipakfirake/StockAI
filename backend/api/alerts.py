"""Alerts API router."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.models.alert import Alert

router = APIRouter()

VALID_CONDITIONS = {
    "PRICE_ABOVE", "PRICE_BELOW",
    "RSI_BELOW", "RSI_ABOVE",
    "MACD_CROSS_UP", "MACD_CROSS_DOWN",
    "SUPERTREND_FLIP", "BB_SQUEEZE", "VOLUME_SURGE", "PATTERN",
}


class CreateAlertRequest(BaseModel):
    symbol: str
    condition_type: str
    condition_value: float
    message: str | None = None


@router.get("")
async def list_alerts(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all alerts for the current user."""
    result = await db.execute(
        select(Alert).where(Alert.user_id == current_user.id).order_by(Alert.created_at.desc())
    )
    alerts = result.scalars().all()
    return {"alerts": [
        {
            "alert_id": str(a.id),
            "symbol": a.symbol,
            "condition_type": a.condition_type,
            "condition_value": float(a.condition_value),
            "message": a.message,
            "is_active": a.is_active,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "created_at": a.created_at.isoformat(),
        }
        for a in alerts
    ]}


@router.post("")
async def create_alert(
    request: CreateAlertRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new alert."""
    if request.condition_type not in VALID_CONDITIONS:
        raise HTTPException(status_code=400, detail=f"Invalid condition_type. Valid: {VALID_CONDITIONS}")

    alert = Alert(
        user_id=current_user.id,
        symbol=request.symbol.upper(),
        condition_type=request.condition_type,
        condition_value=request.condition_value,
        message=request.message,
        is_active=True,
    )
    db.add(alert)
    await db.flush()
    return {"alert_id": str(alert.id), "created": True}


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an alert."""
    result = await db.execute(
        select(Alert).where(Alert.id == uuid.UUID(alert_id), Alert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    return {"deleted": True}


@router.put("/{alert_id}/deactivate")
async def deactivate_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an alert without deleting it."""
    result = await db.execute(
        select(Alert).where(Alert.id == uuid.UUID(alert_id), Alert.user_id == current_user.id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_active = False
    return {"deactivated": True}
