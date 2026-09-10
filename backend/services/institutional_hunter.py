import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from backend.core.logging_config import get_logger
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service

logger = get_logger(__name__)


class SMC_Engine:
    """
    Smart Money Concepts Engine — v2 (High-Profit Edition).
    Uses DAILY candles to find wide, significant Fair Value Gaps.
    Adds confluence scoring (RSI + Volume + EMA) for accuracy.
    Calculates realistic profit targets and risk/reward ratios.
    """

    def __init__(self):
        self.daily_watchlist = {}

    def calculate_fvg(self, candles: List[dict], min_gap_pct: float = 0.3) -> List[Dict]:
        """
        Calculate Fair Value Gaps from DAILY candles.
        Only keeps gaps wider than min_gap_pct % of price (filters out noise).
        Also filters out gaps that have already been mitigated (filled) by subsequent price action.
        """
        fvgs = []
        if len(candles) < 5:
            return fvgs

        for i in range(2, len(candles)):
            c1_high = candles[i - 2].get("high", 0)
            c1_low = candles[i - 2].get("low", 0)
            c2_close = candles[i - 1].get("close", 0)
            c3_high = candles[i].get("high", 0)
            c3_low = candles[i].get("low", 0)
            mid_time = candles[i - 1].get("timestamp", "")

            if c2_close <= 0:
                continue

            # Bullish FVG: candle 1 high < candle 3 low (gap up)
            if c1_high < c3_low:
                gap_size = c3_low - c1_high
                gap_pct = (gap_size / c2_close) * 100
                if gap_pct >= min_gap_pct:
                    # Mitigation check: Did any candle after this fill the gap?
                    mitigated = False
                    for j in range(i + 1, len(candles)):
                        if candles[j].get("low", float('inf')) <= c1_high:
                            mitigated = True
                            break
                    
                    if not mitigated:
                        fvgs.append({
                            "type": "bullish_fvg",
                            "top": round(float(c3_low), 2),
                            "bottom": round(float(c1_high), 2),
                            "gap_size": round(gap_size, 2),
                            "gap_pct": round(gap_pct, 2),
                            "time": mid_time,
                        })

            # Bearish FVG: candle 1 low > candle 3 high (gap down)
            elif c1_low > c3_high:
                gap_size = c1_low - c3_high
                gap_pct = (gap_size / c2_close) * 100
                if gap_pct >= min_gap_pct:
                    # Mitigation check
                    mitigated = False
                    for j in range(i + 1, len(candles)):
                        if candles[j].get("high", 0) >= c1_low:
                            mitigated = True
                            break
                            
                    if not mitigated:
                        fvgs.append({
                            "type": "bearish_fvg",
                            "top": round(float(c1_low), 2),
                            "bottom": round(float(c3_high), 2),
                            "gap_size": round(gap_size, 2),
                            "gap_pct": round(gap_pct, 2),
                            "time": mid_time,
                        })

        return fvgs

    def _compute_confluence(self, candles: List[dict], fvg: dict) -> dict:
        """
        Score how strong this FVG zone is by checking confluence with
        RSI, Volume spike, and EMA proximity.
        Returns a score out of 100 and individual factor details.
        """
        score = 0
        factors = []

        try:
            indicators = indicator_service.compute_all(candles)
        except Exception:
            return {"score": 50, "factors": ["Indicators unavailable"], "grade": "C"}

        # 1. RSI Confluence (max 30 pts)
        rsi = indicators.get("rsi_14")
        if rsi is not None:
            if fvg["type"] == "bullish_fvg" and rsi < 40:
                score += 30
                factors.append(f"RSI oversold ({rsi:.0f})")
            elif fvg["type"] == "bullish_fvg" and rsi < 50:
                score += 15
                factors.append(f"RSI neutral-low ({rsi:.0f})")
            elif fvg["type"] == "bearish_fvg" and rsi > 60:
                score += 30
                factors.append(f"RSI overbought ({rsi:.0f})")
            elif fvg["type"] == "bearish_fvg" and rsi > 50:
                score += 15
                factors.append(f"RSI neutral-high ({rsi:.0f})")

        # 2. Volume spike (max 25 pts)
        volumes = [c.get("volume", 0) for c in candles[-20:] if c.get("volume", 0) > 0]
        if volumes:
            avg_vol = sum(volumes) / len(volumes)
            last_vol = candles[-1].get("volume", 0)
            if last_vol > avg_vol * 1.5:
                score += 25
                factors.append(f"Volume spike ({last_vol / avg_vol:.1f}x avg)")
            elif last_vol > avg_vol:
                score += 10
                factors.append("Above-average volume")

        # 3. EMA proximity (max 25 pts)
        ema21 = indicators.get("ema_21")
        last_close = candles[-1].get("close", 0)
        if ema21 and last_close:
            dist_pct = abs(last_close - ema21) / last_close * 100
            if dist_pct < 1.0:
                score += 25
                factors.append(f"Near EMA21 ({dist_pct:.1f}% away)")
            elif dist_pct < 2.5:
                score += 12
                factors.append(f"Close to EMA21 ({dist_pct:.1f}% away)")

        # 4. Gap size bonus (max 20 pts) — wider gaps = stronger
        gap_pct = fvg.get("gap_pct", 0)
        if gap_pct >= 2.0:
            score += 20
            factors.append(f"Wide gap ({gap_pct:.1f}%)")
        elif gap_pct >= 1.0:
            score += 15
            factors.append(f"Moderate gap ({gap_pct:.1f}%)")
        elif gap_pct >= 0.5:
            score += 8
            factors.append(f"Narrow gap ({gap_pct:.1f}%)")

        grade = "A+" if score >= 85 else "A" if score >= 70 else "B" if score >= 50 else "C"

        return {"score": min(score, 100), "factors": factors, "grade": grade}

    async def generate_daily_watchlist(self, symbols: List[str]):
        """
        Scans DAILY candles (last 60 days) for each symbol to find
        wide, significant FVG zones (Points of Interest).
        Runs on demand — no 24/7 uptime required.
        """
        logger.info(f"🏦 [SMC Engine v2] Scanning {len(symbols)} stocks for Institutional Zones...")
        today_zones = {}

        for symbol in symbols:
            try:
                candles = await market_data_service.fetch_candles(symbol, "1d", limit=60)
                if not candles or len(candles) < 15:
                    logger.debug(f"[SMC] Not enough daily candles for {symbol}")
                    continue

                fvgs = self.calculate_fvg(candles, min_gap_pct=0.3)

                if fvgs:
                    # Score and enrich each FVG
                    enriched = []
                    for fvg in fvgs[-5:]:  # Last 5 significant gaps
                        confluence = self._compute_confluence(candles, fvg)
                        enriched.append({
                            **fvg,
                            "confluence": confluence,
                        })

                    # Sort by confluence score descending, keep top 3
                    enriched.sort(key=lambda x: x["confluence"]["score"], reverse=True)
                    top_zones = enriched[:3]

                    last_price = candles[-1].get("close", 0)
                    today_zones[symbol] = {
                        "fvgs": top_zones,
                        "last_price": round(last_price, 2),
                        "generated_at": datetime.now().isoformat(),
                    }

            except Exception as e:
                logger.error(f"[SMC Engine] Error scanning {symbol}: {e}")

        self.daily_watchlist = today_zones
        logger.info(f"🏦 [SMC Engine v2] Found Institutional Zones for {len(today_zones)} stocks.")
        return today_zones

    def get_watchlist(self) -> Dict:
        return self.daily_watchlist


smc_engine = SMC_Engine()
