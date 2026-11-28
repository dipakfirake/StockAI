"""AI Engine API router."""

import asyncio
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
    """Get AI buy/hold/sell score with SHAP-style explanation and Tri-Model Ensemble (LightGBM + BiLSTM + Transformer)."""
    quote_task = market_data_service.fetch_quote(symbol.upper())
    candles_task = market_data_service.fetch_candles(symbol.upper(), timeframe, limit=250)
    quote, candles = await asyncio.gather(quote_task, candles_task, return_exceptions=True)
    if isinstance(candles, Exception) or len(candles) < 30:
        raise HTTPException(status_code=422, detail="Insufficient data for AI scoring")
    if not isinstance(quote, Exception) and quote:
        candles = market_data_service.synchronize_candle_tip(candles, quote)
    indicators = indicator_service.compute_all(candles)
    return ai_engine_service.score(indicators, symbol.upper(), candles=candles)


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
            quote_task = market_data_service.fetch_quote(sym)
            candles_task = market_data_service.fetch_candles(sym, timeframe, limit=250)
            quote, candles = await asyncio.gather(quote_task, candles_task, return_exceptions=True)
            if not isinstance(candles, Exception) and len(candles) >= 30:
                if not isinstance(quote, Exception) and quote:
                    candles = market_data_service.synchronize_candle_tip(candles, quote)
                indicators = indicator_service.compute_all(candles)
                score = ai_engine_service.score(indicators, sym, candles=candles)
                results.append(score)
        except Exception:
            results.append({"symbol": sym, "score": "ERROR", "confidence": 0})

    return {"scan_results": results, "total": len(results)}


from typing import Optional
from pydantic import BaseModel
from backend.services.rag_service import rag_service

class ChatRequest(BaseModel):
    message: str
    symbol: Optional[str] = None

@router.post("/chat")
async def ai_chat(
    request: ChatRequest,
    current_user=Depends(require_pro_tier)
):
    """
    Advanced Financial Hybrid-Context RAG Assistant powered by Groq AI.
    Delivers token-budgeted, ultra-concise, precision quantitative trade insights.
    """
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Chat message cannot be empty")

    result = await rag_service.process_chat_query(
        message=request.message.strip(),
        symbol_hint=request.symbol.strip() if request.symbol else None,
        user_id=str(getattr(current_user, "id", "") or ""),
        user_tier=str(getattr(current_user, "subscription_tier", "PRO") or "PRO"),
        is_admin=bool(getattr(current_user, "is_admin", False)),
    )
    if result.get("source") == "quota_guardrail":
        raise HTTPException(status_code=429, detail=result.get("reply") or "Daily AI quota reached")
    return {
        "reply": result.get("reply", ""),
        "response": result.get("response", ""),
        "source": result.get("source", "rag"),
        "model": result.get("model"),
        "intent": result.get("intent"),
        "entity": result.get("entity"),
        "groq_active": result.get("groq_active", False),
        "cached": result.get("cached", False),
        "tokens_used": result.get("tokens_used"),
        "latency_ms": result.get("latency_ms"),
        "quota": result.get("quota"),
        "type": "text"
    }
