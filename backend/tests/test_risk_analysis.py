"""Unit tests for risk analysis service."""

import math
import pytest
from backend.services.risk_analysis import analyse_risk


def test_analyse_risk_normal_candles():
    candles = [
        {"close": 100.0 + i * 0.5} for i in range(50)
    ]
    result = analyse_risk(candles)
    assert result["level"] in ("LOW", "MEDIUM", "HIGH")
    assert result["observations"] == 50
    assert result["annualized_volatility_pct"] >= 0
    assert result["value_at_risk_95_pct"] >= 0


def test_analyse_risk_handles_nan_and_none():
    """Verify that NaN, None, and zero values (e.g. from yfinance missing data) do not crash statistics."""
    candles = [
        {"close": 100.0},
        {"close": float("nan")},
        {"close": None},
        {"close": 0.0},
        {"close": 102.0},
        {"close": 101.5},
        {"close": float("inf")},
        {"close": 103.0},
    ]
    result = analyse_risk(candles)
    assert result["level"] in ("LOW", "MEDIUM", "HIGH", "UNKNOWN")
    assert not math.isnan(result["annualized_volatility_pct"])
    assert not math.isnan(result["value_at_risk_95_pct"])


def test_analyse_risk_insufficient_candles():
    assert analyse_risk([])["level"] == "UNKNOWN"
    assert analyse_risk([{"close": 100.0}])["level"] == "UNKNOWN"
    assert analyse_risk([{"close": 100.0}, {"close": 101.0}])["level"] == "UNKNOWN"
