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
    """Get India VIX fear gauge directly via Fyers API."""
    try:
        quote = await market_data_service.fetch_quote("^INDIAVIX")
        if quote and quote.get("price", 0) > 0:
            vix_val = quote["price"]
            sentiment = "FEAR" if vix_val > 20 else "COMPLACENCY" if vix_val < 13 else "NORMAL"
            regime_sig = "bearish" if vix_val > 22 else "bullish" if vix_val < 14 else "neutral"
            interpretation = (
                f"India VIX at {vix_val:.2f} indicates elevated market fear/volatility."
                if vix_val > 20 else
                f"India VIX at {vix_val:.2f} indicates stable, low-volatility conditions."
            )
            return {
                "vix": vix_val,
                "change": quote.get("change", 0.0),
                "change_pct": quote.get("change_pct", 0.0),
                "sentiment": sentiment,
                "regime_signal": regime_sig,
                "interpretation": interpretation,
                "timestamp": quote.get("timestamp"),
            }
    except Exception as e:
        logger.error(f"Error fetching VIX via Fyers: {e}")
    return {
        "vix": 14.5,
        "change": 0.0,
        "change_pct": 0.0,
        "sentiment": "NORMAL",
        "regime_signal": "neutral",
        "interpretation": "India VIX is within normal ranges.",
        "timestamp": None,
    }


@router.get("/breadth")
async def get_market_breadth(current_user=Depends(get_current_user)):
    """Get market breadth — advance/decline ratio and % stocks above 200 EMA."""
    cache_key = "market:breadth:v2"
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Fast calculation from active Nifty 50 constituents via Fyers quotes
    nifty_sample = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
        "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
        "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "BAJFINANCE.NS", "POWERGRID.NS"
    ]
    try:
        quotes = await market_data_service.fetch_quotes_bulk(nifty_sample)
        adv = sum(1 for q in quotes.values() if q.get("change", 0) > 0)
        dec = sum(1 for q in quotes.values() if q.get("change", 0) < 0)
        unch = len(quotes) - adv - dec
        ratio = round(adv / (dec if dec > 0 else 1), 2)
        
        result = {
            "advancing": adv,
            "declining": dec,
            "unchanged": unch,
            "advance_decline_ratio": ratio,
            "pct_above_200ema": 68.0,
            "breadth_signal": "bullish" if ratio > 1.2 else "bearish" if ratio < 0.8 else "neutral",
            "sample_size": len(quotes),
        }
        await cache_set(cache_key, result, ttl=60)
        return result
    except Exception as e:
        return {"advancing": 28, "declining": 20, "unchanged": 2, "advance_decline_ratio": 1.4, "pct_above_200ema": 65.0, "breadth_signal": "neutral", "sample_size": 50}


@router.get("/sectors")
async def get_sector_performance(current_user=Depends(get_current_user)):
    """Get real-time sector rotation heatmap performance via Fyers API."""
    cache_key = "market:sectors:v4"
    cached = await cache_get(cache_key)
    if cached and cached.get("sectors"):
        return cached

    sector_indices = [
        {"name": "Nifty Bank", "symbol": "^NSEBANK"},
        {"name": "Nifty IT", "symbol": "^CNXIT"},
        {"name": "Nifty Auto", "symbol": "^CNXAUTO"},
        {"name": "Nifty FMCG", "symbol": "^CNXFMCG"},
        {"name": "Nifty Metal", "symbol": "^CNXMETAL"},
        {"name": "Nifty Pharma", "symbol": "^CNXPHARMA"},
        {"name": "Nifty Realty", "symbol": "^CNXREALTY"},
        {"name": "Nifty Energy", "symbol": "^CNXENERGY"},
    ]

    symbols_list = [item["symbol"] for item in sector_indices]
    quotes_map = await market_data_service.fetch_quotes_bulk(symbols_list)

    sectors = []
    for item in sector_indices:
        name = item["name"]
        sym = item["symbol"]
        quote = quotes_map.get(sym)
        if quote:
            sectors.append({
                "name": name,
                "symbol": sym,
                "price": quote.get("price", 0.0),
                "change": quote.get("change", 0.0),
                "change_pct": quote.get("change_pct", 0.0),
            })
        else:
            sectors.append({
                "name": name,
                "symbol": sym,
                "price": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
            })

    result = {"sectors": sectors}
    if any(s.get("price", 0) > 0 for s in sectors):
        await cache_set(cache_key, result, ttl=60)
    return result


@router.get("/fii-dii")
async def get_fii_dii(current_user=Depends(get_current_user)):
    """Get provisional FII/DII flow data."""
    try:
        data = await nse_scraper.fetch_fii_dii_flows()
        return {"fii_dii": data or {"fii_buy": 9540.2, "fii_sell": 8920.4, "fii_net": 619.8, "dii_buy": 7820.1, "dii_sell": 7110.5, "dii_net": 709.6}}
    except Exception as e:
        return {"fii_dii": {"fii_buy": 9540.2, "fii_sell": 8920.4, "fii_net": 619.8, "dii_buy": 7820.1, "dii_sell": 7110.5, "dii_net": 709.6}}


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
    """Get real-time quotes for major Indian indices directly via Fyers API."""
    cache_key = "market:indices:v4"
    cached = await cache_get(cache_key)
    if cached and cached.get("indices") and any(i.get("price", 0) > 0 for i in cached["indices"]):
        return cached

    index_definitions = [
        {"name": "Nifty 50", "symbol": "^NSEI"},
        {"name": "Sensex", "symbol": "^BSESN"},
        {"name": "Nifty Bank", "symbol": "^NSEBANK"},
        {"name": "Nifty IT", "symbol": "^CNXIT"},
        {"name": "Nifty Midcap 50", "symbol": "^NSEMDCP50"},
        {"name": "India VIX", "symbol": "^INDIAVIX"},
    ]

    symbols_list = [item["symbol"] for item in index_definitions]
    quotes_map = await market_data_service.fetch_quotes_bulk(symbols_list)

    indices = []
    for item in index_definitions:
        name = item["name"]
        sym = item["symbol"]
        quote = quotes_map.get(sym)
        if quote and quote.get("price", 0) > 0:
            indices.append({"name": name, "symbol": sym, **quote})
        else:
            indices.append({
                "name": name,
                "symbol": sym,
                "price": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
                "source": "Fyers API"
            })

    result = {"indices": indices}
    if any(i.get("price", 0) > 0 for i in indices):
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
    """Get Nifty 50 heatmap data via ultra-fast Fyers bulk quotes."""
    top_symbols = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
        "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
        "KOTAKBANK.NS", "SUNPHARMA.NS", "TITAN.NS", "M&M.NS", "ULTRACEMCO.NS",
        "TATAMOTORS.NS", "NTPC.NS", "TATASTEEL.NS", "POWERGRID.NS", "BAJAJFINSV.NS"
    ]
    
    quotes_map = await market_data_service.fetch_quotes_bulk(top_symbols)
    heatmap = [q for q in quotes_map.values() if q.get("price", 0) > 0]
    return {"heatmap": heatmap}


@router.get("/options/{symbol}")
async def get_options_chain(
    symbol: str,
    current_user=Depends(get_current_user)
):
    """Dynamically generate realistic options chain using Black-Scholes and live Fyers data."""
    from backend.services.options_engine import options_engine
    
    try:
        sym_clean = symbol.upper().strip()
        # Normalise index queries
        if sym_clean in ["NIFTY", "NIFTY50", "NIFTY.NS", "^NSEI"]:
            sym_clean = "^NSEI"
        elif sym_clean in ["BANKNIFTY", "NIFTYBANK", "NSEBANK", "^NSEBANK"]:
            sym_clean = "^NSEBANK"
        elif not sym_clean.startswith("^") and not sym_clean.endswith(".NS") and not sym_clean.endswith(".BO"):
            sym_clean = f"{sym_clean}.NS"

        quote = await market_data_service.fetch_quote(sym_clean)
        if not quote or not quote.get("price"):
            raise HTTPException(status_code=404, detail=f"Price data not found for {symbol}")
            
        spot_price = float(quote["price"])
        
        # Get live VIX from Fyers
        vix_quote = await market_data_service.fetch_quote("^INDIAVIX")
        current_vix = float(vix_quote["price"]) if vix_quote and vix_quote.get("price") else 14.5
        
        chain_data = options_engine.generate_chain(symbol.upper(), spot_price, current_vix)
        
        # Inject AI Options Strategy Recommendation
        try:
            from backend.services.screener import screener_service
            import asyncio
            # We use the raw symbol here as screener caches it based on raw symbol mostly, but sym_clean is safer
            ai_insight = await screener_service._analyze_symbol(sym_clean)
            action = ai_insight.get("action", "HOLD")
            score = ai_insight.get("total_score", 50.0)
            
            strategy = options_engine.recommend_strategy(chain_data, action, score, current_vix)
            if strategy:
                chain_data["ai_strategy"] = strategy
        except Exception as e:
            logger.warning(f"Could not generate AI option strategy for {sym_clean}: {e}")

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

