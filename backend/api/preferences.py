"""User Preferences API — stores and retrieves per-user UI/app preferences."""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.user_preference import UserPreference

router = APIRouter()

# Allowlist of valid preference keys to prevent arbitrary data storage
ALLOWED_PREF_KEYS = {
    # Chart page
    "chart_symbol",
    "chart_timeframe",
    "chart_is_heikin_ashi",
    "chart_show_indicators",
    "chart_show_patterns",
    "chart_show_events",
    # Scanner page
    "scanner_rule",
    "scanner_sector",
    "scanner_mode",
    "scanner_timeframe",
    # Backtest page
    "backtest_symbol",
    "backtest_strategy",
    "backtest_start_date",
    "backtest_end_date",
    "backtest_initial_capital",
}


class PreferencesUpdateRequest(BaseModel):
    preferences: Dict[str, Any]


@router.get("/")
async def get_preferences(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Load all stored preferences for the current user.
    Returns a flat dict: { "chart_symbol": "RELIANCE.NS", ... }
    Unknown or missing keys are simply absent from the response.
    """
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    rows = result.scalars().all()
    return {row.pref_key: row.get_value() for row in rows}


@router.put("/")
async def update_preferences(
    request: PreferencesUpdateRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk-upsert preferences for the current user.
    Only keys in ALLOWED_PREF_KEYS are accepted; unknown keys are silently ignored
    to prevent arbitrary data from being stored.
    Returns all currently stored preferences after the update.
    """
    # Filter to only allowed keys
    safe_prefs = {k: v for k, v in request.preferences.items() if k in ALLOWED_PREF_KEYS}

    if not safe_prefs:
        # Nothing valid to update — return current state
        result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == current_user.id)
        )
        rows = result.scalars().all()
        return {row.pref_key: row.get_value() for row in rows}

    # Fetch existing rows for this user
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    existing = {row.pref_key: row for row in result.scalars().all()}

    for key, value in safe_prefs.items():
        if key in existing:
            # Update existing row
            existing[key].set_value(value)
        else:
            # Insert new preference row
            new_pref = UserPreference(
                user_id=current_user.id,
                pref_key=key,
            )
            new_pref.set_value(value)
            db.add(new_pref)
            existing[key] = new_pref

    await db.commit()

    # Re-fetch to return consistent state
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    rows = result.scalars().all()
    return {row.pref_key: row.get_value() for row in rows}
