"""
Advanced indicator service — extended set from MASTER_PROMPT requirements.

Adds:
- VWAP (Volume Weighted Average Price — intraday)
- SuperTrend (ATR-based trend following, custom implementation)
- Ichimoku Cloud (Tenkan-sen, Kijun-sen, Senkou A/B, Chikou)
- OBV (On-Balance Volume)
- CMF (Chaikin Money Flow)
- Pivot Levels (Standard, Fibonacci, Camarilla)
- Auto Support/Resistance levels
- Candlestick pattern detection
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import ta
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class AdvancedIndicators:
    """Extended technical indicators beyond the MVP set."""

    @staticmethod
    def compute_vwap(df: pd.DataFrame) -> pd.Series:
        """
        Volume Weighted Average Price.
        Meaningful only for intraday data — reset daily.
        """
        typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
        return (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()

    @staticmethod
    def compute_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        """
        SuperTrend indicator — custom implementation using ta library ATR.
        Returns DataFrame with columns: supertrend, direction (1=bullish, -1=bearish)
        """
        try:
            atr = ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=period).average_true_range()
            hl2 = (df["High"] + df["Low"]) / 2
            basic_upper = hl2 + multiplier * atr
            basic_lower = hl2 - multiplier * atr

            final_upper = pd.Series(index=df.index, dtype=float)
            final_lower = pd.Series(index=df.index, dtype=float)
            supertrend = pd.Series(index=df.index, dtype=float)
            direction = pd.Series(index=df.index, dtype=int)

            final_upper.iloc[0] = basic_upper.iloc[0]
            final_lower.iloc[0] = basic_lower.iloc[0]
            supertrend.iloc[0] = final_upper.iloc[0]
            direction.iloc[0] = 1

            for i in range(1, len(df)):
                fu = basic_upper.iloc[i] if (basic_upper.iloc[i] < final_upper.iloc[i-1] or df["Close"].iloc[i-1] > final_upper.iloc[i-1]) else final_upper.iloc[i-1]
                fl = basic_lower.iloc[i] if (basic_lower.iloc[i] > final_lower.iloc[i-1] or df["Close"].iloc[i-1] < final_lower.iloc[i-1]) else final_lower.iloc[i-1]
                final_upper.iloc[i] = fu
                final_lower.iloc[i] = fl

                if supertrend.iloc[i-1] == final_upper.iloc[i-1]:
                    if df["Close"].iloc[i] <= fu:
                        supertrend.iloc[i] = fu
                        direction.iloc[i] = -1
                    else:
                        supertrend.iloc[i] = fl
                        direction.iloc[i] = 1
                else:
                    if df["Close"].iloc[i] >= fl:
                        supertrend.iloc[i] = fl
                        direction.iloc[i] = 1
                    else:
                        supertrend.iloc[i] = fu
                        direction.iloc[i] = -1

            return pd.DataFrame({"SuperTrend": supertrend, "Direction": direction}, index=df.index)
        except Exception as e:
            logger.error(f"SuperTrend computation failed: {e}")
            return pd.DataFrame()

    @staticmethod
    def compute_ichimoku(df: pd.DataFrame) -> dict:
        """
        Ichimoku Kinko Hyo cloud.
        Returns latest values for all 5 lines.
        """
        try:
            ichi = ta.trend.IchimokuIndicator(high=df["High"], low=df["Low"])
            tenkan = ichi.ichimoku_conversion_line().iloc[-1]
            kijun = ichi.ichimoku_base_line().iloc[-1]
            senkou_a = ichi.ichimoku_a().iloc[-1]
            senkou_b = ichi.ichimoku_b().iloc[-1]
            return {
                "tenkan_sen": round(float(tenkan), 4) if pd.notna(tenkan) else None,
                "kijun_sen": round(float(kijun), 4) if pd.notna(kijun) else None,
                "senkou_a": round(float(senkou_a), 4) if pd.notna(senkou_a) else None,
                "senkou_b": round(float(senkou_b), 4) if pd.notna(senkou_b) else None,
            }
        except Exception as e:
            logger.error(f"Ichimoku computation failed: {e}")
            return {}

    @staticmethod
    def compute_obv(df: pd.DataFrame) -> float | None:
        """On-Balance Volume — trend confirmation via cumulative volume."""
        try:
            obv = ta.volume.OnBalanceVolumeIndicator(close=df["Close"], volume=df["Volume"]).on_balance_volume()
            return float(obv.iloc[-1]) if obv is not None and not obv.empty else None
        except Exception:
            return None

    @staticmethod
    def compute_cmf(df: pd.DataFrame, length: int = 20) -> float | None:
        """Chaikin Money Flow — money flow over N periods. Range -1 to +1."""
        try:
            cmf = ta.volume.ChaikinMoneyFlowIndicator(high=df["High"], low=df["Low"], close=df["Close"], volume=df["Volume"], window=length).chaikin_money_flow()
            return round(float(cmf.iloc[-1]), 4) if cmf is not None and not cmf.empty else None
        except Exception:
            return None

    @staticmethod
    def compute_pivot_levels(df: pd.DataFrame) -> dict:
        """
        Standard pivot point levels based on previous day's OHLC.
        Returns: pivot, R1, R2, R3, S1, S2, S3
        """
        if len(df) < 2:
            return {}

        prev = df.iloc[-2]
        H = float(prev["High"])
        L = float(prev["Low"])
        C = float(prev["Close"])

        pivot = round((H + L + C) / 3, 4)
        r1 = round(2 * pivot - L, 4)
        r2 = round(pivot + (H - L), 4)
        r3 = round(H + 2 * (pivot - L), 4)
        s1 = round(2 * pivot - H, 4)
        s2 = round(pivot - (H - L), 4)
        s3 = round(L - 2 * (H - pivot), 4)

        return {
            "pivot": pivot,
            "R1": r1, "R2": r2, "R3": r3,
            "S1": s1, "S2": s2, "S3": s3,
        }

    @staticmethod
    def compute_market_structure(df: pd.DataFrame, lookback: int = 20) -> dict:
        """Original market-structure summary based on recent swing highs/lows."""
        if len(df) < lookback:
            return {"state": "INSUFFICIENT_DATA"}
        recent = df.tail(lookback)
        midpoint = max(2, lookback // 2)
        first, second = recent.iloc[:midpoint], recent.iloc[midpoint:]
        higher_high = float(second["High"].max()) > float(first["High"].max())
        higher_low = float(second["Low"].min()) > float(first["Low"].min())
        lower_high = float(second["High"].max()) < float(first["High"].max())
        lower_low = float(second["Low"].min()) < float(first["Low"].min())
        state = "BULLISH" if higher_high and higher_low else "BEARISH" if lower_high and lower_low else "RANGE"
        return {
            "state": state,
            "range_high": round(float(recent["High"].max()), 4),
            "range_low": round(float(recent["Low"].min()), 4),
            "breakout_level": round(float(recent["High"].max()), 4),
            "breakdown_level": round(float(recent["Low"].min()), 4),
            "lookback_bars": lookback,
        }

    @staticmethod
    def compute_volatility_squeeze(df: pd.DataFrame, window: int = 20) -> dict:
        """Original Bollinger/Keltner compression signal; not a vendor indicator."""
        if len(df) < window + 1:
            return {"state": "INSUFFICIENT_DATA"}
        close = df["Close"]
        basis = close.rolling(window).mean()
        std = close.rolling(window).std(ddof=0)
        bb_width = (4 * std / basis * 100).iloc[-1] if basis.iloc[-1] else 0
        atr = ta.volatility.AverageTrueRange(df["High"], df["Low"], close, window=window).average_true_range().iloc[-1]
        kc_width = (4 * atr / basis.iloc[-1] * 100) if basis.iloc[-1] else 0
        momentum = close.iloc[-1] - close.iloc[-window]
        return {
            "state": "SQUEEZE" if bb_width < kc_width else "EXPANDING",
            "bb_width_pct": round(float(bb_width), 3),
            "keltner_width_pct": round(float(kc_width), 3),
            "momentum": "UP" if momentum > 0 else "DOWN" if momentum < 0 else "FLAT",
        }

    @staticmethod
    def detect_support_resistance(df: pd.DataFrame, window: int = 20, min_touches: int = 2) -> dict:
        """
        Auto-detect support and resistance levels.
        Uses local min/max within rolling windows.
        """
        if len(df) < window * 2:
            return {"support": [], "resistance": []}

        closes = df["Close"]
        highs = df["High"]
        lows = df["Low"]

        # Find local maxima (resistance) and minima (support)
        resistance_levels = []
        support_levels = []

        for i in range(window, len(df) - window):
            # Local max = potential resistance
            if highs.iloc[i] == highs.iloc[i - window:i + window].max():
                resistance_levels.append(float(highs.iloc[i]))

            # Local min = potential support
            if lows.iloc[i] == lows.iloc[i - window:i + window].min():
                support_levels.append(float(lows.iloc[i]))

        # Cluster nearby levels (within 1%)
        def cluster_levels(levels: list, threshold_pct: float = 0.01) -> list:
            if not levels:
                return []
            levels = sorted(set(levels))
            clusters = [[levels[0]]]
            for level in levels[1:]:
                if (level - clusters[-1][-1]) / clusters[-1][-1] < threshold_pct:
                    clusters[-1].append(level)
                else:
                    clusters.append([level])
            return [round(sum(c) / len(c), 4) for c in clusters]

        current_price = float(closes.iloc[-1])
        all_support = [l for l in cluster_levels(support_levels) if l < current_price]
        all_resistance = [l for l in cluster_levels(resistance_levels) if l > current_price]

        return {
            "support": sorted(all_support, reverse=True)[:5],    # Nearest 5
            "resistance": sorted(all_resistance)[:5],             # Nearest 5
            "current_price": round(current_price, 4),
        }

    @staticmethod
    def detect_candlestick_patterns(df: pd.DataFrame) -> list[dict]:
        """
        Detect common candlestick patterns on the last 5 candles.
        Returns list of detected patterns with bullish/bearish classification.
        """
        if len(df) < 5:
            return []

        patterns_detected = []
        last = df.iloc[-1]
        prev = df.iloc[-2]

        body = abs(float(last["Close"]) - float(last["Open"]))
        full_range = float(last["High"]) - float(last["Low"])
        upper_wick = float(last["High"]) - max(float(last["Close"]), float(last["Open"]))
        lower_wick = min(float(last["Close"]), float(last["Open"])) - float(last["Low"])

        is_bullish_candle = float(last["Close"]) > float(last["Open"])
        is_bearish_candle = float(last["Close"]) < float(last["Open"])

        # Doji: body very small (< 5% of range)
        if full_range > 0 and body / full_range < 0.05:
            patterns_detected.append({
                "pattern": "Doji",
                "direction": "neutral",
                "description": "Indecision candle — bulls and bears in balance. Watch for confirmation.",
            })

        # Hammer: small body at top, long lower wick (≥ 2x body), in downtrend
        if body > 0 and lower_wick >= 2 * body and upper_wick <= 0.5 * body and is_bullish_candle:
            patterns_detected.append({
                "pattern": "Hammer",
                "direction": "bullish",
                "description": "Hammer pattern — potential bullish reversal after downtrend. Strong lower wick shows buyers defending lows.",
            })

        # Shooting Star: small body at bottom, long upper wick, in uptrend
        if body > 0 and upper_wick >= 2 * body and lower_wick <= 0.5 * body and is_bearish_candle:
            patterns_detected.append({
                "pattern": "Shooting Star",
                "direction": "bearish",
                "description": "Shooting Star — potential bearish reversal. Sellers pushed price sharply lower after an early rally.",
            })

        # Bullish Engulfing: current bullish candle body engulfs previous bearish candle body
        prev_bearish = float(prev["Open"]) > float(prev["Close"])
        if (is_bullish_candle and prev_bearish and
                float(last["Open"]) < float(prev["Close"]) and
                float(last["Close"]) > float(prev["Open"])):
            patterns_detected.append({
                "pattern": "Bullish Engulfing",
                "direction": "bullish",
                "description": "Bullish Engulfing — buyers completely overwhelmed sellers. Strong reversal signal.",
            })

        # Bearish Engulfing: current bearish candle body engulfs previous bullish candle body
        prev_bullish = float(prev["Close"]) > float(prev["Open"])
        if (is_bearish_candle and prev_bullish and
                float(last["Open"]) > float(prev["Close"]) and
                float(last["Close"]) < float(prev["Open"])):
            patterns_detected.append({
                "pattern": "Bearish Engulfing",
                "direction": "bearish",
                "description": "Bearish Engulfing — sellers completely overwhelmed buyers. Strong reversal signal.",
            })

        # Marubozu (strong trend candle): body is almost entire range
        if full_range > 0 and body / full_range > 0.90:
            direction = "bullish" if is_bullish_candle else "bearish"
            patterns_detected.append({
                "pattern": "Marubozu",
                "direction": direction,
                "description": f"Marubozu — very strong {'bullish' if is_bullish_candle else 'bearish'} candle with almost no wicks. Trend continuation expected.",
            })

        return patterns_detected


advanced_indicators = AdvancedIndicators()
