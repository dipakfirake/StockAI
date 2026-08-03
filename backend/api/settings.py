from fastapi import APIRouter, Depends
from typing import Any, Dict
from pydantic import BaseModel
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


class UpdateSettingsRequest(BaseModel):
    values: Dict[str, Any]


@router.put("/")
async def update_settings(
    request: UpdateSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update persisted dynamic configuration with its declared type preserved."""
    existing = {item.key: item for item in (await db.execute(select(SystemSettings))).scalars().all()}
    unknown = set(request.values) - set(existing)
    if unknown:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unknown settings: {', '.join(sorted(unknown))}")
    for key, value in request.values.items():
        item = existing[key]
        try:
            if item.value_type == "boolean":
                if isinstance(value, str):
                    if value.lower() not in {"true", "false"}:
                        raise ValueError("must be true or false")
                    value = value.lower() == "true"
                if not isinstance(value, bool):
                    raise ValueError("must be boolean")
                item.value = str(value).lower()
            elif item.value_type == "int":
                item.value = str(int(value))
            elif item.value_type == "float":
                item.value = str(float(value))
            else:
                item.value = str(value)
        except (TypeError, ValueError) as exc:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail=f"Invalid value for {key}: {exc}") from exc
    await db.flush()
    return {key: item.get_typed_value() for key, item in existing.items()}
