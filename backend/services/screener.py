"""
AI Swing Trade Screener Service
Scans top market stocks, analyzes technicals, fundamentals, and NLP sentiment,
and generates strict institutional-grade trade setups with defined risk/reward.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import numpy as np

from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service, candles_to_df
from backend.services.signals import signal_engine
from backend.services.nlp_engine import nlp_engine_service

logger = get_logger(__name__)

# Subset of highly liquid Nifty 50 stocks to prevent Yahoo Finance IP bans
NIFTY_UNIVERSE = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
    "BAJFINANCE.NS", "HCLTECH.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS",
    "KOTAKBANK.NS", "SUNPHARMA.NS", "TITAN.NS", "M&M.NS", "ULTRACEMCO.NS",
    "TATAMOTORS.NS", "NTPC.NS", "TATASTEEL.NS", "POWERGRID.NS", "BAJAJFINSV.NS"
]


class ScreenerService:
    @staticmethod
    async def run_screener(symbols: list[str] = None) -> dict:
        """
        Run the multi-factor screener on a list of symbols.
        Returns a ranked list of top trade setups.
        """
        if not symbols:
            symbols = NIFTY_UNIVERSE

        logger.info(f"Starting Swing Trade Screener for {len(symbols)} symbols...")
        
        # We process in batches to avoid rate limits
        batch_size = 5
        all_results = []
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = [ScreenerService._analyze_symbol(sym) for sym in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in results:
                if isinstance(res, dict) and res.get("total_score", 0) > 0:
                    all_results.append(res)
                    
            await asyncio.sleep(1.0)  # Rate limit protection

        # Sort by total conviction score
        all_results.sort(key=lambda x: x["total_score"], reverse=True)
        
        # Only keep top setups (Score > 65)
        top_setups = [r for r in all_results if r["total_score"] >= 65]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stocks_scanned": len(symbols),
            "setups_found": len(top_setups),
            "top_setups": top_setups,
            "all_results": all_results
        }

    @staticmethod
    async def _analyze_symbol(symbol: str) -> dict:
        """Analyze a single symbol across all three dimensions."""
        cache_key = f"screener_analysis:{symbol}"
        cached = await cache_get(cache_key)
        if cached:
            return cached

        try:
            # 1. Fetch Data
            # Use limit=2000 to share the cache with get_stock_insight in stocks.py
            candles_task = market_data_service.fetch_candles(symbol, "1d", limit=2000)
            info_task = market_data_service.get_stock_info(symbol)
            events_task = market_data_service.fetch_corporate_events(symbol)
            from backend.data.ingestion.news_scraper import fetch_stock_news
            news_task = fetch_stock_news(symbol)
            
            candles, info, events, news = await asyncio.gather(candles_task, info_task, events_task, news_task)
            
            if not candles or len(candles) < 50:
                return {"symbol": symbol, "error": "Insufficient candle data"}
                
            info = info or {}
            
            # 2. Technical Score (40% Weight)
            indicators = indicator_service.compute_all(candles)
            signals = signal_engine.evaluate(indicators, symbol)
            sig = signals[0] if signals else {}
            
            # Extract the raw 0-100 technical score from the new signal engine
            tech_raw = sig.get("composite_rating", 50)
            
            # 3. Fundamental Score (35% Weight)
            # Evaluate basic health metrics
            fund_score = 50
            info = info or {}
            
            def _safe_float(v):
                try: return float(v)
                except (ValueError, TypeError): return 0.0
                
            roe = _safe_float(info.get("roe", 0))
            if roe > 0.15: fund_score += 15
            elif roe < 0: fund_score -= 15
            
            debt_eq = _safe_float(info.get("debt_to_equity", 0))
            if debt_eq < 1.0: fund_score += 10
            elif debt_eq > 2.0: fund_score -= 10
                
            rev_growth = _safe_float(info.get("revenue_growth", 0))
            if rev_growth > 0.10: fund_score += 10
            
            pe = _safe_float(info.get("pe_ratio", 0))
            if 0 < pe < 25: fund_score += 15
            elif pe > 50: fund_score -= 10
            
            if events.get("dividends"):
                fund_score += 5  # Bonus for returning capital to shareholders
                
            if events.get("earnings_date"):
                try:
                    edate = datetime.fromisoformat(events["earnings_date"][:10]).replace(tzinfo=timezone.utc)
                    if 0 < (edate - datetime.now(timezone.utc)).days <= 14:
                        fund_score -= 5  # Slight penalty for upcoming earnings risk/volatility
                except:
                    pass
            
            fund_score = max(0, min(100, fund_score))
            
            # 4. News Sentiment Score (25% Weight)
            nlp_result = nlp_engine_service.analyze_headlines(news, events=events)
            compound = nlp_result.get("compound_score", 0.0)
            # Normalize -1 to +1 into 0 to 100
            sentiment_score = ((compound + 1) / 2) * 100
            sentiment_score = max(0, min(100, sentiment_score))
            
            # 5. Composite Conviction Score
            total_score = (tech_raw * 0.40) + (fund_score * 0.35) + (sentiment_score * 0.25)
            
            # 6. Generate Trade Setup
            current_price = candles[-1]["close"]
            raw_atr = indicators.get("atr_14")
            # Enforce a minimum ATR (e.g. 1.5% of price) so target/SL are never exactly entry price
            atr = max(float(raw_atr) if raw_atr is not None else 0.0, current_price * 0.015)
            
            if total_score >= 60:
                action = "BUY"
                stop_loss = current_price - (1.5 * atr)
                target = current_price + (3.0 * atr)
            elif total_score <= 40:
                action = "SELL"
                stop_loss = current_price + (1.5 * atr)
                target = current_price - (3.0 * atr)
            else:
                action = "HOLD"
                stop_loss = current_price - (1.5 * atr)
                target = current_price + (3.0 * atr)

            gain_pct = abs((target - current_price) / current_price) * 100 if current_price > 0 else 0
            risk_pct = abs((current_price - stop_loss) / current_price) * 100 if current_price > 0 else 0
            
            # Estimate holding days (Target / average daily range)
            base_days = max(3, int(round(abs(target - current_price) / (atr if atr > 0 else 1))))
            max_days = base_days + max(3, int(base_days * 0.5))
            hold_time = f"{base_days} to {max_days} Days"

            result = {
                "symbol": symbol,
                "name": info.get("name", symbol),
                "action": action,
                "total_score": round(total_score, 1),
                "scores": {
                    "technical": round(tech_raw, 1),
                    "fundamental": round(fund_score, 1),
                    "sentiment": round(sentiment_score, 1)
                },
                "trade_plan": {
                    "entry_price": round(current_price, 2),
                    "stop_loss": round(stop_loss, 2),
                    "target_price": round(target, 2),
                    "expected_gain_pct": round(gain_pct, 2),
                    "risk_pct": round(risk_pct, 2),
                    "reward_to_risk": round(gain_pct / risk_pct, 2) if risk_pct > 0 else 0,
                    "estimated_hold_time": hold_time
                },
                "news_sentiment": nlp_result.get("overall_sentiment", "NEUTRAL")
            }
            
            # Cache for 15 minutes
            await cache_set(cache_key, result, ttl=900)
            return result
            
        except Exception as e:
            logger.error(f"Screener failed for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "symbol": symbol,
                "name": symbol,
                "error": str(e),
                "action": "HOLD",
                "total_score": 0.0,
                "scores": {"technical": 0, "fundamental": 0, "sentiment": 0},
                "trade_plan": None,
                "news_sentiment": "NEUTRAL"
            }

screener_service = ScreenerService()
