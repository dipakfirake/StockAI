"""
Technical indicator calculation service using ta library.

All indicators are computed on OHLCV DataFrames and returned as dicts.
Indicators included:
  - RSI (14)
  - MACD (12/26/9)
  - Bollinger Bands (20/2)
  - EMA (9, 21, 50, 200)
  - SMA (50, 200)
  - ATR (14)
  - ADX (14)
  - Stochastic (14, 3)
  - Volume SMA (20)
  - SuperTrend (Custom Implementation)
  - VWAP
  - Ichimoku
"""

from __future__ import annotations

import pandas as pd
import numpy as np
import ta

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def candles_to_df(candles: list[dict]) -> pd.DataFrame:
    """Convert list of candle dicts to a pandas DataFrame."""
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"
    })
    return df


def calculate_supertrend(df: pd.DataFrame, period: int = 7, multiplier: float = 3.0) -> pd.DataFrame:
    """Custom SuperTrend implementation."""
    hl2 = (df['High'] + df['Low']) / 2
    atr = ta.volatility.AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=period).average_true_range()
    
    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)
    
    final_upperband = np.zeros(len(df))
    final_lowerband = np.zeros(len(df))
    supertrend = np.zeros(len(df))
    supertrend_dir = np.zeros(len(df), dtype=int)
    
    basic_upper = basic_upperband.values
    basic_lower = basic_lowerband.values
    close_prices = df['Close'].values
    
    final_upperband[0] = basic_upper[0]
    final_lowerband[0] = basic_lower[0]
    supertrend[0] = final_upperband[0]
    supertrend_dir[0] = 1
    
    for i in range(1, len(df)):
        if basic_upper[i] < final_upperband[i-1] or close_prices[i-1] > final_upperband[i-1]:
            final_upperband[i] = basic_upper[i]
        else:
            final_upperband[i] = final_upperband[i-1]
            
        if basic_lower[i] > final_lowerband[i-1] or close_prices[i-1] < final_lowerband[i-1]:
            final_lowerband[i] = basic_lower[i]
        else:
            final_lowerband[i] = final_lowerband[i-1]
            
        if supertrend[i-1] == final_upperband[i-1] and close_prices[i] <= final_upperband[i]:
            supertrend[i] = final_upperband[i]
            supertrend_dir[i] = -1
        elif supertrend[i-1] == final_upperband[i-1] and close_prices[i] > final_upperband[i]:
            supertrend[i] = final_lowerband[i]
            supertrend_dir[i] = 1
        elif supertrend[i-1] == final_lowerband[i-1] and close_prices[i] >= final_lowerband[i]:
            supertrend[i] = final_lowerband[i]
            supertrend_dir[i] = 1
        elif supertrend[i-1] == final_lowerband[i-1] and close_prices[i] < final_lowerband[i]:
            supertrend[i] = final_upperband[i]
            supertrend_dir[i] = -1
            
    return pd.DataFrame({
        'SuperTrend': supertrend,
        'Direction': supertrend_dir
    }, index=df.index)


def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects candlestick patterns using strict, high-accuracy mathematical ratios."""
    patterns = np.full(len(df), None, dtype=object)
    
    op = df['Open'].values
    hi = df['High'].values
    lo = df['Low'].values
    cl = df['Close'].values
    
    for i in range(2, len(df)):
        O1, H1, L1, C1 = op[i-1], hi[i-1], lo[i-1], cl[i-1]
        O2, H2, L2, C2 = op[i], hi[i], lo[i], cl[i]
        
        body1 = abs(C1 - O1)
        body2 = abs(C2 - O2)
        range1 = H1 - L1
        range2 = H2 - L2
        
        if range2 == 0:
            continue
            
        is_bullish1 = C1 > O1
        is_bullish2 = C2 > O2
        
        lower_wick = min(O2, C2) - L2
        upper_wick = H2 - max(O2, C2)
        
        # 1. Standard Engulfing (Body engulfs previous body)
        if not is_bullish1 and is_bullish2 and O2 <= C1 and C2 >= O1 and body2 > body1 * 1.2:
            patterns[i] = 'Bullish Engulfing'
            continue
        elif is_bullish1 and not is_bullish2 and O2 >= C1 and C2 <= O1 and body2 > body1 * 1.2:
            patterns[i] = 'Bearish Engulfing'
            continue
            
        # 2. Hammer / Hanging Man (Lower wick >= 2.0x body, Upper wick <= 15% of range)
        if is_bullish2 and lower_wick >= 2.0 * body2 and upper_wick <= 0.15 * range2:
            patterns[i] = 'Hammer' if not is_bullish1 else 'Hanging Man'
            continue
                
        # 3. Shooting Star / Inverted Hammer (Upper wick >= 2.0x body, Lower wick <= 15% of range)
        if not is_bullish2 and upper_wick >= 2.0 * body2 and lower_wick <= 0.15 * range2:
            patterns[i] = 'Shooting Star' if is_bullish1 else 'Inverted Hammer'
            continue
            
        # 4. Doji (Body is <= 5% of total range)
        if (body2 / range2) <= 0.05:
            patterns[i] = 'Doji'
            continue
            
    return pd.Series(patterns, index=df.index, name='Pattern')

class IndicatorService:
    """Computes technical indicators from OHLCV candle data."""

    @staticmethod
    def compute_all(candles: list[dict]) -> dict:
        if len(candles) < 30:
            logger.warning("Insufficient candles for indicator computation (need ≥ 30)")
            return {}

        df = candles_to_df(candles)

        try:
            # RSI
            rsi = ta.momentum.RSIIndicator(close=df["Close"], window=14)
            df["rsi_14"] = rsi.rsi()

            # MACD
            macd = ta.trend.MACD(close=df["Close"], window_slow=26, window_fast=12, window_sign=9)
            df["macd"] = macd.macd()
            df["macd_signal"] = macd.macd_signal()
            df["macd_hist"] = macd.macd_diff()

            # Bollinger Bands
            bb = ta.volatility.BollingerBands(close=df["Close"], window=20, window_dev=2)
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_mid"] = bb.bollinger_mavg()
            df["bb_lower"] = bb.bollinger_lband()

            # EMAs
            df["ema_9"] = ta.trend.EMAIndicator(close=df["Close"], window=9).ema_indicator()
            df["ema_21"] = ta.trend.EMAIndicator(close=df["Close"], window=21).ema_indicator()
            df["ema_50"] = ta.trend.EMAIndicator(close=df["Close"], window=50).ema_indicator()
            df["ema_200"] = ta.trend.EMAIndicator(close=df["Close"], window=200).ema_indicator()

            # SMAs
            df["sma_50"] = ta.trend.SMAIndicator(close=df["Close"], window=50).sma_indicator()
            df["sma_200"] = ta.trend.SMAIndicator(close=df["Close"], window=200).sma_indicator()

            # ATR
            df["atr_14"] = ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()

            # ADX
            adx = ta.trend.ADXIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=14)
            df["adx_14"] = adx.adx()

            # Stochastic
            stoch = ta.momentum.StochasticOscillator(high=df["High"], low=df["Low"], close=df["Close"], window=14, smooth_window=3)
            df["stoch_k"] = stoch.stoch()
            df["stoch_d"] = stoch.stoch_signal()

            # CCI
            cci = ta.trend.CCIIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=20)
            df["cci_20"] = cci.cci()

            # Volume SMA
            df["vol_sma_20"] = ta.trend.SMAIndicator(close=df["Volume"], window=20).sma_indicator()
            
            # SuperTrend
            st_df = calculate_supertrend(df)
            df["supertrend"] = st_df["SuperTrend"]
            df["supertrend_dir"] = st_df["Direction"]
                
            # VWAP
            df["vwap"] = ta.volume.VolumeWeightedAveragePrice(high=df["High"], low=df["Low"], close=df["Close"], volume=df["Volume"]).volume_weighted_average_price()
                
            # Ichimoku
            ichi = ta.trend.IchimokuIndicator(high=df["High"], low=df["Low"])
            df["ichi_tenkan"] = ichi.ichimoku_conversion_line()
            df["ichi_kijun"] = ichi.ichimoku_base_line()
            df["ichi_senkou_a"] = ichi.ichimoku_a()
            df["ichi_senkou_b"] = ichi.ichimoku_b()

            latest = df.iloc[-1]

            def _safe(val, ndigits=4):
                try:
                    return round(float(val), ndigits) if pd.notna(val) else None
                except Exception:
                    return None

            return {
                "rsi_14": _safe(latest.get("rsi_14")),
                "macd": {
                    "macd": _safe(latest.get("macd")),
                    "signal": _safe(latest.get("macd_signal")),
                    "histogram": _safe(latest.get("macd_hist")),
                },
                "bb": {
                    "upper": _safe(latest.get("bb_upper")),
                    "middle": _safe(latest.get("bb_mid")),
                    "lower": _safe(latest.get("bb_lower")),
                },
                "ema_9": _safe(latest.get("ema_9")),
                "ema_21": _safe(latest.get("ema_21")),
                "ema_50": _safe(latest.get("ema_50")),
                "ema_200": _safe(latest.get("ema_200")),
                "sma_50": _safe(latest.get("sma_50")),
                "sma_200": _safe(latest.get("sma_200")),
                "atr_14": _safe(latest.get("atr_14")),
                "adx_14": _safe(latest.get("adx_14")),
                "stoch_k": _safe(latest.get("stoch_k")),
                "stoch_d": _safe(latest.get("stoch_d")),
                "cci_20": _safe(latest.get("cci_20")),
                "vol_sma_20": _safe(latest.get("vol_sma_20"), ndigits=0),
                "supertrend": {
                    "value": _safe(latest.get("supertrend")),
                    "direction": "up" if latest.get("supertrend_dir") == 1 else "down" if latest.get("supertrend_dir") == -1 else "none"
                },
                "vwap": _safe(latest.get("vwap")),
                "ichimoku": {
                    "tenkan_sen": _safe(latest.get("ichi_tenkan")),
                    "kijun_sen": _safe(latest.get("ichi_kijun")),
                    "senkou_span_a": _safe(latest.get("ichi_senkou_a")),
                    "senkou_span_b": _safe(latest.get("ichi_senkou_b")),
                },
                "close": _safe(latest.get("Close")),
                "volume": int(latest.get("Volume", 0)),
            }
        except Exception as e:
            logger.error(f"Indicator computation failed: {e}")
            return {}

    @staticmethod
    def _detect_order_blocks(df: pd.DataFrame) -> pd.Series:
        """High-accuracy Order Block detection: strong impulsive candle with massive volume and price displacement > ATR."""
        ob_series = pd.Series([None] * len(df), index=df.index)
        
        # Ensure we have ATR and Vol SMA for mathematical rigor
        if 'atr_14' not in df.columns:
            df['atr_14'] = ta.volatility.AverageTrueRange(high=df["High"], low=df["Low"], close=df["Close"], window=14).average_true_range()
        if 'vol_sma_20' not in df.columns:
            df['vol_sma_20'] = ta.trend.SMAIndicator(close=df["Volume"], window=20).sma_indicator()
            
        for i in range(20, len(df)):
            body = abs(df['Close'].iloc[i] - df['Open'].iloc[i])
            prev_body = abs(df['Close'].iloc[i-1] - df['Open'].iloc[i-1])
            atr = df['atr_14'].iloc[i-1]
            vol_sma = df['vol_sma_20'].iloc[i-1]
            vol = df['Volume'].iloc[i]
            
            if atr == 0 or vol_sma == 0:
                continue
                
            # Strict Conditions:
            # 1. Volume must be > 150% of the 20-period moving average volume (Institutional footprint)
            # 2. Price Body must be > 1.5x the Average True Range (True displacement)
            # 3. Body > 3x previous body
            if vol > (vol_sma * 1.5) and body > (atr * 1.5) and body > (prev_body * 3):
                if df['Close'].iloc[i] > df['Open'].iloc[i]:
                    ob_series.iloc[i-1] = "bullish_ob"
                else:
                    ob_series.iloc[i-1] = "bearish_ob"
        return ob_series

    @staticmethod
    def compute_for_candles_series(candles: list[dict]) -> list[dict]:
        if len(candles) < 30:
            return candles

        df = candles_to_df(candles)
        try:
            df["rsi_14"] = ta.momentum.RSIIndicator(close=df["Close"], window=14).rsi()
            macd_indicator = ta.trend.MACD(close=df["Close"])
            df["macd_hist"] = macd_indicator.macd_diff()
            df["macd"] = macd_indicator.macd()
            df["macd_signal"] = macd_indicator.macd_signal()
            df["ema_9"] = ta.trend.EMAIndicator(close=df["Close"], window=9).ema_indicator()
            df["ema_21"] = ta.trend.EMAIndicator(close=df["Close"], window=21).ema_indicator()
            df["ema_50"] = ta.trend.EMAIndicator(close=df["Close"], window=50).ema_indicator()
            df["cci_20"] = ta.trend.CCIIndicator(high=df["High"], low=df["Low"], close=df["Close"], window=20).cci()
            
            # Premium Indicators
            st_df = calculate_supertrend(df)
            df["supertrend"] = st_df["SuperTrend"]
            df["supertrend_dir"] = st_df["Direction"]
            df["vwap"] = ta.volume.VolumeWeightedAveragePrice(high=df["High"], low=df["Low"], close=df["Close"], volume=df["Volume"]).volume_weighted_average_price()
            df["order_block"] = IndicatorService._detect_order_blocks(df)

            result = []
            for ts, row in df.iterrows():
                result.append({
                    "timestamp": ts.isoformat(),
                    "open": round(float(row["Open"]), 4),
                    "high": round(float(row["High"]), 4),
                    "low": round(float(row["Low"]), 4),
                    "close": round(float(row["Close"]), 4),
                    "volume": int(row["Volume"]),
                    "rsi_14": round(float(row["rsi_14"]), 2) if pd.notna(row.get("rsi_14")) else None,
                    "macd_hist": round(float(row["macd_hist"]), 4) if pd.notna(row.get("macd_hist")) else None,
                    "macd": round(float(row["macd"]), 4) if pd.notna(row.get("macd")) else None,
                    "macd_signal": round(float(row["macd_signal"]), 4) if pd.notna(row.get("macd_signal")) else None,
                    "ema_9": round(float(row["ema_9"]), 4) if pd.notna(row.get("ema_9")) else None,
                    "ema_21": round(float(row["ema_21"]), 4) if pd.notna(row.get("ema_21")) else None,
                    "ema_50": round(float(row["ema_50"]), 4) if pd.notna(row.get("ema_50")) else None,
                    "cci_20": round(float(row["cci_20"]), 4) if pd.notna(row.get("cci_20")) else None,
                    "supertrend": round(float(row["supertrend"]), 4) if pd.notna(row.get("supertrend")) else None,
                    "supertrend_dir": int(row["supertrend_dir"]) if pd.notna(row.get("supertrend_dir")) else 0,
                    "vwap": round(float(row["vwap"]), 4) if pd.notna(row.get("vwap")) else None,
                    "order_block": row["order_block"] if pd.notna(row.get("order_block")) else None,
                })
            return result
        except Exception as e:
            logger.error(f"Series indicator computation failed: {e}")
            return candles

indicator_service = IndicatorService()
