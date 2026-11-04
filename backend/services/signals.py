"""
Rule-based signal engine using a Premium Composite Technical Score.

Generates a normalized 0-100 score by combining:
- Oscillators (30% weight): RSI, Stochastic, CCI, MACD
- Moving Averages (50% weight): EMA crosses, Price vs SMA
- Volatility (20% weight): Bollinger Bands
- Momentum Multiplier: ADX

Signal ranges:
0-20: STRONG SELL
20-40: SELL
40-60: HOLD
60-80: BUY
80-100: STRONG BUY
"""

from __future__ import annotations

from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class SignalEngine:
    @staticmethod
    def evaluate(indicators: dict, symbol: str = "", timeframe: str = "1d") -> list[dict]:
        """
        Evaluate all rules against the latest indicator values using a 0-100 composite score.
        """
        signals = []
        
        # Safe getters
        def _get(key, default=None):
            return indicators.get(key, default)

        rsi = _get("rsi_14")
        macd_dict = _get("macd", {})
        macd = macd_dict.get("macd") if isinstance(macd_dict, dict) else None
        macd_sig = macd_dict.get("signal") if isinstance(macd_dict, dict) else None
        stoch_k = _get("stoch_k")
        cci = _get("cci_20")
        
        ema9 = _get("ema_9")
        ema21 = _get("ema_21")
        ema50 = _get("ema_50")
        ema200 = _get("ema_200")
        sma50 = _get("sma_50")
        sma200 = _get("sma_200")
        
        bb_dict = _get("bb", {})
        bb_upper = bb_dict.get("upper") if isinstance(bb_dict, dict) else None
        bb_lower = bb_dict.get("lower") if isinstance(bb_dict, dict) else None
        
        close = _get("close")
        adx = _get("adx_14")
        atr = _get("atr_14") or _get("atr")
        volume = _get("volume")
        vol_sma_20 = _get("vol_sma_20")
        supertrend_raw = _get("supertrend")

        reasons = []
        
        # --- 1. Oscillators Score (0-100) ---
        osc_scores = []
        if rsi is not None:
            if rsi < 30: osc_scores.append(100); reasons.append(f"RSI({rsi:.1f}) is Oversold")
            elif rsi > 70: osc_scores.append(0); reasons.append(f"RSI({rsi:.1f}) is Overbought")
            else: osc_scores.append(50)
            
        if stoch_k is not None:
            if stoch_k < 20: osc_scores.append(100); reasons.append(f"Stochastic({stoch_k:.1f}) is Oversold")
            elif stoch_k > 80: osc_scores.append(0); reasons.append(f"Stochastic({stoch_k:.1f}) is Overbought")
            else: osc_scores.append(50)
            
        if cci is not None:
            if cci < -100: osc_scores.append(100); reasons.append(f"CCI({cci:.1f}) is Oversold")
            elif cci > 100: osc_scores.append(0); reasons.append(f"CCI({cci:.1f}) is Overbought")
            else: osc_scores.append(50)
            
        if macd is not None and macd_sig is not None:
            if macd > macd_sig: osc_scores.append(100); reasons.append("MACD is Bullish")
            else: osc_scores.append(0); reasons.append("MACD is Bearish")

        osc_final = sum(osc_scores) / len(osc_scores) if osc_scores else 50

        # --- 2. Moving Averages Score (0-100) ---
        ma_scores = []
        if ema9 is not None and ema21 is not None:
            if ema9 > ema21: ma_scores.append(100); reasons.append("Short-term EMA Trend is Up")
            else: ma_scores.append(0); reasons.append("Short-term EMA Trend is Down")
            
        if ema50 is not None and ema200 is not None:
            if ema50 > ema200: ma_scores.append(100); reasons.append("Golden Cross (EMA50 > EMA200)")
            else: ma_scores.append(0); reasons.append("Death Cross (EMA50 < EMA200)")
            
        if close is not None and sma50 is not None:
            if close > sma50: ma_scores.append(100)
            else: ma_scores.append(0)
            
        if close is not None and sma200 is not None:
            if close > sma200: ma_scores.append(100); reasons.append("Price > 200 SMA (Long-term Bullish)")
            else: ma_scores.append(0); reasons.append("Price < 200 SMA (Long-term Bearish)")

        ma_final = sum(ma_scores) / len(ma_scores) if ma_scores else 50

        # --- 3. Volatility / Reversion Score (0-100) ---
        bb_final = 50
        if close is not None and bb_lower is not None and bb_upper is not None:
            if close <= bb_lower:
                bb_final = 100
                reasons.append("Price touching lower Bollinger Band (Mean Reversion Buy)")
            elif close >= bb_upper:
                bb_final = 0
                reasons.append("Price touching upper Bollinger Band (Mean Reversion Sell)")

        # --- 4. Base Composite Score ---
        # 30% Oscillators, 50% Moving Averages, 20% Mean Reversion
        composite_score = (osc_final * 0.30) + (ma_final * 0.50) + (bb_final * 0.20)

        # --- 5. ADX Trend Multiplier ---
        if adx is not None and adx > 25:
            # Strong trend, push extremes further
            if composite_score > 50:
                composite_score = min(100.0, composite_score + 10)
                reasons.append(f"ADX({adx:.1f}) confirms strong bullish trend")
            elif composite_score < 50:
                composite_score = max(0.0, composite_score - 10)
                reasons.append(f"ADX({adx:.1f}) confirms strong bearish trend")

        # --- 6. SuperTrend Directional Confluence ---
        st_dir = None
        if isinstance(supertrend_raw, dict):
            st_dir = supertrend_raw.get("direction") or supertrend_raw.get("Direction")
        elif supertrend_raw is not None:
            try:
                st_dir = int(supertrend_raw)
            except (ValueError, TypeError):
                st_dir = None

        if st_dir == 1:
            if composite_score >= 50:
                composite_score = min(100.0, composite_score + 8.0)
                reasons.append("SuperTrend confirms Bullish trend")
        elif st_dir == -1:
            if composite_score <= 50:
                composite_score = max(0.0, composite_score - 8.0)
                reasons.append("SuperTrend confirms Bearish trend")

        # --- 7. Institutional Volume Expansion Confirmation ---
        if volume is not None and vol_sma_20 is not None and vol_sma_20 > 0:
            if volume >= (vol_sma_20 * 1.5):
                reasons.append("High volume expansion confirms institutional activity")

        # --- Build Signal ---
        if composite_score >= 80:
            sig_type, strength = "BUY", "STRONG"
        elif composite_score >= 60:
            sig_type, strength = "BUY", "MODERATE"
        elif composite_score <= 20:
            sig_type, strength = "SELL", "STRONG"
        elif composite_score <= 40:
            sig_type, strength = "SELL", "MODERATE"
        else:
            sig_type, strength = "HOLD", "MODERATE"
            
        if not reasons:
            reasons = ["Indicators are neutral, no strong conviction."]
            
        # Select top 3 most relevant reasons for readability
        reason_text = ". ".join(reasons[:3]) + "."

        horizon = SignalEngine._holding_horizon(sig_type, strength, timeframe)
        
        # Standardize score from 0-100 to -10 to +10 for backward compatibility with UI if needed, 
        # or just pass it as the new score metric. Let's pass the 0-100 directly but scale the 'score' field to standard -5 to 5
        # 50 -> 0. 100 -> 5. 0 -> -5
        legacy_score = (composite_score - 50) / 10.0

        # --- Dynamic Institutional Risk & Target Calculations ---
        entry_price = round(float(close), 2) if close is not None else None
        stop_loss = None
        target_1 = None
        target_2 = None
        risk_reward_ratio = None
        risk_quality = "NEUTRAL"

        if entry_price is not None and atr is not None and float(atr) > 0:
            atr_val = float(atr)
            if sig_type == "BUY":
                stop_loss = round(entry_price - (1.5 * atr_val), 2)
                risk_per_share = max(0.05, entry_price - stop_loss)
                target_1 = round(entry_price + (1.5 * risk_per_share), 2)
                target_2 = round(entry_price + (2.5 * risk_per_share), 2)
                risk_reward_ratio = round((target_1 - entry_price) / risk_per_share, 2)
                risk_quality = "OPTIMAL" if strength == "STRONG" else "ACCEPTABLE"
            elif sig_type == "SELL":
                stop_loss = round(entry_price + (1.5 * atr_val), 2)
                risk_per_share = max(0.05, stop_loss - entry_price)
                target_1 = round(entry_price - (1.5 * risk_per_share), 2)
                target_2 = round(entry_price - (2.5 * risk_per_share), 2)
                risk_reward_ratio = round((entry_price - target_1) / risk_per_share, 2)
                risk_quality = "OPTIMAL" if strength == "STRONG" else "ACCEPTABLE"

        signals.append({
            "type": sig_type,
            "strength": strength,
            "score": round(legacy_score, 1),
            "composite_rating": round(composite_score, 1),
            "reason": reason_text,
            "holding_period": horizon,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2,
            "risk_reward_ratio": risk_reward_ratio,
            "risk_quality": risk_quality,
            "indicators_used": {
                "rsi": rsi, "macd": macd, "ema9": ema9, "ema21": ema21, "adx": adx, "cci": cci, "stoch": stoch_k, "supertrend": st_dir, "atr": atr
            },
        })

        return signals

    @staticmethod
    def _holding_horizon(signal_type: str, strength: str, timeframe: str) -> dict:
        ranges = {
            "1m": (0.02, 0.25), "5m": (0.1, 0.75), "15m": (0.25, 1.5),
            "30m": (0.5, 2), "1h": (1, 5), "1d": (5, 20), "1w": (20, 60),
        }
        low, high = ranges.get(timeframe, ranges["1d"])
        if signal_type == "HOLD":
            low, high = high, high * 2
        elif strength == "STRONG":
            high = max(low, high * 0.75)
        elif strength == "WEAK":
            low, high = low * 0.75, high * 1.25
        unit = "days" if timeframe in {"1d", "1w"} else "sessions"
        return {
            "min": round(low, 2),
            "max": round(high, 2),
            "unit": unit,
            "label": f"{round(low, 1)}–{round(high, 1)} {unit}",
            "basis": f"Technical Composite Rating",
        }

signal_engine = SignalEngine()
