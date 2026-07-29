"""Watchlist API router."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.models.watchlist import Watchlist
from backend.services.market_data import market_data_service

router = APIRouter()


class AddToWatchlistRequest(BaseModel):
    symbol: str


@router.get("")
async def get_watchlist(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get watchlist with live quotes."""
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id).order_by(Watchlist.added_at.desc())
    )
    items = result.scalars().all()

    stocks = []
    for item in items:
        quote = await market_data_service.fetch_quote(item.symbol)
        entry = {"symbol": item.symbol, "added_at": item.added_at.isoformat()}
        if quote:
            entry.update({
                "price": quote.get("price"),
                "change": quote.get("change"),
                "change_pct": quote.get("change_pct"),
                "volume": quote.get("volume"),
            })
        stocks.append(entry)

    return {"stocks": stocks}


@router.post("")
async def add_to_watchlist(
    request: AddToWatchlistRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a stock to the watchlist."""
    symbol = request.symbol.upper().strip()
    # Check already exists
    existing = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.symbol == symbol)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"{symbol} is already in your watchlist")

    item = Watchlist(user_id=current_user.id, symbol=symbol)
    db.add(item)
    await db.flush()
    return {"added": True, "symbol": symbol}


@router.delete("/{symbol}")
async def remove_from_watchlist(
    symbol: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a stock from the watchlist."""
    symbol = symbol.upper()
    result = await db.execute(
        select(Watchlist).where(Watchlist.user_id == current_user.id, Watchlist.symbol == symbol)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail=f"{symbol} not in watchlist")
    await db.delete(item)
    return {"removed": True, "symbol": symbol}
