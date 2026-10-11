"""
Volume Profile calculation service.

Computes the distribution of traded volume across price bins to identify
institutional accumulation/distribution zones:
  - Point of Control (POC): price level with highest traded volume
  - Value Area High (VAH): upper bound of 70% volume concentration
  - Value Area Low (VAL): lower bound of 70% volume concentration
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def calculate_volume_profile(
    df: pd.DataFrame,
    num_bins: int = 50,
    value_area_pct: float = 0.70,
) -> dict:
    """
    Compute volume profile from OHLCV DataFrame.

    Groups volume into ``num_bins`` equal-width price bins between the period
    High and Low.  For each bin, buy volume (close > open) and sell volume
    (close <= open) are aggregated separately.

    Returns a dict with:
      - bins: list of {price_low, price_high, price_mid, buy_volume, sell_volume, total_volume}
      - poc: Point of Control (price_mid of highest-volume bin)
      - vah: Value Area High
      - val: Value Area Low
      - total_volume: grand total across all bins
    """
    if df.empty or len(df) < 5:
        logger.warning("Insufficient data for volume profile (need >= 5 rows)")
        return {"bins": [], "poc": 0, "vah": 0, "val": 0, "total_volume": 0}

    period_high = float(df["High"].max())
    period_low = float(df["Low"].min())

    if period_high == period_low:
        return {"bins": [], "poc": period_high, "vah": period_high, "val": period_low, "total_volume": 0}

    bin_edges = np.linspace(period_low, period_high, num_bins + 1)
    bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2.0

    buy_volumes = np.zeros(num_bins)
    sell_volumes = np.zeros(num_bins)

    closes = df["Close"].values
    opens = df["Open"].values
    highs = df["High"].values
    lows = df["Low"].values
    volumes = df["Volume"].values

    for i in range(len(df)):
        candle_low = lows[i]
        candle_high = highs[i]
        vol = volumes[i]
        is_buy = closes[i] > opens[i]

        # Determine which bins this candle's price range overlaps
        bin_start = int(np.searchsorted(bin_edges, candle_low, side="right")) - 1
        bin_end = int(np.searchsorted(bin_edges, candle_high, side="left"))

        bin_start = max(0, bin_start)
        bin_end = min(num_bins - 1, bin_end)

        num_overlapping = bin_end - bin_start + 1
        if num_overlapping <= 0:
            continue

        vol_per_bin = vol / num_overlapping

        for b in range(bin_start, bin_end + 1):
            if is_buy:
                buy_volumes[b] += vol_per_bin
            else:
                sell_volumes[b] += vol_per_bin

    total_volumes = buy_volumes + sell_volumes
    grand_total = float(total_volumes.sum())

    # Point of Control — price level with the highest total volume
    poc_idx = int(np.argmax(total_volumes))
    poc_price = float(bin_mids[poc_idx])

    # Value Area — the contiguous range around the POC containing
    # ``value_area_pct`` (default 70%) of total volume
    target_volume = grand_total * value_area_pct
    accumulated = float(total_volumes[poc_idx])
    va_low_idx = poc_idx
    va_high_idx = poc_idx

    while accumulated < target_volume and (va_low_idx > 0 or va_high_idx < num_bins - 1):
        expand_low = total_volumes[va_low_idx - 1] if va_low_idx > 0 else 0
        expand_high = total_volumes[va_high_idx + 1] if va_high_idx < num_bins - 1 else 0

        if expand_low >= expand_high and va_low_idx > 0:
            va_low_idx -= 1
            accumulated += total_volumes[va_low_idx]
        elif va_high_idx < num_bins - 1:
            va_high_idx += 1
            accumulated += total_volumes[va_high_idx]
        elif va_low_idx > 0:
            va_low_idx -= 1
            accumulated += total_volumes[va_low_idx]
        else:
            break

    vah = float(bin_edges[va_high_idx + 1])
    val = float(bin_edges[va_low_idx])

    bins = []
    for b in range(num_bins):
        bins.append({
            "price_low": round(float(bin_edges[b]), 2),
            "price_high": round(float(bin_edges[b + 1]), 2),
            "price_mid": round(float(bin_mids[b]), 2),
            "buy_volume": round(float(buy_volumes[b]), 0),
            "sell_volume": round(float(sell_volumes[b]), 0),
            "total_volume": round(float(total_volumes[b]), 0),
        })

    bin_total = sum(b["total_volume"] for b in bins)

    return {
        "bins": bins,
        "poc": round(poc_price, 2),
        "vah": round(vah, 2),
        "val": round(val, 2),
        "total_volume": bin_total,
    }
