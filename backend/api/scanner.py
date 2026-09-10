"""Scanner API router — Phase 6."""

from fastapi import APIRouter, Depends, HTTPException
from backend.core.auth import get_current_user
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS

router = APIRouter()

import asyncio

# Comprehensive mapping of NSE sectors to liquid constituent symbols
SECTOR_MAP = {
    "Nifty Bank": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS"],
    "Nifty IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS"],
    "Nifty Auto": ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "TVSMOTOR.NS", "BHARATFORG.NS"],
    "Nifty FMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS", "DABUR.NS", "GODREJCP.NS", "MARICO.NS"],
    "Nifty Metal": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "JINDALSTEL.NS", "NMDC.NS", "SAIL.NS", "NATIONALUM.NS"],
    "Nifty Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS", "APOLLOHOSP.NS", "AUROPHARMA.NS", "TORNTPHARM.NS"],
    "Nifty Realty": ["DLF.NS", "GODREJPROP.NS", "MACROTECH.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS", "BRIGADE.NS", "PRESTIGE.NS"],
    "Nifty Energy": ["RELIANCE.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "BPCL.NS", "IOC.NS", "COALINDIA.NS", "TATAPOWER.NS", "ADANIGREEN.NS"],
}

_SCANNER_SEMAPHORE = asyncio.Semaphore(8)

async def evaluate_rule(symbol: str, rule: str) -> tuple[bool, str]:
    """Helper to evaluate a rule on a single symbol with concurrency throttling."""
    async with _SCANNER_SEMAPHORE:
        try:
            candles = await market_data_service.fetch_candles(symbol, "1d", limit=60)
            if len(candles) < 30:
                return False, ""
                
            indicators = indicator_service.compute_all(candles)
            price = indicators.get("close", 0.0)
            
            if rule == "EMA_BULLISH_CROSS":
                ema9 = indicators.get("ema_9")
                ema21 = indicators.get("ema_21")
                if ema9 and ema21 and ema9 > ema21:
                    return True, f"EMA9 ({ema9:.2f}) > EMA21 ({ema21:.2f})"

            elif rule == "EMA_BEARISH_CROSS":
                ema9 = indicators.get("ema_9")
                ema21 = indicators.get("ema_21")
                if ema9 and ema21 and ema9 < ema21:
                    return True, f"EMA9 ({ema9:.2f}) < EMA21 ({ema21:.2f})"
            
            elif rule == "MACD_BULLISH":
                macd = indicators.get("macd")
                if macd and macd.get("histogram") and macd["histogram"] > 0:
                    return True, f"MACD Hist positive (+{macd['histogram']:.2f})"
                    
            elif rule == "SUPERTREND_BUY":
                st = indicators.get("supertrend", {})
                if st.get("direction") == "up":
                    return True, "SuperTrend is Bullish (Trend: UP)"

            elif rule == "SUPERTREND_SELL":
                st = indicators.get("supertrend", {})
                if st.get("direction") == "down":
                    return True, "SuperTrend is Bearish (Trend: DOWN)"

            elif rule == "RSI_BULLISH_MOMENTUM":
                rsi = indicators.get("rsi_14")
                if rsi and 50 <= rsi <= 70:
                    return True, f"Bullish Momentum Zone (RSI {rsi:.1f})"

            elif rule == "PRICE_ABOVE_200SMA":
                sma200 = indicators.get("sma_200")
                if price and sma200 and price > sma200:
                    return True, f"Price (₹{price:.2f}) above 200 SMA (₹{sma200:.2f})"

            elif rule == "RSI_OVERSOLD":
                rsi = indicators.get("rsi_14")
                if rsi and rsi < 30:
                    return True, f"Oversold Reversal (RSI {rsi:.1f})"
            
            elif rule == "RSI_OVERBOUGHT":
                rsi = indicators.get("rsi_14")
                if rsi and rsi > 70:
                    return True, f"Overbought Breakout (RSI {rsi:.1f})"
                    
            elif rule == "BB_SQUEEZE":
                bb = indicators.get("bb", {})
                upper = bb.get("upper")
                lower = bb.get("lower")
                if upper and lower and lower > 0:
                    bandwidth = (upper - lower) / lower * 100
                    if bandwidth < 8.0:
                        return True, f"BB Bandwidth Squeezed ({bandwidth:.2f}%)"

            return False, ""
        except Exception:
            return False, ""


@router.get("/nifty50")
async def scan_nifty50(
    rule: str = "EMA_BULLISH_CROSS",
    current_user=Depends(get_current_user)
):
    """
    Scan Nifty 50 stocks concurrently for a specific rule match.
    """
    scan_list = NSE_NIFTY50_SYMBOLS
    tasks = [evaluate_rule(sym, rule) for sym in scan_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    matches = []
    for sym, res in zip(scan_list, results):
        if isinstance(res, tuple) and res[0]:
            matches.append({
                "symbol": sym,
                "rule": rule,
                "detail": res[1]
            })

    return {"rule": rule, "matches": matches, "total_scanned": len(scan_list)}


@router.get("/sector/{sector_name}")
async def scan_sector(
    sector_name: str,
    rule: str = "EMA_BULLISH_CROSS",
    current_user=Depends(get_current_user)
):
    """
    Scan a specific sector concurrently for a rule match.
    """
    if sector_name not in SECTOR_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported sector. Available: {list(SECTOR_MAP.keys())}")

    scan_list = SECTOR_MAP[sector_name]
    tasks = [evaluate_rule(sym, rule) for sym in scan_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    matches = []
    for sym, res in zip(scan_list, results):
        if isinstance(res, tuple) and res[0]:
            matches.append({
                "symbol": sym,
                "rule": rule,
                "detail": res[1]
            })

    return {"rule": rule, "sector": sector_name, "matches": matches, "total_scanned": len(scan_list)}


from pydantic import BaseModel
from typing import List, Union

class ScanCondition(BaseModel):
    indicator: str
    operator: str
    value: Union[float, str]

class CustomScanRequest(BaseModel):
    universe: str
    timeframe: str = "1d"
    conditions: List[ScanCondition]

async def _eval_custom_symbol(symbol: str, timeframe: str, conditions: List[ScanCondition]):
    try:
        candles = await market_data_service.fetch_candles(symbol, timeframe, limit=50)
        if len(candles) < 30:
            return None
        
        indicators = indicator_service.compute_all(candles)
        if not indicators:
            return None
        
        flat_inds = {}
        for k, v in indicators.items():
            if isinstance(v, dict):
                for sub_k, sub_v in v.items():
                    flat_inds[f"{k}_{sub_k}"] = sub_v
            else:
                flat_inds[k] = v

        matched_all = True
        details = []
        
        for cond in conditions:
            ind_val = flat_inds.get(cond.indicator)
            if ind_val is None:
                matched_all = False
                break
            
            try:
                if cond.operator == ">" and float(ind_val) > float(cond.value):
                    details.append(f"{cond.indicator} ({ind_val:.2f}) > {cond.value}")
                elif cond.operator == "<" and float(ind_val) < float(cond.value):
                    details.append(f"{cond.indicator} ({ind_val:.2f}) < {cond.value}")
                elif cond.operator == "==" and str(ind_val) == str(cond.value):
                    details.append(f"{cond.indicator} ({ind_val}) == {cond.value}")
                else:
                    matched_all = False
                    break
            except (ValueError, TypeError):
                matched_all = False
                break
                
        if matched_all:
            return {
                "symbol": symbol,
                "detail": " AND ".join(details)
            }
        return None
    except Exception:
        return None

@router.post("/custom")
async def scan_custom(
    request: CustomScanRequest,
    current_user=Depends(get_current_user)
):
    """
    Scan a universe using custom rules concurrently.
    """
    scan_list = NSE_NIFTY50_SYMBOLS
    if request.universe in SECTOR_MAP:
        scan_list = SECTOR_MAP[request.universe]

    tasks = [_eval_custom_symbol(sym, request.timeframe, request.conditions) for sym in scan_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    matches = [r for r in results if r is not None and not isinstance(r, Exception)]
            
    return {"universe": request.universe, "matches": matches, "total_scanned": len(scan_list)}

from backend.services.institutional_hunter import smc_engine

@router.get("/institutional")
async def get_institutional_zones(
    current_user=Depends(get_current_user)
):
    """
    Returns the daily pre-calculated Institutional Liquidity Zones (FVG / SMC).
    If the watchlist is empty (e.g. system just booted), it calculates it on-the-fly.
    """
    zones = smc_engine.get_watchlist()
    if not zones:
        # Generate on the fly for the top liquid stocks
        liquid_universe = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "SBIN.NS"]
        zones = await smc_engine.generate_daily_watchlist(liquid_universe)
        
    return {"status": "success", "zones": zones}
