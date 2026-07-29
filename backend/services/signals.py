"""
Rule-based signal engine.

Every signal includes a human-readable reason string.
No black-box outputs. Every decision is explainable.

Signal types: BUY, SELL, HOLD, WATCH
Strength: STRONG, MODERATE, WEAK
"""

from __future__ import annotations

from typing import Optional
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


class SignalEngine:
    """
    Evaluates technical indicators and generates explainable signals.

    Rules are evaluated in priority order. First matching set wins.
    All signals include a reason string suitable for display to the user.
    """

    @staticmethod
    def evaluate(indicators: dict, symbol: str = "") -> list[dict]:
        """
        Evaluate all rules against the latest indicator values.
        Returns a list of signal dicts.
        """
        signals = []
        rsi = indicators.get("rsi_14")
        macd = indicators.get("macd", {})
        macd_val = macd.get("macd") if macd else None
        macd_sig = macd.get("signal") if macd else None
        macd_hist = macd.get("histogram") if macd else None
        ema9 = indicators.get("ema_9")
        ema21 = indicators.get("ema_21")
        ema50 = indicators.get("ema_50")
        ema200 = indicators.get("ema_200")
        bb = indicators.get("bb", {})
        bb_upper = bb.get("upper") if bb else None
        bb_lower = bb.get("lower") if bb else None
        close = indicators.get("close")
        adx = indicators.get("adx_14")
        atr = indicators.get("atr_14")
        vol = indicators.get("volume")
        vol_sma = indicators.get("vol_sma_20")

        reasons_bullish = []
        reasons_bearish = []
        score = 0  # Positive = bullish, negative = bearish

        # --- RSI rules ---
        if rsi is not None:
            if rsi < 30:
                reasons_bullish.append(f"RSI({rsi:.1f}) is in oversold territory — historically precedes a bounce")
                score += 2
            elif rsi < 40:
                reasons_bullish.append(f"RSI({rsi:.1f}) approaching oversold — watch for reversal")
                score += 1
            elif rsi > 70:
                reasons_bearish.append(f"RSI({rsi:.1f}) is in overbought territory — watch for a pullback")
                score -= 2
            elif rsi > 60:
                reasons_bearish.append(f"RSI({rsi:.1f}) approaching overbought")
                score -= 1

        # --- MACD rules ---
        if macd_val is not None and macd_sig is not None:
            if macd_hist is not None and macd_hist > 0 and macd_val > macd_sig:
                reasons_bullish.append("MACD histogram is positive and MACD is above signal — bullish momentum")
                score += 1
            elif macd_hist is not None and macd_hist < 0 and macd_val < macd_sig:
                reasons_bearish.append("MACD histogram is negative and MACD is below signal — bearish momentum")
                score -= 1

        # --- EMA crossover rules ---
        if ema9 is not None and ema21 is not None:
            if ema9 > ema21:
                reasons_bullish.append(f"EMA9({ema9:.2f}) is above EMA21({ema21:.2f}) — short-term trend is up")
                score += 1
            else:
                reasons_bearish.append(f"EMA9({ema9:.2f}) is below EMA21({ema21:.2f}) — short-term trend is down")
                score -= 1

        # --- Golden / death cross ---
        if ema50 is not None and ema200 is not None:
            if ema50 > ema200:
                reasons_bullish.append(f"Golden cross: EMA50({ema50:.2f}) > EMA200({ema200:.2f}) — long-term bull trend")
                score += 2
            else:
                reasons_bearish.append(f"Death cross: EMA50({ema50:.2f}) < EMA200({ema200:.2f}) — long-term bear trend")
                score -= 2

        # --- Bollinger Band rules ---
        if close is not None and bb_lower is not None and bb_upper is not None:
            if close <= bb_lower:
                reasons_bullish.append(f"Price({close:.2f}) touched lower Bollinger Band({bb_lower:.2f}) — mean reversion opportunity")
                score += 1
            elif close >= bb_upper:
                reasons_bearish.append(f"Price({close:.2f}) touched upper Bollinger Band({bb_upper:.2f}) — potential reversal")
                score -= 1

        # --- ADX trend strength ---
        if adx is not None and adx > 25:
            trend_desc = "strong bullish" if score > 0 else "strong bearish"
            direction = reasons_bullish if score > 0 else reasons_bearish
            direction.append(f"ADX({adx:.1f}) > 25 — {trend_desc} trend is confirmed")

        # --- Volume confirmation ---
        if vol is not None and vol_sma is not None and vol > vol_sma * 1.5:
            if score > 0:
                reasons_bullish.append(f"Volume({vol:,}) is 1.5x above 20-day average({vol_sma:,.0f}) — bullish move confirmed")
                score += 1
            else:
                reasons_bearish.append(f"Volume({vol:,}) is 1.5x above 20-day average({vol_sma:,.0f}) — bearish move confirmed")
                score -= 1

        # --- Build signal ---
        if score >= 4:
            sig_type, strength = "BUY", "STRONG"
            reasons = reasons_bullish
        elif score >= 2:
            sig_type, strength = "BUY", "MODERATE"
            reasons = reasons_bullish
        elif score >= 1:
            sig_type, strength = "WATCH", "WEAK"
            reasons = reasons_bullish[:2] if reasons_bullish else ["Mild bullish bias — monitor closely"]
        elif score <= -4:
            sig_type, strength = "SELL", "STRONG"
            reasons = reasons_bearish
        elif score <= -2:
            sig_type, strength = "SELL", "MODERATE"
            reasons = reasons_bearish
        elif score <= -1:
            sig_type, strength = "WATCH", "WEAK"
            reasons = reasons_bearish[:2] if reasons_bearish else ["Mild bearish bias — monitor closely"]
        else:
            sig_type, strength = "HOLD", "MODERATE"
            reasons = ["No strong signal — indicators are neutral"]

        reason_text = ". ".join(reasons) + "."

        signals.append({
            "type": sig_type,
            "strength": strength,
            "score": score,
            "reason": reason_text,
            "indicators_used": {
                k: indicators.get(k)
                for k in ["rsi_14", "macd", "ema_9", "ema_21", "ema_50", "ema_200", "adx_14"]
            },
        })

        return signals


signal_engine = SignalEngine()
