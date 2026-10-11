"""Unit tests for volume profile calculation."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from backend.services.volume_profile import calculate_volume_profile


def _make_ohlcv_df(n: int = 60, base_price: float = 1000.0) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for testing."""
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]
    rows = []
    price = base_price
    for d in dates:
        change = np.random.uniform(-0.015, 0.015)
        o = price
        c = price * (1 + change)
        h = max(o, c) * np.random.uniform(1.0, 1.008)
        lo = min(o, c) * np.random.uniform(0.992, 1.0)
        v = np.random.randint(100_000, 5_000_000)
        rows.append({"Open": o, "High": h, "Low": lo, "Close": c, "Volume": v})
        price = c
    df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    return df


class TestCalculateVolumeProfile:

    def test_returns_correct_structure(self):
        """Result dict contains bins, poc, vah, val, total_volume."""
        df = _make_ohlcv_df(60)
        result = calculate_volume_profile(df, num_bins=20)

        assert isinstance(result, dict)
        assert "bins" in result
        assert "poc" in result
        assert "vah" in result
        assert "val" in result
        assert "total_volume" in result
        assert len(result["bins"]) == 20

    def test_bin_structure(self):
        """Each bin contains the required fields."""
        df = _make_ohlcv_df(60)
        result = calculate_volume_profile(df, num_bins=10)

        for b in result["bins"]:
            assert "price_low" in b
            assert "price_high" in b
            assert "price_mid" in b
            assert "buy_volume" in b
            assert "sell_volume" in b
            assert "total_volume" in b
            assert b["price_low"] < b["price_high"]

    def test_poc_within_price_range(self):
        """Point of Control must be within the period high/low range."""
        df = _make_ohlcv_df(100)
        result = calculate_volume_profile(df, num_bins=30)

        period_low = float(df["Low"].min())
        period_high = float(df["High"].max())
        assert period_low <= result["poc"] <= period_high

    def test_value_area_contains_poc(self):
        """The value area [VAL, VAH] must contain the POC."""
        df = _make_ohlcv_df(80)
        result = calculate_volume_profile(df, num_bins=25)

        assert result["val"] <= result["poc"] <= result["vah"]

    def test_total_volume_matches_sum(self):
        """Grand total should equal sum of all bin total_volumes."""
        df = _make_ohlcv_df(50)
        result = calculate_volume_profile(df, num_bins=15)

        bin_sum = sum(b["total_volume"] for b in result["bins"])
        assert abs(result["total_volume"] - bin_sum) <= 2.0  # rounding tolerance

    def test_insufficient_data(self):
        """With fewer than 5 rows, should return empty bins."""
        df = _make_ohlcv_df(3)
        result = calculate_volume_profile(df)

        assert result["bins"] == []
        assert result["total_volume"] == 0

    def test_empty_dataframe(self):
        """Empty DataFrame should return safe defaults."""
        df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        result = calculate_volume_profile(df)

        assert result["bins"] == []
        assert result["total_volume"] == 0

    def test_single_price_level(self):
        """When all prices are identical, should handle gracefully."""
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(10)]
        rows = [{"Open": 100, "High": 100, "Low": 100, "Close": 100, "Volume": 1000} for _ in dates]
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
        result = calculate_volume_profile(df)

        assert result["poc"] == 100
        assert result["bins"] == []
