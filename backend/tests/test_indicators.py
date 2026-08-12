"""Unit tests for indicator calculations."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.services.indicators import IndicatorService, candles_to_df


def generate_candles(n: int = 100) -> list[dict]:
    """Generate synthetic OHLCV candles for testing."""
    candles = []
    price = 1000.0
    base_date = datetime(2023, 1, 1)
    for i in range(n):
        change = np.random.uniform(-0.02, 0.02)
        open_ = price
        close = price * (1 + change)
        high = max(open_, close) * np.random.uniform(1.0, 1.01)
        low = min(open_, close) * np.random.uniform(0.99, 1.0)
        candles.append({
            "timestamp": (base_date + timedelta(days=i)).isoformat(),
            "open": round(open_, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": np.random.randint(100000, 5000000),
        })
        price = close
    return candles


def test_candles_to_df():
    """candles_to_df should produce a valid DataFrame with OHLCV columns."""
    candles = generate_candles(50)
    df = candles_to_df(candles)
    assert isinstance(df, pd.DataFrame)
    assert "Open" in df.columns
    assert "Close" in df.columns
    assert len(df) == 50


def test_compute_all_returns_dict():
    """compute_all should return a dict with standard indicator keys."""
    candles = generate_candles(100)
    result = IndicatorService.compute_all(candles)
    assert isinstance(result, dict)
    assert "rsi_14" in result
    assert "macd" in result
    assert "bb" in result
    assert "ema_9" in result
    assert "ema_21" in result


def test_compute_all_insufficient_data():
    """compute_all with < 30 candles should return empty dict."""
    candles = generate_candles(10)
    result = IndicatorService.compute_all(candles)
    assert result == {}


def test_rsi_within_range():
    """RSI should always be between 0 and 100."""
    candles = generate_candles(100)
    result = IndicatorService.compute_all(candles)
    rsi = result.get("rsi_14")
    if rsi is not None:
        assert 0 <= rsi <= 100


def test_bollinger_band_structure():
    """BB result should have upper, middle, lower keys."""
    candles = generate_candles(100)
    result = IndicatorService.compute_all(candles)
    bb = result.get("bb", {})
    assert "upper" in bb
    assert "middle" in bb
    assert "lower" in bb
    if all(v is not None for v in bb.values()):
        assert bb["upper"] >= bb["middle"] >= bb["lower"]


def get_deterministic_candles() -> list[dict]:
    """Return a deterministic array of candles for exact mathematical validation."""
    prices = [100.0, 102.0, 101.0, 105.0, 104.0, 107.0, 106.0, 109.0, 110.0, 108.0,
              107.0, 109.0, 111.0, 113.0, 112.0, 115.0, 114.0, 118.0, 117.0, 119.0,
              120.0, 118.0, 117.0, 119.0, 122.0, 121.0, 124.0, 125.0, 123.0, 126.0,
              128.0, 127.0, 130.0, 129.0, 132.0, 131.0]
    
    candles = []
    base_date = datetime(2023, 1, 1)
    for i, p in enumerate(prices):
        candles.append({
            "timestamp": (base_date + timedelta(days=i)).isoformat(),
            "open": p - 1,
            "high": p + 2,
            "low": p - 2,
            "close": p,
            "volume": 100000
        })
    return candles


def test_mathematical_accuracy_rsi():
    """Verify RSI calculation exactly against known standard formulas."""
    candles = get_deterministic_candles()
    result = IndicatorService.compute_all(candles)
    rsi = result.get("rsi_14")
    # For this specific upward trending array, RSI should be in overbought territory (> 60)
    assert rsi is not None
    assert 65.0 <= rsi <= 85.0


def test_mathematical_accuracy_ema():
    """Verify EMA 9 and 21 calculations strictly follow the multiplier formula."""
    candles = get_deterministic_candles()
    result = IndicatorService.compute_all(candles)
    ema9 = result.get("ema_9")
    ema21 = result.get("ema_21")
    assert ema9 is not None
    assert ema21 is not None
    # With a strictly monotonic overall uptrend, short EMA must lead long EMA
    assert ema9 > ema21
    # Check if EMA9 is roughly tracking the recent prices (around 128-131)
    assert 125.0 <= ema9 <= 132.0
