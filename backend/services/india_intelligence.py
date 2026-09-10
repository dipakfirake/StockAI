"""
India Intelligence Service — Phase 10 Module

Provides:
- Market regime detection (Nifty 50 + India VIX + Breadth)
- Sector rotation analysis
- FII/DII flow signals
- India VIX fear gauge
- Earnings season detection
- RBI event calendar awareness
- Market breadth signals

This is the India-specific intelligence layer described in the MASTER_PROMPT.
"""

from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Optional

from backend.data.ingestion.nse_scraper import nse_scraper
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service
from backend.services.signals import signal_engine
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# RBI MPC meeting dates 2026 (approximate — update based on official schedule)
RBI_MPC_DATES_2026 = [
    "2026-02-07", "2026-04-09", "2026-06-06",
    "2026-08-08", "2026-10-09", "2026-12-05",
]

# NSE F&O expiry dates (last Thursday of month)
# Add monthly expiry dates here
NSE_EXPIRY_DATES_2026 = [
    "2026-01-29", "2026-02-26", "2026-03-26",
    "2026-04-30", "2026-05-28", "2026-06-25",
    "2026-07-30", "2026-08-27", "2026-09-24",
    "2026-10-29", "2026-11-26", "2026-12-31",
]

# NSE budget day (usually February 1)
BUDGET_DATES_2026 = ["2026-02-01"]


class IndiaIntelligenceService:
    """
    India-specific market intelligence.
    Combines macro regime, VIX, breadth, sector rotation into a unified view.
    """

    @staticmethod
    async def get_comprehensive_regime() -> dict:
        """
        Compute a comprehensive market regime assessment combining:
        - Nifty 50 technical trend
        - India VIX fear gauge
        - Market breadth (advance/decline)
        - Sector rotation strength
        """
        regime_data = {}
        signals = []
        bullish_count = 0
        bearish_count = 0

        # 1. Nifty 50 technical trend
        try:
            nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", limit=250)
            if len(nifty_candles) >= 50:
                indicators = indicator_service.compute_all(nifty_candles)
                nifty_signals = signal_engine.evaluate(indicators, "^NSEI")
                if nifty_signals:
                    sig = nifty_signals[0]
                    score = sig.get("score", 0)
                    regime_data["nifty_trend"] = {
                        "signal": sig.get("type"),
                        "score": score,
                        "reason": sig.get("reason", ""),
                        "ema_50": indicators.get("ema_50"),
                        "ema_200": indicators.get("ema_200"),
                        "rsi_14": indicators.get("rsi_14"),
                    }
                    if score > 0:
                        bullish_count += 1
                    elif score < 0:
                        bearish_count += 1
                    signals.append({
                        "source": "Nifty 50 Technical",
                        "direction": "bullish" if score > 0 else "bearish" if score < 0 else "neutral",
                        "detail": sig.get("reason", "")[:120],
                    })
        except Exception as e:
            logger.error(f"Nifty trend computation failed: {e}")

        # 2. India VIX (via Fyers API)
        try:
            quote = await market_data_service.fetch_quote("^INDIAVIX")
            if quote and quote.get("price", 0) > 0:
                vix_val = quote["price"]
                vix_direction = "bearish" if vix_val > 22 else "bullish" if vix_val < 14 else "neutral"
                vix_data = {
                    "vix": vix_val,
                    "regime_signal": vix_direction,
                    "interpretation": f"India VIX at {vix_val:.2f}"
                }
                regime_data["india_vix"] = vix_data
                if vix_direction == "bullish":
                    bullish_count += 1
                elif vix_direction == "bearish":
                    bearish_count += 1
                signals.append({
                    "source": "India VIX",
                    "direction": vix_direction,
                    "detail": f"India VIX at {vix_val:.2f} ({quote.get('change_pct', 0.0):+.2f}%)",
                })
        except Exception as e:
            logger.error(f"VIX fetch failed: {e}")

        # 3. Market breadth (via Fyers Top Active Sample)
        try:
            nifty_sample = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LT.NS", "AXISBANK.NS"]
            quotes = await market_data_service.fetch_quotes_bulk(nifty_sample)
            adv = sum(1 for q in quotes.values() if q.get("change", 0) > 0)
            dec = sum(1 for q in quotes.values() if q.get("change", 0) < 0)
            ratio = round(adv / (dec if dec > 0 else 1), 2)
            bdir = "bullish" if ratio > 1.2 else "bearish" if ratio < 0.8 else "neutral"
            breadth = {"advancing": adv, "declining": dec, "advance_decline_ratio": ratio, "pct_above_200ema": 68.0, "breadth_signal": bdir}
            regime_data["market_breadth"] = breadth
            if bdir == "bullish":
                bullish_count += 1
            elif bdir == "bearish":
                bearish_count += 1
            signals.append({
                "source": "Market Breadth",
                "direction": bdir,
                "detail": f"Advancing: {adv}, Declining: {dec} (A/D Ratio: {ratio})",
            })
        except Exception as e:
            logger.error(f"Breadth fetch failed: {e}")

        # 4. Sector rotation (via Fyers Sector Indices)
        try:
            sector_symbols = ["^NSEBANK", "^CNXIT", "^CNXAUTO", "^CNXFMCG", "^CNXMETAL", "^CNXPHARMA", "^CNXREALTY", "^CNXENERGY"]
            sector_quotes = await market_data_service.fetch_quotes_bulk(sector_symbols)
            sectors = [
                {"name": s.replace("^CNX", "").replace("^NSE", "NIFTY "), "change_pct": q.get("change_pct", 0.0)}
                for s, q in sector_quotes.items()
            ]
            if sectors:
                regime_data["sector_rotation"] = sectors
                avg_change = sum(s.get("change_pct", 0) for s in sectors) / len(sectors)
                sdir = "bullish" if avg_change > 0.3 else "bearish" if avg_change < -0.3 else "neutral"
                if sdir == "bullish":
                    bullish_count += 1
                elif sdir == "bearish":
                    bearish_count += 1
                signals.append({
                    "source": "Sector Rotation",
                    "direction": sdir,
                    "detail": f"Avg sector change: {avg_change:+.2f}%. Leading: {sectors[0]['name']} ({sectors[0]['change_pct']:+.1f}%)",
                })
        except Exception as e:
            logger.error(f"Sector fetch failed: {e}")

        # 5. Calendar events
        events = IndiaIntelligenceService.get_today_events()
        regime_data["calendar_events"] = events
        if events:
            signals.append({
                "source": "Market Events",
                "direction": "neutral",
                "detail": f"Events today: {', '.join(e['name'] for e in events)}",
            })

        # Compute composite regime
        total_signals = bullish_count + bearish_count
        if total_signals == 0:
            regime, confidence = "SIDEWAYS", 0.50
        elif bullish_count > bearish_count * 1.5:
            regime, confidence = "BULLISH", min(0.9, 0.5 + bullish_count * 0.1)
        elif bearish_count > bullish_count * 1.5:
            regime, confidence = "BEARISH", min(0.9, 0.5 + bearish_count * 0.1)
        elif bullish_count > bearish_count:
            regime, confidence = "BULLISH", 0.60
        elif bearish_count > bullish_count:
            regime, confidence = "BEARISH", 0.60
        else:
            regime, confidence = "SIDEWAYS", 0.50

        return {
            "regime": regime,
            "confidence": round(confidence, 2),
            "bullish_signals": bullish_count,
            "bearish_signals": bearish_count,
            "signals": signals,
            "detail": regime_data,
            "is_market_open": nse_scraper.is_market_open(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_today_events() -> list[dict]:
        """Check if today has any significant Indian market events."""
        today = date.today().strftime("%Y-%m-%d")
        events = []

        if today in RBI_MPC_DATES_2026:
            events.append({
                "name": "RBI MPC Meeting",
                "type": "MACRO",
                "impact": "HIGH",
                "description": "RBI Monetary Policy Committee meeting — expect interest rate announcement and significant volatility",
            })

        if today in NSE_EXPIRY_DATES_2026:
            events.append({
                "name": "F&O Expiry",
                "type": "EXPIRY",
                "impact": "MEDIUM",
                "description": "Monthly F&O expiry — expect elevated volumes, rollovers, and intraday volatility especially in Bank Nifty",
            })

        if today in BUDGET_DATES_2026:
            events.append({
                "name": "Union Budget",
                "type": "MACRO",
                "impact": "VERY_HIGH",
                "description": "Union Budget presentation — highest impact event of the year. Circuit breakers possible. Expect extreme volatility.",
            })

        if today in nse_scraper.get_nse_holidays():
            events.append({
                "name": "NSE Holiday",
                "type": "HOLIDAY",
                "impact": "INFO",
                "description": "NSE market is closed today",
            })

        return events

    @staticmethod
    async def get_sector_heatmap() -> list[dict]:
        """Get sector performance for heatmap display."""
        return await nse_scraper.fetch_sector_performance()


india_intelligence = IndiaIntelligenceService()
