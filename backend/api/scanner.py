"""Scanner API router — Phase 6."""

from fastapi import APIRouter, Depends, HTTPException
from backend.core.auth import get_current_user
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.data.ingestion.yfinance_ingestion import NSE_NIFTY50_SYMBOLS

router = APIRouter()

# Stub mapping of sectors to symbols for MVP
SECTOR_MAP = {
    "Nifty Bank": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS"],
    "Nifty IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS"],
    "Nifty Auto": ["TATAMOTORS.NS", "M&M.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "TVSMOTOR.NS"],
}

async def evaluate_rule(symbol: str, rule: str) -> tuple[bool, str]:
    """Helper to evaluate a rule on a single symbol."""
    try:
        candles = await market_data_service.fetch_candles(symbol, "1d", limit=50)
        if len(candles) < 30:
            return False, ""
            
        indicators = indicator_service.compute_all(candles)
        
        if rule == "RSI_OVERSOLD":
            rsi = indicators.get("rsi_14")
            if rsi and rsi < 30:
                return True, f"RSI is {rsi}"
        
        elif rule == "RSI_OVERBOUGHT":
            rsi = indicators.get("rsi_14")
            if rsi and rsi > 70:
                return True, f"RSI is {rsi}"
                
        elif rule == "MACD_BULLISH":
            macd = indicators.get("macd")
            if macd and macd.get("histogram") and macd["histogram"] > 0:
                return True, f"MACD Hist is positive ({macd['histogram']})"
                
        elif rule == "EMA_BULLISH_CROSS":
            ema9 = indicators.get("ema_9")
            ema21 = indicators.get("ema_21")
            if ema9 and ema21 and ema9 > ema21:
                return True, f"EMA9 ({ema9:.2f}) > EMA21 ({ema21:.2f})"
                
        elif rule == "SUPERTREND_BUY":
            st = indicators.get("supertrend", {})
            if st.get("direction") == "up":
                return True, f"SuperTrend is Bullish (Trend: up)"
                
        elif rule == "BB_SQUEEZE":
            bb = indicators.get("bb", {})
            upper = bb.get("upper")
            lower = bb.get("lower")
            if upper and lower:
                bandwidth = (upper - lower) / lower * 100
                if bandwidth < 5.0:  # 5% threshold
                    return True, f"BB Bandwidth squeezed to {bandwidth:.2f}%"

        return False, ""
    except Exception:
        return False, ""


@router.get("/nifty50")
async def scan_nifty50(
    rule: str = "RSI_OVERSOLD",
    current_user=Depends(get_current_user)
):
    """
    Scan Nifty 50 stocks for a specific rule match.
    """
    matches = []
    scan_list = NSE_NIFTY50_SYMBOLS
    
    for symbol in scan_list:
        matched, detail = await evaluate_rule(symbol, rule)
        if matched:
            matches.append({
                "symbol": symbol,
                "rule": rule,
                "detail": detail
            })

    return {"rule": rule, "matches": matches, "total_scanned": len(scan_list)}


@router.get("/sector/{sector_name}")
async def scan_sector(
    sector_name: str,
    rule: str = "RSI_OVERSOLD",
    current_user=Depends(get_current_user)
):
    """
    Scan a specific sector for a rule match.
    Supported sectors: Nifty Bank, Nifty IT, Nifty Auto
    """
    if sector_name not in SECTOR_MAP:
        raise HTTPException(status_code=400, detail="Unsupported sector")

    matches = []
    scan_list = SECTOR_MAP[sector_name]
    
    for symbol in scan_list:
        matched, detail = await evaluate_rule(symbol, rule)
        if matched:
            matches.append({
                "symbol": symbol,
                "rule": rule,
                "detail": detail
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

@router.post("/custom")
async def scan_custom(
    request: CustomScanRequest,
    current_user=Depends(get_current_user)
):
    """
    Scan a universe using custom rules.
    """
    scan_list = NSE_NIFTY50_SYMBOLS
    if request.universe in SECTOR_MAP:
        scan_list = SECTOR_MAP[request.universe]

    matches = []
    for symbol in scan_list:
        try:
            candles = await market_data_service.fetch_candles(symbol, request.timeframe, limit=50)
            if len(candles) < 30:
                continue
            
            indicators = indicator_service.compute_all(candles)
            if not indicators:
                continue
            
            # Extract nested values like macd.macd or bb.upper if needed, but for MVP keep it flat
            flat_inds = {}
            for k, v in indicators.items():
                if isinstance(v, dict):
                    for sub_k, sub_v in v.items():
                        flat_inds[f"{k}_{sub_k}"] = sub_v
                else:
                    flat_inds[k] = v

            matched_all = True
            details = []
            
            for cond in request.conditions:
                ind_val = flat_inds.get(cond.indicator)
                if ind_val is None:
                    matched_all = False
                    break
                
                try:
                    if cond.operator == ">" and float(ind_val) > float(cond.value):
                        details.append(f"{cond.indicator} ({ind_val}) > {cond.value}")
                    elif cond.operator == "<" and float(ind_val) < float(cond.value):
                        details.append(f"{cond.indicator} ({ind_val}) < {cond.value}")
                    elif cond.operator == "==" and str(ind_val) == str(cond.value):
                        details.append(f"{cond.indicator} ({ind_val}) == {cond.value}")
                    else:
                        matched_all = False
                        break
                except ValueError:
                    matched_all = False
                    break
                    
            if matched_all:
                matches.append({
                    "symbol": symbol,
                    "detail": " AND ".join(details)
                })
        except Exception:
            continue
            
    return {"universe": request.universe, "matches": matches, "total_scanned": len(scan_list)}
