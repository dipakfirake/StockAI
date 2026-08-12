"""Market overview, regime, and India Intelligence API router."""

import asyncio

from fastapi import APIRouter, Depends, Query, HTTPException
from backend.core.logging_config import get_logger
from backend.core.config import settings
from backend.core.cache import cache_get, cache_set
from backend.core.auth import get_current_user
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.signals import signal_engine
from backend.services.india_intelligence import india_intelligence
from backend.data.ingestion.nse_scraper import nse_scraper
from backend.services.advanced_indicators import advanced_indicators, AdvancedIndicators
from backend.services.indicators import candles_to_df
from backend.services.screener import screener_service

router = APIRouter()
logger = get_logger(__name__)

NIFTY_SYMBOL = "^NSEI"
SENSEX_SYMBOL = "^BSESN"


@router.get("/regime")
async def get_market_regime(current_user=Depends(get_current_user)):
    """
    Detect current market regime from Nifty 50 indicators.
    Simple version — uses only technical analysis.
    """
    try:
        candles = await market_data_service.fetch_candles(NIFTY_SYMBOL, "1d", limit=250)
        if len(candles) < 50:
            return {"regime": "UNKNOWN", "confidence": 0.0, "signals": [], "reason": "Insufficient data"}

        indicators = indicator_service.compute_all(candles)
        signals = signal_engine.evaluate(indicators, NIFTY_SYMBOL)

        sig = signals[0] if signals else {}
        sig_type = sig.get("type", "HOLD")
        score = sig.get("score", 0)

        if score >= 4:
            regime, confidence = "BULLISH", 0.85
        elif score >= 2:
            regime, confidence = "BULLISH", 0.65
        elif score <= -4:
            regime, confidence = "BEARISH", 0.85
        elif score <= -2:
            regime, confidence = "BEARISH", 0.65
        else:
            regime, confidence = "SIDEWAYS", 0.55

        return {
            "regime": regime,
            "confidence": confidence,
            "score": score,
            "reason": sig.get("reason", ""),
            "is_market_open": nse_scraper.is_market_open(),
            "indicators": {
                "rsi_14": indicators.get("rsi_14"),
                "ema_50": indicators.get("ema_50"),
                "ema_200": indicators.get("ema_200"),
                "adx_14": indicators.get("adx_14"),
            }
        }
    except Exception as e:
        return {"regime": "UNKNOWN", "confidence": 0.0, "score": 0, "reason": f"Data unavailable: {str(e)}", "is_market_open": False, "indicators": {}}


@router.get("/india-intelligence")
async def get_india_intelligence(current_user=Depends(get_current_user)):
    """
    Comprehensive India market intelligence:
    Combines Nifty trend + India VIX + Market Breadth + Sector Rotation + Events.
    """
    try:
        return await india_intelligence.get_comprehensive_regime()
    except Exception as e:
        return {
            "regime": "Neutral (Fallback)",
            "confidence": 0.5,
            "summary": "Mock fallback due to rate limit/environment issues",
            "vix": None,
            "breadth": None,
            "events": None
        }


@router.get("/vix")
async def get_india_vix(current_user=Depends(get_current_user)):
    """Get India VIX fear gauge."""
    try:
        data = await nse_scraper.fetch_india_vix()
        if data is None:
            return {"vix": None, "sentiment": "UNAVAILABLE", "regime_signal": "neutral",
                    "interpretation": "India VIX data unavailable (market may be closed or yfinance rate-limited)",
                    "timestamp": None}
        return data
    except Exception as e:
        return {"vix": None, "sentiment": "UNAVAILABLE", "regime_signal": "neutral",
                "interpretation": f"Error fetching VIX: {str(e)}", "timestamp": None}


@router.get("/breadth")
async def get_market_breadth(current_user=Depends(get_current_user)):
    """Get market breadth — advance/decline ratio and % stocks above 200 EMA."""
    try:
        data = await nse_scraper.fetch_market_breadth()
        if data is None:
            return {"advancing": 0, "declining": 0, "unchanged": 0, "advance_decline_ratio": 0,
                    "pct_above_200ema": 0, "breadth_signal": "neutral", "sample_size": 0,
                    "error": "Market breadth unavailable"}
        return data
    except Exception as e:
        return {"error": str(e), "breadth_signal": "neutral"}


@router.get("/sectors")
async def get_sector_performance(current_user=Depends(get_current_user)):
    """Get sector rotation heatmap — performance of major NSE sector indices."""
    try:
        sectors = await nse_scraper.fetch_sector_performance()
        return {"sectors": sectors or []}
    except Exception as e:
        return {"sectors": [], "error": str(e)}


@router.get("/fii-dii")
async def get_fii_dii(current_user=Depends(get_current_user)):
    """Get provisional FII/DII flow data from NSE."""
    try:
        data = await nse_scraper.fetch_fii_dii_flows()
        return {"fii_dii": data or {"error": "FII/DII data unavailable (NSE API may be down)"}}
    except Exception as e:
        return {"fii_dii": {"error": str(e)}}


@router.get("/corporate-actions/{symbol}")
async def get_corporate_actions(symbol: str, current_user=Depends(get_current_user)):
    """Get historical dividends and splits for a symbol."""
    data = await nse_scraper.fetch_corporate_actions(symbol)
    return {"corporate_actions": data}


@router.get("/events")
async def get_market_events(current_user=Depends(get_current_user)):
    """Get significant Indian market events for today (RBI, expiry, budget, holidays)."""
    try:
        return {
            "events": india_intelligence.get_today_events(),
            "is_market_open": nse_scraper.is_market_open(),
            "is_trading_day": nse_scraper.is_trading_day(),
        }
    except Exception as e:
        return {"events": [], "is_market_open": False, "is_trading_day": False, "error": str(e)}


@router.get("/indices")
async def get_market_indices(current_user=Depends(get_current_user)):
    """Get exchange-preferred, source-labelled quotes for major Indian indices."""
    cache_key = "market:indices:v2"
    cached = await cache_get(cache_key)
    if cached:
        return cached
    symbols = {
        "Nifty 50": NIFTY_SYMBOL,
        "Sensex": SENSEX_SYMBOL,
        "Nifty Bank": "^NSEBANK",
        "Nifty IT": "^CNXIT",
        "Nifty Midcap 100": "^CRSMID",
        "India VIX": "^INDIAVIX",
    }
    official = await nse_scraper.fetch_index_quotes()

    async def fetch_index(name: str, sym: str):
        official_key = {
            "Nifty 50": "NIFTY 50", 
            "Nifty Bank": "NIFTY BANK",
            "Nifty IT": "NIFTY IT",
            "Nifty Midcap 100": "NIFTY MIDCAP 100",
            "India VIX": "INDIA VIX"
        }.get(name)
        if official_key and official_key in official:
            return {"name": name, "symbol": sym, **official[official_key]}
        try:
            quote = await market_data_service.fetch_quote(sym)
            if quote and quote.get("price", 0) > 0:
                return {"name": name, "symbol": sym, **quote}
        except Exception:
            pass
        return {"name": name, "symbol": sym, "price": None, "error": "Unavailable"}
    indices = await asyncio.gather(*(fetch_index(name, sym) for name, sym in symbols.items()))
    result = {"indices": indices}
    await cache_set(cache_key, result, ttl=settings.CACHE_TTL_INDEX_QUOTE)
    return result


@router.get("/advanced-indicators/{symbol}")
async def get_advanced_indicators(
    symbol: str,
    timeframe: str = Query("1d"),
    current_user=Depends(get_current_user),
):
    """
    Get advanced indicators: SuperTrend, Ichimoku, OBV, CMF,
    Pivot Levels, Support/Resistance, Candlestick Patterns.
    """
    candles = await market_data_service.fetch_candles(symbol.upper(), timeframe, limit=300)
    if len(candles) < 50:
        return {"symbol": symbol, "error": "Insufficient data for advanced indicators"}

    df = candles_to_df(candles)

    # Compute all advanced indicators
    st_df = AdvancedIndicators.compute_supertrend(df)
    ichimoku = AdvancedIndicators.compute_ichimoku(df)
    obv = AdvancedIndicators.compute_obv(df)
    cmf = AdvancedIndicators.compute_cmf(df)
    pivots = AdvancedIndicators.compute_pivot_levels(df)
    sr_levels = AdvancedIndicators.detect_support_resistance(df)
    patterns = AdvancedIndicators.detect_candlestick_patterns(df)
    market_structure = AdvancedIndicators.compute_market_structure(df)
    volatility_squeeze = AdvancedIndicators.compute_volatility_squeeze(df)

    supertrend_latest = None
    if st_df is not None and not st_df.empty and len(st_df) > 0:
        try:
            row = st_df.iloc[-1]
            supertrend_latest = {
                "value": round(float(row.iloc[0]), 4) if hasattr(row, 'iloc') else None,
                "direction": "bullish" if (row.iloc[1] == 1 if hasattr(row, 'iloc') else False) else "bearish",
            }
        except Exception:
            pass

    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "supertrend": supertrend_latest,
        "ichimoku": ichimoku,
        "obv": round(obv, 0) if obv else None,
        "cmf": cmf,
        "pivot_levels": pivots,
        "support_resistance": sr_levels,
        "candlestick_patterns": patterns,
        "market_structure": market_structure,
        "volatility_squeeze": volatility_squeeze,
    }

@router.get("/heatmap")
async def get_market_heatmap(current_user=Depends(get_current_user)):
    """Get Nifty 50 heatmap data."""
    import asyncio
    
    # We will fetch for a subset of major components to keep it fast, or all if cached
    top_symbols = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
        "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
        "KOTAKBANK.NS", "SUNPHARMA.NS", "TITAN.NS", "M&M.NS", "ULTRACEMCO.NS",
        "TATAMOTORS.NS", "NTPC.NS", "TATASTEEL.NS", "POWERGRID.NS", "BAJAJFINSV.NS"
    ]
    
    async def _fetch(sym):
        try:
            return await market_data_service.fetch_quote(sym)
        except Exception:
            return None
            
    tasks = [_fetch(sym) for sym in top_symbols]
    results = await asyncio.gather(*tasks)
    
    heatmap = [r for r in results if r is not None and r.get("price")]
    return {"heatmap": heatmap}

@router.get("/options/{symbol}")
async def get_options_chain(
    symbol: str,
    current_user=Depends(get_current_user)
):
    """Dynamically generate realistic options chain using Black-Scholes."""
    from backend.services.options_engine import options_engine
    
    try:
        quote = await market_data_service.fetch_quote(symbol.upper())
        if not quote or "price" not in quote:
            raise HTTPException(status_code=404, detail="Symbol not found")
            
        spot_price = quote["price"]
        
        # Get VIX to inform Implied Volatility
        from backend.data.ingestion.nse_scraper import nse_scraper
        vix_data = await nse_scraper.fetch_india_vix()
        current_vix = vix_data["vix"] if vix_data else 15.0
        
        chain_data = options_engine.generate_chain(symbol.upper(), spot_price, current_vix)
        return chain_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate options chain for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch options data")

@router.get("/screener")
async def get_swing_trade_screener(
    sector: str = Query(None, description="Optional sector or universe to screen (e.g. NIFTY50)"),
    current_user=Depends(get_current_user)
):
    """
    Run the AI Swing Trade Screener across a predefined universe.
    Combines Technicals, Fundamentals, and NLP News Sentiment to find trade setups.
    """
    try:
        # We can implement a caching layer here if this is hit frequently
        cache_key = f"screener_results_{sector or 'default'}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        results = await screener_service.run_screener()
        
        # Cache for 1 hour to prevent API rate limits
        await cache_set(cache_key, results, ttl=3600)
        return results
    except Exception as e:
        logger.error(f"Screener failed: {e}")
        raise HTTPException(status_code=500, detail="Screener execution failed")

@router.get("/bulk-screener")
async def get_bulk_screener(current_user=Depends(get_current_user)):
    """
    Returns the massive pre-calculated AI Screener results for the NIFTY 50/500.
    This data is calculated continuously in the background by Celery workers to prevent timeouts.
    """
    try:
        # Fetch the pre-computed massive payload from Redis
        cached = await cache_get("screener:bulk:latest")
        if not cached:
            # If celery hasn't finished its first run, return a 202 Accepted status
            return {"status": "processing", "message": "The Master AI is currently crunching the entire market in the background. Please check back in a few minutes.", "results": []}
            
        return {"status": "ready", "results": cached}
    except Exception as e:
        logger.error(f"Bulk Screener fetch failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch bulk screener data")

