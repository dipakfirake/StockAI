"""AI Engine API router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from backend.core.auth import get_current_user, require_pro_tier
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.ai_engine import ai_engine_service

router = APIRouter()


@router.get("/score/{symbol}")
async def get_ai_score(
    symbol: str,
    timeframe: str = Query("1d"),
    current_user=Depends(require_pro_tier),
):
    """Get AI buy/hold/sell score with SHAP-style explanation."""
    candles = await market_data_service.fetch_candles(symbol.upper(), timeframe, limit=250)
    if len(candles) < 30:
        raise HTTPException(status_code=422, detail="Insufficient data for AI scoring")
    indicators = indicator_service.compute_all(candles)
    return ai_engine_service.score(indicators, symbol.upper())


@router.get("/scan")
async def scan_stocks(
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    timeframe: str = Query("1d"),
    current_user=Depends(require_pro_tier),
):
    """Scan multiple stocks and return AI scores for each."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(symbol_list) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 symbols per scan")

    results = []
    for sym in symbol_list:
        try:
            candles = await market_data_service.fetch_candles(sym, timeframe, limit=250)
            if len(candles) >= 30:
                indicators = indicator_service.compute_all(candles)
                score = ai_engine_service.score(indicators, sym)
                results.append(score)
        except Exception:
            results.append({"symbol": sym, "score": "ERROR", "confidence": 0})

    return {"scan_results": results, "total": len(results)}


from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    symbol: str = None

@router.post("/chat")
async def ai_chat(
    request: ChatRequest,
    current_user=Depends(require_pro_tier)
):
    """Simple AI chat assistant for market insights."""
    msg = request.message.lower()
    symbol = request.symbol.upper() if request.symbol else None
    
    response = "I am your AI Stock Assistant. I can analyze technicals and give trading insights."
    
    if any(k in msg for k in ["market", "nifty", "regime", "up", "down", "why", "today", "breadth"]):
        try:
            from backend.services.india_intelligence import india_intelligence
            regime = await india_intelligence.get_comprehensive_regime()
            
            phase = regime.get('regime', 'UNKNOWN')
            conf = int(regime.get('confidence', 0) * 100)
            breadth = regime.get('detail', {}).get('market_breadth', {}).get('breadth_signal', 'neutral')
            
            response = f"Currently, the broader market is in a **{phase}** phase (Confidence: {conf}%). "
            response += f"Market breadth is **{breadth}**. "
            
            if "why" in msg or "up" in msg or "down" in msg:
                signals = regime.get("signals", [])
                if signals:
                    response += "\n\nKey drivers today:\n"
                    for s in signals:
                        response += f"- **{s['source']}** ({s['direction']}): {s['detail']}\n"
        except Exception as e:
            response = "I'm currently unable to fetch the real-time market regime data. Please try again in a moment."
    elif "buy" in msg or "sell" in msg or "score" in msg or "analyze" in msg or "view" in msg or "should" in msg:
        import re
        if not symbol:
            clean_msg = re.sub(r'\b(should|i|buy|buying|or|not|sell|selling|analyze|score|for|view|the|stock|is|are|best|good|now|days|today|tomorrow|what|about|think|how|does|look|of|a|an|it|to)\b', '', msg.replace("?", "")).strip()
            if clean_msg:
                search_results = await market_data_service.search_stocks(clean_msg)
                if search_results:
                    top_match = search_results[0]['symbol']
                    symbol = top_match if "." in top_match or top_match.startswith("^") else f"{top_match}.NS"
        
        if symbol:
            try:
                candles = await market_data_service.fetch_candles(symbol, "1d", limit=250)
                if len(candles) >= 30:
                    indicators = indicator_service.compute_all(candles)
                    score = ai_engine_service.score(indicators, symbol)
                    
                    from backend.services.advanced_indicators import AdvancedIndicators
                    from backend.services.indicators import candles_to_df
                    df = candles_to_df(candles)
                    sr = AdvancedIndicators.detect_support_resistance(df)
                    
                    latest_close = candles[-1]["close"]
                    
                    response = f"Based on real-time technicals, my analysis for **{symbol}** indicates a **{score['score']} ({int(score['confidence']*100)}% confidence)**. The stock is currently trading at ₹{latest_close:,.2f}. "
                    if score['explanation']:
                        top_feature = score['explanation'][0]
                        response += f"The primary driver is the {top_feature['feature']} which is {top_feature['direction']}. "
                    
                    if sr['support'] and sr['resistance']:
                        response += f"Immediate support lies around ₹{sr['support'][0]:,.2f} and resistance near ₹{sr['resistance'][0]:,.2f}."
                else:
                    response = f"I don't have enough data to analyze {symbol} right now."
            except Exception as e:
                import logging
                logging.error(f"Error analyzing {symbol}: {e}")
                response = f"Sorry, I couldn't analyze {symbol} at this moment."
        else:
            response = "I couldn't identify the stock you are asking about. Please provide a clear symbol or company name."
            
    elif "support" in msg or "resistance" in msg or "level" in msg:
        if symbol:
            try:
                from backend.services.advanced_indicators import AdvancedIndicators
                from backend.services.indicators import candles_to_df
                candles = await market_data_service.fetch_candles(symbol, "1d", limit=250)
                df = candles_to_df(candles)
                sr = AdvancedIndicators.detect_support_resistance(df)
                response = f"Detected support levels: {sr['support'][:2]}. Resistance levels: {sr['resistance'][:2]}."
            except Exception:
                response = "Unable to compute levels."
        else:
            response = "Please provide a symbol to find support/resistance levels."

    return {"response": response, "type": "text"}
