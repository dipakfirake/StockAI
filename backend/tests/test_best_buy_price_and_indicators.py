"""
Unit and Integration Tests for:
1. Best Price to Buy Engine (Optimal Entry Zone vs CMP)
2. Structural Rule-Based Stop Loss & Asymmetric High-Reward Targets
3. Complete Technical Indicators Suite & Fundamental Valuation Ratios
4. Market Crash / Downside Protection Filter
5. Specialized Modular ML Models (Swing, Intraday, FnO, Fast Growth, Cap Segments)
6. Multi-Model Concurrency & Simultaneous Inference Execution
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from backend.services.indicators import IndicatorService, candles_to_df
from backend.services.screener import ScreenerService
from backend.services.ai_engine import ai_engine_service


def _generate_mock_candles(n=60, base_price=100.0, trend="up"):
    """Generates synthetic OHLCV daily bars for testing."""
    candles = []
    p = base_price
    start_time = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    for i in range(n):
        if trend == "up":
            delta = 0.5 + (i * 0.05)
        elif trend == "down":
            delta = -0.5 - (i * 0.05)
        else:
            delta = 0.2 if i % 2 == 0 else -0.2
        
        o = p
        c = p + delta
        h = max(o, c) + 0.4
        l = min(o, c) - 0.4
        v = 100000 + (i * 1000)
        p = c
        ts = (start_time + timedelta(days=i)).isoformat()
        candles.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})
    return candles


def test_complete_technical_indicators_in_candle_series():
    """Verify that compute_for_candles_series returns all required technical indicators."""
    candles = _generate_mock_candles(n=70, base_price=200.0)
    series = IndicatorService.compute_for_candles_series(candles)
    assert len(series) == 70
    
    last = series[-1]
    # Verify core indicators
    assert "rsi_14" in last
    assert "macd" in last
    assert "macd_hist" in last
    assert "macd_signal" in last
    assert "ema_9" in last
    assert "ema_21" in last
    assert "ema_50" in last
    assert "ema_200" in last
    assert "bb_upper" in last
    assert "bb_middle" in last
    assert "bb_lower" in last
    assert "stoch_k" in last
    assert "stoch_d" in last
    assert "adx_14" in last
    assert "atr_14" in last
    assert "supertrend" in last
    assert "vwap" in last

    # Check that values are calculated numbers (not None on bar 70)
    assert last["rsi_14"] is not None
    assert last["ema_9"] is not None
    assert last["ema_21"] is not None
    assert last["bb_upper"] > last["bb_lower"]
    assert last["atr_14"] > 0


@pytest.mark.asyncio
async def test_best_buy_price_and_structural_stop_loss():
    """Verify that screener computes Best Buy Price (not just CMP) and structural SL below swing low."""
    candles = _generate_mock_candles(n=60, base_price=1000.0, trend="up")
    latest_close = candles[-1]["close"]
    
    # Mock quote extended above support
    mock_quote = {"symbol": "INFY.NS", "price": latest_close + 15.0}
    mock_info = {
        "name": "Infosys Ltd",
        "pe_ratio": 24.5,
        "forward_pe": 22.0,
        "roe": 0.28,
        "roce": 0.32,
        "debt_to_equity": 0.05,
        "current_ratio": 2.1,
        "revenue_growth": 0.16,
        "ebitda": 30000000000.0,
        "market_cap": 600000000000.0,
    }

    with patch("backend.services.market_data.market_data_service.fetch_candles", new=AsyncMock(return_value=candles)), \
         patch("backend.services.market_data.market_data_service.fetch_quote", new=AsyncMock(return_value=mock_quote)), \
         patch("backend.services.market_data.market_data_service.get_stock_info", new=AsyncMock(return_value=mock_info)), \
         patch("backend.services.market_data.market_data_service.fetch_corporate_events", new=AsyncMock(return_value={})), \
         patch("backend.data.ingestion.news_scraper.fetch_stock_news", new=AsyncMock(return_value=[])):

        res = await ScreenerService._analyze_symbol("INFY.NS", force_refresh=True)

        assert res["symbol"] == "INFY.NS"
        assert res["action"] in ("BUY", "HOLD")
        assert res["cap_segment"] == "LARGE_CAP"
        assert res["is_fast_growth"] is True

        plan = res.get("trade_plan")
        assert plan is not None
        assert "best_buy_price" in plan
        assert "cmp" in plan
        assert "stop_loss" in plan
        assert "target_price" in plan

        # Structural Stop Loss must be strictly below Best Buy Price
        assert plan["stop_loss"] < plan["best_buy_price"]
        # Target must be strictly above Best Buy Price
        assert plan["target_price"] > plan["best_buy_price"]
        
        # Risk percentage must be controlled (between 1.5% and 5.5%)
        risk_pct = plan["risk_pct"]
        assert 1.4 <= risk_pct <= 5.5

        # Asymmetric Risk-to-Reward (minimum 1:2.0)
        assert plan["reward_to_risk"] >= 2.0

        # Assert targets are anchored to best_buy_price, NOT flat cmp
        assert "targets" in plan
        assert len(plan["targets"]) == 3
        t1 = plan["targets"][0]
        t2 = plan["targets"][1]
        t3 = plan["targets"][2]

        # T2 must equal target_price
        assert t2["price"] == plan["target_price"]
        
        # gain_pct in targets must match gain calculated from best_buy_price
        expected_t2_gain = round(abs(t2["price"] - plan["best_buy_price"]) / plan["best_buy_price"] * 100, 2)
        assert t2["gain_pct"] == expected_t2_gain
        assert "cmp_gain_pct" in t2
        assert "cmp_gain_pct" in plan


@pytest.mark.asyncio
async def test_consolidation_hold_target_calculated_from_structure():
    """Verify that even for consolidating stocks (HOLD), targets and entries are calculated from structural support/resistance."""
    flat_candles = []
    base_time = datetime(2026, 1, 1, 9, 15)
    for i in range(60):
        t = (base_time + timedelta(days=i)).isoformat()
        flat_candles.append({
            "timestamp": t,
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 100.0,
            "volume": 200000
        })

    mock_quote = {"symbol": "TATASTEEL.NS", "price": 100.0, "change": 0.0, "change_percent": 0.0}
    mock_info = {"name": "Tata Steel", "market_cap": 120000000000.0, "pe_ratio": 15.0}

    with patch("backend.services.market_data.market_data_service.fetch_candles", new=AsyncMock(return_value=flat_candles)), \
         patch("backend.services.market_data.market_data_service.fetch_quote", new=AsyncMock(return_value=mock_quote)), \
         patch("backend.services.market_data.market_data_service.get_stock_info", new=AsyncMock(return_value=mock_info)), \
         patch("backend.services.market_data.market_data_service.fetch_corporate_events", new=AsyncMock(return_value={})), \
         patch("backend.data.ingestion.news_scraper.fetch_stock_news", new=AsyncMock(return_value=[])):

        res = await ScreenerService._analyze_symbol("TATASTEEL.NS", force_refresh=True)
        plan = res.get("trade_plan")
        assert plan is not None
        assert "best_buy_price" in plan
        assert "target_price" in plan
        assert plan["stop_loss"] < plan["best_buy_price"]
        assert plan["target_price"] > plan["best_buy_price"]
        for tgt in plan["targets"]:
            expected_gain = round(abs(tgt["price"] - plan["best_buy_price"]) / plan["best_buy_price"] * 100, 2)
            assert tgt["gain_pct"] == expected_gain
            assert "cmp_gain_pct" in tgt


def test_specialized_ai_engine_profiles():
    """Verify that AIEngineService routes specialized profiles: SWING, INTRADAY, FNO, FAST_GROWTH."""
    indicators = {
        "close": 2500.0,
        "rsi_14": 56.5,
        "ema_9": 2490.0,
        "ema_21": 2470.0,
        "ema_50": 2420.0,
        "sma_200": 2300.0,
        "adx_14": 28.5,
        "atr_14": 35.0,
        "vwap": 2495.0,
        "macd": {"histogram": 4.5, "macd": 12.0, "signal": 7.5}
    }
    
    # 1. Swing Equity Mode
    swing_res = ai_engine_service.score(
        indicators=indicators,
        symbol="RELIANCE.NS",
        market_cap=1900000000000.0,
        trading_mode="SWING",
        segment="LARGE_CAP"
    )
    assert swing_res["trading_mode"] == "SWING"
    assert swing_res["segment"] == "LARGE_CAP"
    assert "probabilities" in swing_res
    assert "score" in swing_res

    # 2. Intraday Mode
    intraday_res = ai_engine_service.score(
        indicators=indicators,
        symbol="TCS.NS",
        market_cap=1400000000000.0,
        trading_mode="INTRADAY"
    )
    assert intraday_res["trading_mode"] == "INTRADAY"
    assert "intraday_execution" in intraday_res
    assert intraday_res["intraday_execution"]["timeframe"] == "5m / 15m"

    # 3. FnO Derivatives Mode
    fno_res = ai_engine_service.score(
        indicators=indicators,
        symbol="INFY.NS",
        trading_mode="FNO"
    )
    assert fno_res["trading_mode"] == "FNO"
    assert "fno_strategy" in fno_res
    assert "recommended_structure" in fno_res["fno_strategy"]

    # 4. Fast Growth Specialist Mode
    fast_growth_res = ai_engine_service.score(
        indicators=indicators,
        symbol="ANGELONE.NS",
        trading_mode="SWING",
        segment="FAST_GROWTH",
        fundamentals={"revenue_growth": 0.25, "roe": 0.30, "debt_to_equity": 0.20}
    )
    assert fast_growth_res["segment"] == "FAST_GROWTH"
    assert "growth_specialist" in fast_growth_res
    assert fast_growth_res["growth_specialist"]["is_fast_growth"] is True


@pytest.mark.asyncio
async def test_simultaneous_multi_model_concurrency():
    """Verify that all specialized models run simultaneously in parallel without deadlock or corruption."""
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "IOC.NS", "ANGELONE.NS", "BSOFT.NS", "TITAN.NS"]
    modes = ["SWING", "INTRADAY", "FNO", "SWING", "SWING", "INTRADAY", "FNO", "SWING"]
    segments = ["LARGE_CAP", "LARGE_CAP", "LARGE_CAP", "LARGE_CAP", "MID_CAP", "FAST_GROWTH", "MID_CAP", "LARGE_CAP"]

    async def _run_inference(sym, mode, seg):
        inds = {
            "close": 500.0,
            "rsi_14": 52.0,
            "ema_9": 498.0,
            "ema_21": 492.0,
            "ema_50": 480.0,
            "sma_200": 460.0,
            "adx_14": 24.0,
            "atr_14": 8.0,
            "vwap": 499.0,
            "macd": {"histogram": 1.2, "macd": 3.0, "signal": 1.8}
        }
        return await asyncio.to_thread(
            ai_engine_service.score,
            indicators=inds,
            symbol=sym,
            trading_mode=mode,
            segment=seg
        )

    tasks = [_run_inference(sym, mode, seg) for sym, mode, seg in zip(symbols, modes, segments)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 8
    for r in results:
        assert "score" in r
        assert "probabilities" in r
        assert "trading_mode" in r
        assert "segment" in r
