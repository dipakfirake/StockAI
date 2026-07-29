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
