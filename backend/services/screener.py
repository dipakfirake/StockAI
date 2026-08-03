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
        try:
            # 1. Fetch Data
            candles_task = market_data_service.fetch_candles(symbol, "1d", limit=200)
            info_task = market_data_service.get_stock_info(symbol)
            news_task = market_data_service.fetch_news(symbol)
            
            candles, info, news = await asyncio.gather(candles_task, info_task, news_task)
            
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
            roe = info.get("roe", 0) or 0
            debt_eq = info.get("debt_to_equity", 0) or 0
            rev_growth = info.get("revenue_growth", 0) or 0
            pe = info.get("pe_ratio", 0) or 0
            
            if roe > 0.15: fund_score += 15
            elif roe > 0.05: fund_score += 5
            
            if debt_eq > 0 and debt_eq < 1.0: fund_score += 10
            elif debt_eq > 2.0: fund_score -= 10
            
            if rev_growth > 0: fund_score += 10
            
            if pe > 0 and pe < 25: fund_score += 15
            elif pe > 50: fund_score -= 10
            
            fund_score = max(0, min(100, fund_score))
            
            # 4. News Sentiment Score (25% Weight)
            nlp_result = nlp_engine_service.analyze_headlines(news)
            compound = nlp_result.get("compound_score", 0.0)
            # Normalize -1 to +1 into 0 to 100
            sentiment_score = ((compound + 1) / 2) * 100
            sentiment_score = max(0, min(100, sentiment_score))
            
            # 5. Composite Conviction Score
            total_score = (tech_raw * 0.40) + (fund_score * 0.35) + (sentiment_score * 0.25)
            
            # 6. Generate Trade Setup
            current_price = candles[-1]["close"]
            atr = indicators.get("atr_14", current_price * 0.02) # Default to 2% if missing
            
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

            gain_pct = abs((target - current_price) / current_price) * 100
            risk_pct = abs((current_price - stop_loss) / current_price) * 100
            
            # Estimate holding days (Target / average daily range)
            hold_days = max(3, int(round(abs(target - current_price) / (atr if atr > 0 else 1))))
            hold_time = f"{hold_days} to {hold_days + 10} Days"

            return {
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
            
        except Exception as e:
            logger.error(f"Screener failed for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

screener_service = ScreenerService()
