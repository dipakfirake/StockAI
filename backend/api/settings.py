from fastapi import APIRouter, Depends
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.settings import SystemSettings
from backend.core.auth import get_current_user
from backend.models.user import User

router = APIRouter()

DEFAULT_SETTINGS = [
    {"key": "default_risk_pct", "value": "2.0", "value_type": "float", "description": "Default risk percentage per trade"},
    {"key": "default_slippage", "value": "0.1", "value_type": "float", "description": "Default slippage percentage"},
    {"key": "enable_trading", "value": "true", "value_type": "boolean", "description": "Global kill switch for trading"}
]

@router.get("/")
async def get_all_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get system settings. Admins or regular users."""
    settings = (await db.execute(select(SystemSettings))).scalars().all()
    if not settings:
        # Seed default settings
        for s in DEFAULT_SETTINGS:
            db.add(SystemSettings(**s))
        await db.commit()
        settings = (await db.execute(select(SystemSettings))).scalars().all()
    
    return {s.key: s.get_typed_value() for s in settings}
