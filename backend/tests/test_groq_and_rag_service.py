"""Automated verification suite for Groq AI integration and Advanced Financial Hybrid-Context RAG."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.groq_service import groq_service, GroqService
from backend.services.rag_service import rag_service, FinancialRAGService, COMMON_TICKER_MAP, CONCEPT_KB


def test_entity_and_intent_extraction():
    """Verify that user queries are correctly classified into CONCEPT, MARKET_REGIME, or STOCK_ANALYSIS."""
    rag = FinancialRAGService()

    # 1. Concept Queries
    intent, entity = rag.extract_intent_and_entity("What is Anchor VWAP and how do institutions use it?")
    assert intent == "CONCEPT"
    assert entity == "anchor vwap"

    intent, entity = rag.extract_intent_and_entity("Can you explain Heikin Ashi candles?")
    assert intent == "CONCEPT"
    assert entity == "heikin ashi"

    intent, entity = rag.extract_intent_and_entity("What is a fair value gap in smart money concepts?")
    assert intent == "CONCEPT"
    assert entity == "fair value gap"

    # 2. Market Regime Queries
    intent, entity = rag.extract_intent_and_entity("How is the broader market and Nifty looking today?")
    assert intent == "MARKET_REGIME"
    assert entity == "^NSEI"

    intent, entity = rag.extract_intent_and_entity("Is the market breadth bullish or bearish right now?")
    assert intent == "MARKET_REGIME"

    # 3. Stock Analysis Queries with Named Entity Resolution (Multi-Cap)
    # Large Cap
    intent, entity = rag.extract_intent_and_entity("Should I buy Tata Motors today?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "TATAMOTORS.NS"

    intent, entity = rag.extract_intent_and_entity("What is the target and stop loss for TCS?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "TCS.NS"

    intent, entity = rag.extract_intent_and_entity("Give me analysis on Reliance", symbol_hint="RELIANCE.NS")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "RELIANCE.NS"

    # Mid Cap
    intent, entity = rag.extract_intent_and_entity("How is Polycab looking for swing trade?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "POLYCAB.NS"

    intent, entity = rag.extract_intent_and_entity("Is Dixon Tech a buy?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "DIXON.NS"

    # Small Cap
    intent, entity = rag.extract_intent_and_entity("Analyze Suzlon Energy for me")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "SUZLON.NS"

    intent, entity = rag.extract_intent_and_entity("What is the stop loss for IREDA?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "IREDA.NS"

    intent, entity = rag.extract_intent_and_entity("Should I buy CDSL?")
    assert intent == "STOCK_ANALYSIS"
    assert entity == "CDSL.NS"


@pytest.mark.asyncio
async def test_dynamic_universal_stock_search_async():
    """Verify that extract_intent_and_entity_async dynamically searches DB/Yahoo for any Small/Mid/Large cap stock."""
    rag = FinancialRAGService()

    fake_search_results = [
        {"symbol": "PREMIERENE", "name": "Premier Energies Limited", "exchange": "NSE"}
    ]

    with patch("backend.services.market_data.market_data_service.search_stocks", new=AsyncMock(return_value=fake_search_results)):
        intent, entity = await rag.extract_intent_and_entity_async("What is the trade plan for Premier Energies?")
        assert intent == "STOCK_ANALYSIS"
        assert entity == "PREMIERENE.NS"


def test_deterministic_quant_response_conciseness_and_precision():
    """Verify that deterministic quant synthesis produces punchy bullet points under 120 words with verified numbers."""
    rag = FinancialRAGService()

    fake_context = {
        "symbol": "TCS.NS",
        "cmp": 4150.0,
        "action": "BUY",
        "total_score": 78.5,
        "cap_segment": "LARGE_CAP",
        "is_fast_growth": True,
        "trade_plan": {
            "best_buy_price": 4120.0,
            "stop_loss": 4015.0,
            "target_1": 4277.5,
            "target_2": 4382.5,
            "expected_gain_pct": 6.4,
            "risk_pct": 2.5,
            "reward_to_risk": 2.5,
            "hold_time": "3 to 5 Days",
            "entry_advice": "Pullback dip to 21-EMA support base."
        },
        "support": 4015.0,
        "resistance": 4385.0
    }

    reply = rag.generate_deterministic_response("STOCK_ANALYSIS", "TCS.NS", fake_context, "Should I buy TCS?")
    
    assert "TCS" in reply
    assert "BUY" in reply
    assert "78.5/100" in reply
    assert "₹4,120.00" in reply
    assert "₹4,015.00" in reply
    assert "₹4,382.50" in reply
    assert "+6.4%" in reply
    assert "2.5:1" in reply
    assert "[💎 Large Cap]" in reply
    assert "[🚀 Fast Growth]" in reply

    # Token and brevity check: response should be under 120 words
    word_count = len(reply.split())
    assert word_count <= 120, f"Response too verbose ({word_count} words)"


@pytest.mark.asyncio
async def test_groq_service_fallback_when_unconfigured():
    """Verify that when GROQ_API_KEY is missing or empty, GroqService gracefully returns None and RAG uses quant fallback."""
    with patch("backend.services.groq_service.settings.GROQ_API_KEY", ""):
        service = GroqService()
        assert service.is_configured() is False
        
        res = await service.generate_completion("system prompt", "user query")
        assert res is None

        # Verify Master RAG pipeline still returns 100% valid response via fallback
        rag_res = await rag_service.process_chat_query("What is Anchor VWAP?")
        assert rag_res is not None
        assert "Anchor VWAP" in rag_res["reply"]
        assert rag_res["source"] == "deterministic_quant_rag"
        assert rag_res["groq_active"] is False


@pytest.mark.asyncio
async def test_groq_service_completion_with_mocked_api():
    """Verify that GroqService properly formats request payload, headers, and handles successful completion."""
    fake_groq_response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "llama-3.3-70b-versatile",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "### 🎯 TCS Trade Plan\n- **Signal & Conviction**: **BUY** (Score: **78.5/100** | CMP: ₹4,150.00)\n- **Execution Levels**: Best Buy: **₹4,120.00** | SL: **₹4,015.00** (-2.5%) | Target: **₹4,382.50** (+6.4%) | R:R: **2.5:1**\n- **Setup**: Pullback to 21-EMA support.\n- **Boundaries**: Support: ₹4,015.00 | Resistance: ₹4,385.00"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 180,
            "completion_tokens": 85,
            "total_tokens": 265
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_groq_response

    with patch("backend.services.groq_service.settings.GROQ_API_KEY", "gsk_test_mock_secret_key_12345"), \
         patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):

        service = GroqService()
        assert service.is_configured() is True

        res = await service.generate_completion(
            system_prompt="system instructions",
            user_prompt="Should I buy TCS?",
            max_tokens=280
        )

        assert res is not None
        assert res["success"] is True
        assert "TCS Trade Plan" in res["content"]
        assert res["model"] == "llama-3.3-70b-versatile"
        assert res["tokens_used"] == 265


@pytest.mark.asyncio
async def test_end_to_end_rag_stock_query_routing():
    """Verify end-to-end RAG pipeline processing a stock question with mocked market data."""
    fake_plan = {
        "action": "BUY",
        "total_score": 82.0,
        "name": "Tata Motors",
        "cap_segment": "LARGE_CAP",
        "is_fast_growth": True,
        "trade_plan": {
            "best_buy_price": 950.0,
            "stop_loss": 925.0,
            "target_1": 985.0,
            "target_2": 1012.5,
            "expected_gain_pct": 6.6,
            "risk_pct": 2.6,
            "reward_to_risk": 2.5,
            "estimated_hold_time": "3 to 4 Days",
            "entry_advice": "Dip to 21-EMA base."
        }
    }

    with patch.object(rag_service, "retrieve_stock_context", new=AsyncMock(return_value={
        "symbol": "TATAMOTORS.NS",
        "cmp": 955.0,
        "action": "BUY",
        "total_score": 82.0,
        "is_fast_growth": True,
        "trade_plan": fake_plan["trade_plan"],
        "support": 925.0,
        "resistance": 1015.0
    })):
        res = await rag_service.process_chat_query("Should I buy Tata Motors?")
        assert res is not None
        assert res["intent"] == "STOCK_ANALYSIS"
        assert res["entity"] == "TATAMOTORS.NS"
        assert "TATAMOTORS" in res["reply"] or "Tata Motors" in res["reply"]
        assert "₹950.00" in res["reply"]
        assert "₹925.00" in res["reply"]
        assert "₹1,012.50" in res["reply"]
