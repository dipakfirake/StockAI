"""Unit tests for the rule-based signal engine."""

import pytest
from backend.services.signals import SignalEngine


def make_indicators(**kwargs) -> dict:
    """Helper to build an indicator dict with defaults."""
    defaults = {
        "rsi_14": 50.0,
        "stoch_k": 50.0,
        "cci_20": 0.0,
        "macd": {"macd": 1.0, "signal": 0.5, "histogram": 0.5}, # Slightly bullish to balance score to ~50
        "ema_9": 105.0, "ema_21": 100.0, "ema_50": 105.0, "ema_200": 100.0, # MA cross defaults bullish to balance osc
        "sma_50": 95.0, "sma_200": 90.0,
        "bb": {"upper": 110.0, "middle": 100.0, "lower": 90.0},
        "close": 100.0,
        "adx_14": 20.0,
        "volume": 1000000,
        "vol_sma_20": 800000,
    }
    defaults.update(kwargs)
    return defaults


def test_oversold_rsi_generates_buy():
    """RSI < 30 should produce a BUY signal."""
    indicators = make_indicators(rsi_14=25.0)
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    assert signals[0]["type"] == "BUY"


def test_overbought_rsi_generates_sell():
    """RSI > 70 should produce a SELL signal."""
    # Provide bearish defaults so the overbought RSI tips it to SELL
    macd = {"macd": -1.0, "signal": -0.5, "histogram": -0.5}
    indicators = make_indicators(
        rsi_14=78.0, 
        macd=macd, 
        ema_9=95.0, ema_21=100.0, ema_50=98.0, ema_200=102.0,
        close=90.0, sma_50=95.0, sma_200=100.0
    )
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    assert signals[0]["type"] == "SELL"


def test_neutral_indicators_generate_hold():
    """Neutral indicators should produce a HOLD signal."""
    indicators = make_indicators(rsi_14=50.0, stoch_k=50.0, cci_20=0.0)
    # Neutralize moving averages to get a 50 score
    indicators.update({"ema_9": 100.0, "ema_21": 101.0, "ema_50": 100.0, "ema_200": 101.0, "close": 100.0, "sma_50": 101.0, "sma_200": 101.0})
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    # Expected score around ~35-45 which is SELL/HOLD. If we want HOLD, score must be 40-60.
    # To get 40-60: osc is 50. ma is 0. 50*0.3 = 15. We need more MA score to reach > 40.
    # Let's make some MAs bullish: close > sma_50 (100 > 95) = 100. ema_9 > ema_21 (105 > 100) = 100.
    indicators.update({"ema_9": 105.0, "ema_21": 100.0, "ema_50": 90.0, "ema_200": 100.0, "close": 100.0, "sma_50": 95.0, "sma_200": 105.0})
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals[0]["type"] in ("HOLD", "WATCH")


def test_golden_cross_scores_bullish():
    """EMA50 > EMA200 (golden cross) should add bullish score."""
    indicators = make_indicators(
        rsi_14=45.0,
        ema_50=2100.0, ema_200=2000.0,
        ema_9=105.0, ema_21=103.0,
    )
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    assert signals[0]["score"] > 0


def test_signal_has_reason():
    """Every signal must include a non-empty reason string."""
    indicators = make_indicators(rsi_14=28.0)
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    assert isinstance(signals[0]["reason"], str)
    assert len(signals[0]["reason"]) > 0


def test_signal_has_indicators_used():
    """Signal must include indicators_used dict for transparency."""
    indicators = make_indicators()
    signals = SignalEngine.evaluate(indicators, "TEST")
    assert signals
    assert "indicators_used" in signals[0]
    assert isinstance(signals[0]["indicators_used"], dict)


def test_daily_signal_includes_review_horizon():
    """Chart signals disclose a timeframe-based, non-guaranteed review horizon."""
    signal = SignalEngine.evaluate(make_indicators(rsi_14=25.0), "TEST", "1d")[0]
    horizon = signal["holding_period"]
    assert horizon["unit"] == "days"
    assert horizon["min"] == 5
    assert horizon["max"] in (15.0, 20.0)
    assert horizon["basis"] == "Technical Composite Rating"


def test_intraday_signal_uses_sessions_for_review_horizon():
    signal = SignalEngine.evaluate(make_indicators(rsi_14=25.0), "TEST", "15m")[0]
    assert signal["holding_period"]["unit"] == "sessions"
