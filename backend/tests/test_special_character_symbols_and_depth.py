"""
Comprehensive tests for special character stock symbols (e.g. M&M.NS, M&MFIN.NS, L&TFH.NS, J&KBANK.NS)
Validates:
1. Parameter Sanitization (sanitize_symbol accepts ampersand, underscore, percent-encoded URL inputs).
2. Defense against malicious traversal, code injection, and invalid characters.
3. RAG intent and entity extraction for multi-character ampersand tickers.
4. Market depth and synthetic order book generation for M&M.NS without exceptions.
"""

import pytest
from fastapi import HTTPException
from backend.core.param_validator import sanitize_symbol, validate_timeframe
from backend.services.market_depth_service import MarketDepthService
from backend.services.rag_service import rag_service


def test_sanitize_symbol_ampersand_and_special_chars():
    """Verify Indian equities with ampersands and hyphens are validated and sanitized cleanly."""
    assert sanitize_symbol("M&M.NS") == "M&M.NS"
    assert sanitize_symbol("m&m.ns") == "M&M.NS"
    assert sanitize_symbol("M&M") == "M&M"
    assert sanitize_symbol("M%26M.NS") == "M&M.NS"
    assert sanitize_symbol("m%26m.ns") == "M&M.NS"
    assert sanitize_symbol("M&MFIN.NS") == "M&MFIN.NS"
    assert sanitize_symbol("L&TFH.NS") == "L&TFH.NS"
    assert sanitize_symbol("J&KBANK.NS") == "J&KBANK.NS"
    assert sanitize_symbol("BAJAJ-AUTO.NS") == "BAJAJ-AUTO.NS"
    assert sanitize_symbol("NIFTY_50") == "^NSEI"
    assert sanitize_symbol("NIFTY50") == "^NSEI"
    assert sanitize_symbol("^NSEI") == "^NSEI"


def test_sanitize_symbol_rejects_malicious_inputs():
    """Verify path traversal, SQL injection fragments, and invalid symbols still fail with 400."""
    invalid_cases = [
        "",
        None,
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "SELECT * FROM stocks",
        "M&M; DROP TABLE stocks; --",
        "A" * 35,  # Exceeds 30 char bound
        "INVALID CHAR$",
        "RELIANCE | calc",
    ]
    for case in invalid_cases:
        with pytest.raises(HTTPException) as exc_info:
            sanitize_symbol(case)
        assert exc_info.value.status_code == 400


def test_rag_entity_extraction_for_ampersand_tickers():
    """Verify RAG intent and entity resolution correctly maps symbols with ampersands."""
    intent, sym = rag_service.extract_intent_and_entity("should i buy M&M")
    assert intent == "STOCK_ANALYSIS"
    assert sym == "M&M.NS"

    intent, sym = rag_service.extract_intent_and_entity("should i buy M&M.NS")
    assert intent == "STOCK_ANALYSIS"
    assert sym == "M&M.NS"

    intent, sym = rag_service.extract_intent_and_entity("should i buy m&mfin")
    assert intent == "STOCK_ANALYSIS"
    assert sym == "M&MFIN.NS"

    intent, sym = rag_service.extract_intent_and_entity("what is your view on L&TFH")
    assert intent == "STOCK_ANALYSIS"
    assert sym == "L&TFH.NS"

    intent, sym = rag_service.extract_intent_and_entity("can we accumulate J&KBANK")
    assert intent == "STOCK_ANALYSIS"
    assert sym == "J&KBANK.NS"


def test_market_depth_synthetic_generation_for_mm():
    """Verify MarketDepthService correctly handles M&M.NS without tick or calculation failure."""
    fake_quote = {
        "symbol": "M&M.NS",
        "price": 3500.0,
        "previous_close": 3480.0,
        "open": 3490.0,
        "high": 3520.0,
        "low": 3470.0,
        "volume": 1500000,
    }
    depth = MarketDepthService.generate_synthetic_depth("M&M.NS", fake_quote, is_open=False)
    assert depth["symbol"] == "M&M.NS"
    assert len(depth["bids"]) == 5
    assert len(depth["asks"]) == 5
    assert depth["ltp"] == 3500.0
    assert depth["lower_circuit"] > 0
    assert depth["upper_circuit"] > depth["lower_circuit"]
    assert depth["spread"] >= 0
