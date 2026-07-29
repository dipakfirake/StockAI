"""Stocks API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.signals import signal_engine
from backend.services.ai_engine import ai_engine_service

router = APIRouter()


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1, description="Stock name or symbol"),
    current_user=Depends(get_current_user),
):
    """Search stocks by name or symbol."""
    results = await market_data_service.search_stocks(q)
    return {"results": results}


@router.get("/{symbol}/quote")
async def get_quote(symbol: str, current_user=Depends(get_current_user)):
    """Get live quote for a stock."""
    quote = await market_data_service.fetch_quote(symbol)
    if not quote:
        raise HTTPException(status_code=404, detail=f"No quote data found for {symbol}")
    return quote


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 30m, 1h, 1d, 1w"),
    limit: int = Query(200, ge=1, le=2000),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    """Get OHLCV candlestick data with indicator series."""
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit, start_date, end_date)
    series_candles = indicator_service.compute_for_candles_series(candles)
    return {"symbol": symbol, "timeframe": timeframe, "candles": series_candles}


@router.get("/{symbol}/indicators")
async def get_indicators(
    symbol: str,
    timeframe: str = Query("1d"),
    current_user=Depends(get_current_user),
):
    """Get computed technical indicators."""
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit=250)
    if len(candles) < 30:
        raise HTTPException(status_code=422, detail="Insufficient data to compute indicators")
    indicators = indicator_service.compute_all(candles)
    return {"symbol": symbol, "timeframe": timeframe, "indicators": indicators}


@router.get("/{symbol}/signals")
async def get_signals(
    symbol: str,
    timeframe: str = Query("1d"),
    current_user=Depends(get_current_user),
):
    """Get rule-based trading signals with explanations."""
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit=250)
    if len(candles) < 30:
        raise HTTPException(status_code=422, detail="Insufficient data to compute signals")
    indicators = indicator_service.compute_all(candles)
    signals = signal_engine.evaluate(indicators, symbol)
    return {"symbol": symbol, "timeframe": timeframe, "signals": signals}


@router.get("/{symbol}/ai-score")
async def get_ai_score(
    symbol: str,
    timeframe: str = Query("1d"),
    current_user=Depends(get_current_user),
):
    """Get AI buy/hold/sell score with SHAP-style explanation."""
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit=250)
    if len(candles) < 30:
        raise HTTPException(status_code=422, detail="Insufficient data to compute AI score")
    indicators = indicator_service.compute_all(candles)
    score = ai_engine_service.score(indicators, symbol)
    return score


@router.get("/{symbol}/info")
async def get_stock_info(symbol: str, current_user=Depends(get_current_user)):
    """Get company fundamentals and metadata."""
    info = await market_data_service.get_stock_info(symbol)
    if not info:
        raise HTTPException(status_code=404, detail=f"No info found for {symbol}")
    return info


@router.get("/{symbol}/patterns")
async def get_patterns(
    symbol: str,
    timeframe: str = Query("1d"),
    limit: int = Query(250),
    current_user=Depends(get_current_user)
):
    """Get detected candlestick patterns for a symbol."""
    from backend.services.indicators import detect_candlestick_patterns, candles_to_df
    import pandas as pd
    
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit=limit)
    if len(candles) < 10:
        return {"symbol": symbol, "patterns": []}
        
    df = candles_to_df(candles)
    patterns_series = detect_candlestick_patterns(df)
    
    result = []
    for ts, pattern in patterns_series.dropna().items():
        result.append({
            "timestamp": ts.isoformat(),
            "pattern": pattern
        })
        
    return {"symbol": symbol, "timeframe": timeframe, "patterns": result}

