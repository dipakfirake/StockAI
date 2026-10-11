"""Stocks API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.auth import get_current_user
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.signals import signal_engine
from backend.services.ai_engine import ai_engine_service
from backend.services.risk_analysis import analyse_risk

router = APIRouter()


@router.get("/{symbol}/insight")
async def get_stock_insight(
    symbol: str,
    timeframe: str = Query("1d"),
    anchor_date: str | None = Query(None, description="ISO date to anchor VWAP calculation"),
    current_user=Depends(get_current_user),
):
    """One live, UI-ready view of price action, risk, technicals and recent news."""
    from backend.data.ingestion.news_scraper import fetch_stock_news
    from backend.services.screener import screener_service

    # Fetch optimal 500 candles (~2 years of daily data), enough for SMA200 and all indicators in 1 fast call
    fetch_limit = 500

    import asyncio
    import math

    results = await asyncio.gather(
        market_data_service.fetch_quote(symbol),
        market_data_service.fetch_candles(symbol, timeframe, limit=fetch_limit),
        fetch_stock_news(symbol),
        screener_service._analyze_symbol(symbol),
        market_data_service.fetch_corporate_events(symbol),
        return_exceptions=True
    )
    quote = results[0] if not isinstance(results[0], Exception) else None
    candles = results[1] if (not isinstance(results[1], Exception) and isinstance(results[1], list)) else []
    news = results[2] if (not isinstance(results[2], Exception) and isinstance(results[2], list)) else []
    swing_trade = results[3] if (not isinstance(results[3], Exception) and isinstance(results[3], dict)) else {}
    events = results[4] if (not isinstance(results[4], Exception) and isinstance(results[4], dict)) else {}

    if not quote or not isinstance(quote, dict):
        raise HTTPException(status_code=404, detail=f"No quote data found for {symbol}")

    price = float(quote.get("price", 0.0))

    # Compute dynamic 52W High & Low from historical candles
    if candles and price > 0:
        year_candles = candles[-252:]
        highs = []
        lows = []
        for c in year_candles:
            try:
                h = float(c.get("high", price))
                l = float(c.get("low", price))
                if math.isfinite(h) and h > 0: highs.append(h)
                if math.isfinite(l) and l > 0: lows.append(l)
            except (ValueError, TypeError):
                continue
        quote["52w_high"] = round(max(highs), 2) if highs else price
        quote["52w_low"] = round(min(lows), 2) if lows else price
    else:
        quote["52w_high"] = price
        quote["52w_low"] = price

    # Populate Market Cap from swing_trade or stock info
    if swing_trade and swing_trade.get("market_cap"):
        quote["market_cap"] = swing_trade["market_cap"]
    elif not quote.get("market_cap"):
        try:
            info = await market_data_service.get_stock_info(symbol)
            if info and info.get("market_cap"):
                quote["market_cap"] = info["market_cap"]
        except Exception:
            pass

    indicators = indicator_service.compute_all(candles) if len(candles) >= 30 else {}
    series_candles = indicator_service.compute_for_candles_series(candles)
    
    if anchor_date and len(series_candles) > 0:
        try:
            from backend.services.indicators import calculate_anchored_vwap, candles_to_df
            import pandas as pd
            pd.to_datetime(anchor_date)
            df = candles_to_df(series_candles)
            avwap_series = calculate_anchored_vwap(df, anchor_date)
            for i, c in enumerate(series_candles):
                ts = pd.to_datetime(c["timestamp"])
                if ts in avwap_series.index and not pd.isna(avwap_series[ts]):
                    c["anchored_vwap"] = round(float(avwap_series[ts]), 4)
                else:
                    c["anchored_vwap"] = None
        except Exception as e:
            logger.warning(f"Anchored VWAP calculation error for {symbol}: {e}")

    patterns = []
    if len(series_candles) >= 10:
        from backend.services.indicators import candles_to_df, detect_candlestick_patterns
        try:
            patterns = [
                {"timestamp": timestamp.isoformat(), "pattern": pattern}
                for timestamp, pattern in detect_candlestick_patterns(candles_to_df(series_candles)).dropna().items()
            ]
        except Exception:
            patterns = []
    return {
        "symbol": quote["symbol"],
        "timeframe": timeframe,
        "as_of": quote["timestamp"],
        "quote": quote,
        "swing_trade": swing_trade,
        "candles": series_candles,
        "risk": analyse_risk(series_candles),
        "indicators": indicators,
        "signals": signal_engine.evaluate(indicators, quote["symbol"], timeframe) if indicators else [],
        "ai_score": ai_engine_service.score(indicators, quote["symbol"]) if indicators else None,
        "patterns": patterns,
        "events": events,
        "news": news,
        "data_note": "Prices are provider-delayed when the exchange or upstream source does not supply a live tick.",
    }


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
    if not quote.get("market_cap") or quote.get("market_cap") == 0:
        try:
            info = await asyncio.wait_for(market_data_service.get_stock_info(symbol), timeout=15.0)
            if info and info.get("market_cap"):
                quote["market_cap"] = info["market_cap"]
        except Exception:
            pass
    return quote


@router.get("/{symbol}/candles")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1d", description="Timeframe: 1m, 5m, 15m, 30m, 1h, 1d, 1w"),
    limit: int = Query(200, ge=1, le=2000),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    anchor_date: str | None = Query(None, description="ISO date to anchor VWAP calculation"),
    current_user=Depends(get_current_user),
):
    """Get OHLCV candlestick data with indicator series."""
    candles = await market_data_service.fetch_candles(symbol, timeframe, limit, start_date, end_date)
    series_candles = indicator_service.compute_for_candles_series(candles)
    
    if anchor_date and len(series_candles) > 0:
        from backend.services.indicators import calculate_anchored_vwap, candles_to_df
        import pandas as pd
        df = candles_to_df(series_candles)
        avwap_series = calculate_anchored_vwap(df, anchor_date)
        
        # Inject anchored VWAP back into the result
        for i, c in enumerate(series_candles):
            ts = pd.to_datetime(c["timestamp"])
            if ts in avwap_series.index and not pd.isna(avwap_series[ts]):
                c["anchored_vwap"] = round(float(avwap_series[ts]), 4)
            else:
                c["anchored_vwap"] = None

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
    signals = signal_engine.evaluate(indicators, symbol, timeframe)
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


@router.get("/{symbol}/volume-profile")
async def get_volume_profile(
    symbol: str,
    timeframe: str = Query("1d"),
    limit: int = Query(250),
    num_bins: int = Query(50),
    current_user=Depends(get_current_user),
):
    """Compute volume profile (POC, VAH, VAL) for a symbol."""
    from backend.services.volume_profile import calculate_volume_profile
    from backend.services.indicators import candles_to_df

    candles = await market_data_service.fetch_candles(symbol, timeframe, limit=limit)
    if len(candles) < 10:
        raise HTTPException(status_code=422, detail="Insufficient data for volume profile")

    df = candles_to_df(candles)
    profile = calculate_volume_profile(df, num_bins=num_bins)
    return {"symbol": symbol, "timeframe": timeframe, **profile}
