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
from backend.core.market_hours import get_dynamic_screener_ttl
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service, candles_to_df
from backend.services.signals import signal_engine
from backend.services.nlp_engine import nlp_engine_service
from backend.services.ai_engine import ai_engine_service

logger = get_logger(__name__)

# Sector Universes for targeted market screening
SECTOR_UNIVERSES: dict[str, list[str]] = {
    "NIFTY_50": [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
        "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "HINDUNILVR.NS", "LT.NS",
        "AXISBANK.NS", "KOTAKBANK.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS",
        "ULTRACEMCO.NS", "ASIANPAINT.NS", "NTPC.NS", "TATAMOTORS.NS", "BAJFINANCE.NS",
        "POWERGRID.NS", "M&M.NS", "ADANIENT.NS", "TATASTEEL.NS", "COALINDIA.NS"
    ],
    "BANKING": [
        "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS",
        "INDUSINDBK.NS", "AUBANK.NS", "BANDHANBNK.NS", "BANKBARODA.NS", "PNB.NS"
    ],
    "IT": [
        "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS",
        "LTIM.NS", "COFORGE.NS", "PERSISTENT.NS"
    ],
    "AUTO": [
        "TATAMOTORS.NS", "MARUTI.NS", "M&M.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
        "HEROMOTOCO.NS", "TVSMOTOR.NS", "ASHOKLEY.NS"
    ],
    "PHARMA": [
        "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS",
        "LUPIN.NS", "AUROPHARMA.NS"
    ],
    "ENERGY": [
        "RELIANCE.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "BPCL.NS",
        "COALINDIA.NS", "IOC.NS", "GAIL.NS"
    ],
    "FMCG": [
        "ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "BRITANNIA.NS", "TATACONSUM.NS",
        "DABUR.NS", "MARICO.NS", "GODREJCP.NS"
    ],
    "METAL": [
        "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS",
        "JINDALSTEL.NS", "NMDC.NS", "NATIONALUM.NS"
    ],
    "MID_CAP": [
        "POLYCAB.NS", "DIXON.NS", "PERSISTENT.NS", "COFORGE.NS", "CAMS.NS",
        "FEDERALBNK.NS", "BEL.NS", "CUMMINSIND.NS", "GODREJPROP.NS", "PIIND.NS"
    ],
    "SMALL_CAP": [
        "SUZLON.NS", "CDSL.NS", "BSE.NS", "ANGELONE.NS", "MAZDOCK.NS",
        "KAYNES.NS", "KALYANKJIL.NS", "RBLBANK.NS", "BSOFT.NS", "ZENTEC.NS"
    ]
}

# Default highly liquid Nifty universe
NIFTY_UNIVERSE = SECTOR_UNIVERSES["NIFTY_50"]


class ScreenerService:
    @staticmethod
    async def run_screener(
        symbols: list[str] = None,
        sector: str = None,
        force_refresh: bool = False
    ) -> dict:
        """
        Run the multi-factor screener on a list of symbols or sector universe.
        Returns categorized lists of BUY, SELL, and HOLD setups with summary stats.
        """
        norm_sector = sector.upper().replace(" ", "_") if sector else "DEFAULT"
        if not symbols:
            symbols = SECTOR_UNIVERSES.get(norm_sector, NIFTY_UNIVERSE)

        cache_key = f"screener_results_{norm_sector}"
        if not force_refresh:
            cached = await cache_get(cache_key)
            if cached and isinstance(cached, dict) and "buy_stocks" in cached:
                logger.info(f"Returning cached screener results for {norm_sector}")
                return cached

        logger.info(f"Starting Swing Trade Screener for {len(symbols)} symbols ({norm_sector})...")
        
        # We process in batches with rate-limit guards
        batch_size = 6
        all_results = []
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            tasks = [ScreenerService._analyze_symbol(sym, force_refresh=force_refresh) for sym in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res in results:
                if isinstance(res, dict) and res.get("total_score", 0) > 0 and not res.get("error"):
                    all_results.append(res)
                    
            if i + batch_size < len(symbols):
                await asyncio.sleep(0.4)

        # Categorize into explicit trading lists
        buy_stocks = [r for r in all_results if r.get("action") == "BUY"]
        buy_stocks.sort(key=lambda x: x.get("total_score", 0), reverse=True)

        sell_stocks = [r for r in all_results if r.get("action") == "SELL"]
        sell_stocks.sort(key=lambda x: x.get("total_score", 0))  # lowest score / strongest sell first

        hold_stocks = [r for r in all_results if r.get("action") == "HOLD"]
        hold_stocks.sort(key=lambda x: x.get("total_score", 0), reverse=True)

        # Sort all results by score descending
        all_results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
        top_setups = [r for r in all_results if r.get("total_score", 0) >= 65]

        # Calculate institutional summary metrics
        buy_gains = [r["trade_plan"]["expected_gain_pct"] for r in buy_stocks if r.get("trade_plan") and r["trade_plan"].get("expected_gain_pct")]
        buy_rrs = [r["trade_plan"]["reward_to_risk"] for r in buy_stocks if r.get("trade_plan") and r["trade_plan"].get("reward_to_risk")]
        sell_drops = [r["trade_plan"]["expected_gain_pct"] for r in sell_stocks if r.get("trade_plan") and r["trade_plan"].get("expected_gain_pct")]

        summary = {
            "total_scanned": len(symbols),
            "valid_results": len(all_results),
            "buy_count": len(buy_stocks),
            "sell_count": len(sell_stocks),
            "hold_count": len(hold_stocks),
            "avg_buy_gain_pct": round(float(np.mean(buy_gains)), 2) if buy_gains else 0.0,
            "avg_buy_rr": round(float(np.mean(buy_rrs)), 2) if buy_rrs else 0.0,
            "avg_sell_drop_pct": round(float(np.mean(sell_drops)), 2) if sell_drops else 0.0,
            "market_breadth": "BULLISH" if len(buy_stocks) > len(sell_stocks) else ("BEARISH" if len(sell_stocks) > len(buy_stocks) else "NEUTRAL"),
            "top_buy_pick": buy_stocks[0]["symbol"] if buy_stocks else None,
            "top_sell_pick": sell_stocks[0]["symbol"] if sell_stocks else None,
        }

        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sector": norm_sector,
            "total_scanned": len(symbols),
            "stocks_scanned": len(symbols),
            "setups_found": len(top_setups),
            "summary": summary,
            "buy_stocks": buy_stocks,
            "sell_stocks": sell_stocks,
            "hold_stocks": hold_stocks,
            "top_setups": top_setups,
            "all_results": all_results
        }

        # Dynamic market-hours cache (60s open, 1 hour closed)
        await cache_set(cache_key, output, ttl=get_dynamic_screener_ttl())
        return output

    @staticmethod
    async def _analyze_symbol(symbol: str, force_refresh: bool = False) -> dict:
        """Analyze a single symbol across all three dimensions."""
        cache_key = f"screener_analysis:{symbol}"
        if not force_refresh:
            cached = await cache_get(cache_key)
            if cached:
                return cached

        try:
            # 1. Fetch Data
            # Use limit=250 (approx 1 year of daily candles) which is optimal for swing trade indicators (EMA 200, ATR 14, RSI 14)
            candles_task = market_data_service.fetch_candles(symbol, "1d", limit=250)
            quote_task = market_data_service.fetch_quote(symbol)
            info_task = market_data_service.get_stock_info(symbol)
            events_task = market_data_service.fetch_corporate_events(symbol)
            from backend.data.ingestion.news_scraper import fetch_stock_news
            news_task = fetch_stock_news(symbol)
            
            candles, quote, info, events, news = await asyncio.gather(
                candles_task, quote_task, info_task, events_task, news_task, return_exceptions=True
            )
            
            if isinstance(candles, Exception) or not candles:
                return {"symbol": symbol, "error": "Insufficient data"}
            if isinstance(quote, Exception): quote = {}
            if isinstance(info, Exception): info = {}
            if isinstance(events, Exception): events = {}
            if isinstance(news, Exception): news = []

            # Synchronize candle tip with live quote to ensure latest bar and indicators reflect CMP
            if quote:
                candles = market_data_service.synchronize_candle_tip(candles, quote)

            indicators = indicator_service.compute_all(candles) if len(candles) >= 30 else {}
            
            # 2.5 Market Relative Strength (Accuracy Upgrade)
            if indicators:
                try:
                    nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", limit=50)
                    if nifty_candles and len(nifty_candles) >= 20:
                        nifty_indicators = indicator_service.compute_all(nifty_candles)
                        if len(nifty_indicators) > 0 and 'price_return_20d' in nifty_indicators:
                            nifty_return_20d = nifty_indicators.get("price_return_20d", 0.0)
                            stock_return_20d = indicators.get("price_return_20d", 0.0)
                            indicators["rs_momentum_20d"] = stock_return_20d - nifty_return_20d
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"Failed to fetch Nifty for RS: {e}")
            
            signals = signal_engine.evaluate(indicators, symbol)
            sig = signals[0] if signals else {}
            
            # Extract the raw 0-100 technical score from the new signal engine
            tech_raw = sig.get("composite_rating", 50)
            
            # 3. AI ML Score (Tri-Model Ensemble: LightGBM + BiLSTM + Transformer)
            ai_res = ai_engine_service.score(
                indicators if indicators else {},
                symbol=symbol,
                compute_shap=True,
                candles=candles if isinstance(candles, list) else None,
            )
            
            # 4. Fundamental Score (35% Weight)
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
            # Prioritize live market quote price for exact real-time entry price
            live_price = float(quote.get("price", 0.0)) if quote and quote.get("price") else 0.0
            last_candle_price = float(candles[-1]["close"]) if candles else 0.0
            current_price = live_price if live_price > 0 else last_candle_price
            raw_atr = indicators.get("atr_14") if indicators else 0.0
            # Enforce a minimum ATR (e.g. 1.5% of price) so target/SL are never exactly entry price
            atr = max(float(raw_atr) if raw_atr is not None else 0.0, current_price * 0.015)
            
            # Structural reference levels for optimal entry analysis
            ema_21 = float(indicators.get("ema_21") or 0.0) if indicators else 0.0
            ema_9 = float(indicators.get("ema_9") or 0.0) if indicators else 0.0
            bb = indicators.get("bb") or {}
            bb_mid = float(bb.get("middle") or 0.0)
            
            recent_lows = [float(c["low"]) for c in candles[-10:] if isinstance(c, dict) and "low" in c] if candles else []
            recent_highs = [float(c["high"]) for c in candles[-10:] if isinstance(c, dict) and "high" in c] if candles else []
            swing_low = min(recent_lows) if recent_lows else current_price - (1.0 * atr)
            swing_high = max(recent_highs) if recent_highs else current_price + (1.0 * atr)

            if total_score >= 60:
                action = "BUY"
                conviction_scale = (total_score - 60) / 40.0  # 0.0 to 1.0
                target_mult = 2.0 + (2.0 * conviction_scale)
                sl_mult = 1.0 + (0.5 * conviction_scale)
                stop_loss = max(0.05, current_price - (sl_mult * atr))
                t1 = max(0.05, current_price + (1.5 * atr))
                t2 = max(0.05, current_price + (target_mult * atr))
                t3 = max(0.05, current_price + (3.5 * atr))
                target = t2

                ref_support = ema_21 if ema_21 > 0 else (bb_mid if bb_mid > 0 else current_price - (0.5 * atr))
                if current_price > ref_support + (0.45 * atr):
                    entry_type = "PULLBACK_DIP"
                    optimal_entry_price = max(ref_support, current_price - (0.45 * atr))
                    optimal_entry_price = round(optimal_entry_price, 2)
                    entry_zone = f"₹{optimal_entry_price - 0.15*atr:.2f} – ₹{optimal_entry_price + 0.15*atr:.2f} (Dip to 21-EMA)"
                    entry_advice = f"Stock is extended above 21-EMA. Optimal entry on a minor pullback to ₹{optimal_entry_price:.2f} for max profit & lower risk."
                elif swing_high - current_price <= (0.25 * atr) and current_price >= swing_high * 0.99:
                    entry_type = "BREAKOUT"
                    optimal_entry_price = round(swing_high + (0.15 * atr), 2)
                    entry_zone = f"Above ₹{optimal_entry_price:.2f} (Breakout Confirmation)"
                    entry_advice = f"Testing resistance at ₹{swing_high:.2f}. Enter on confirmed volume breakout above ₹{optimal_entry_price:.2f}."
                else:
                    entry_type = "MARKET_CMP"
                    optimal_entry_price = round(current_price, 2)
                    entry_zone = f"₹{current_price - 0.15*atr:.2f} – ₹{current_price + 0.15*atr:.2f} (Current Market Level)"
                    entry_advice = "Price is at the optimal accumulation zone near support. Suitable to enter at current market price."

            elif total_score <= 40:
                action = "SELL"
                conviction_scale = (40 - total_score) / 40.0  # 0.0 to 1.0
                target_mult = 2.0 + (2.0 * conviction_scale)
                sl_mult = 1.0 + (0.5 * conviction_scale)
                stop_loss = max(0.05, current_price + (sl_mult * atr))
                t1 = max(0.05, current_price - (1.5 * atr))
                t2 = max(0.05, current_price - (target_mult * atr))
                t3 = max(0.05, current_price - (3.5 * atr))
                target = t2

                ref_resistance = ema_21 if ema_21 > 0 else (bb_mid if bb_mid > 0 else current_price + (0.5 * atr))
                if current_price < ref_resistance - (0.45 * atr):
                    entry_type = "RALLY_SELL"
                    optimal_entry_price = min(ref_resistance, current_price + (0.45 * atr))
                    optimal_entry_price = round(optimal_entry_price, 2)
                    entry_zone = f"₹{optimal_entry_price - 0.15*atr:.2f} – ₹{optimal_entry_price + 0.15*atr:.2f} (Pullback to 21-EMA)"
                    entry_advice = f"Oversold bounce expected. Optimal short entry on rally to ₹{optimal_entry_price:.2f}."
                elif current_price - swing_low <= (0.25 * atr):
                    entry_type = "BREAKDOWN"
                    optimal_entry_price = round(swing_low - (0.15 * atr), 2)
                    entry_zone = f"Below ₹{optimal_entry_price:.2f} (Breakdown Confirmation)"
                    entry_advice = f"Testing floor at ₹{swing_low:.2f}. Enter short on breakdown below ₹{optimal_entry_price:.2f}."
                else:
                    entry_type = "MARKET_CMP"
                    optimal_entry_price = round(current_price, 2)
                    entry_zone = f"₹{current_price - 0.15*atr:.2f} – ₹{current_price + 0.15*atr:.2f} (Current Market Level)"
                    entry_advice = "Breakdown momentum active. Sell/Short at current market price."

            else:
                action = "HOLD"
                stop_loss = max(0.05, current_price - (1.2 * atr))
                t1 = max(0.05, current_price + (0.8 * atr))
                t2 = max(0.05, current_price + (1.2 * atr))
                t3 = max(0.05, current_price + (1.8 * atr))
                target = t2
                entry_type = "CONSOLIDATION"
                optimal_entry_price = round(current_price, 2)
                entry_zone = f"Support: ₹{stop_loss:.2f} | Resistance: ₹{target:.2f}"
                entry_advice = "Range-bound consolidation. Avoid fresh entries in channel midpoint; wait for breakout or boundary test."

            risk_amount = abs(current_price - stop_loss)
            gain_pct = abs((target - current_price) / current_price) * 100 if current_price > 0 else 0.0
            risk_pct = abs((current_price - stop_loss) / current_price) * 100 if current_price > 0 else 0.0

            optimal_risk_amount = abs(optimal_entry_price - stop_loss)
            optimal_gain_pct = abs((target - optimal_entry_price) / optimal_entry_price) * 100 if optimal_entry_price > 0 else gain_pct
            optimal_risk_pct = abs((optimal_entry_price - stop_loss) / optimal_entry_price) * 100 if optimal_entry_price > 0 else risk_pct
            optimal_rr = round(optimal_gain_pct / optimal_risk_pct, 2) if optimal_risk_pct > 0 else 0.0
            
            targets_breakdown = [
                {
                    "level": "T1 (Conservative)",
                    "price": round(t1, 2),
                    "gain_pct": round(abs(t1 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t1 - current_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                },
                {
                    "level": "T2 (Primary / Optimal)",
                    "price": round(t2, 2),
                    "gain_pct": round(abs(t2 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t2 - current_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                },
                {
                    "level": "T3 (Extended Breakout)",
                    "price": round(t3, 2),
                    "gain_pct": round(abs(t3 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t3 - current_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                }
            ]

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
                    "current_price": round(current_price, 2),
                    "entry_price": round(current_price, 2),
                    "optimal_entry_price": round(optimal_entry_price, 2),
                    "entry_type": entry_type,
                    "entry_zone": entry_zone,
                    "entry_advice": entry_advice,
                    "stop_loss": round(stop_loss, 2),
                    "target_price": round(target, 2),
                    "target_1": round(t1, 2),
                    "target_2": round(t2, 2),
                    "target_3": round(t3, 2),
                    "risk_amount": round(risk_amount, 2),
                    "expected_gain_pct": round(gain_pct, 2),
                    "risk_pct": round(risk_pct, 2),
                    "reward_to_risk": round(gain_pct / risk_pct, 2) if risk_pct > 0 else 0.0,
                    "optimal_expected_gain_pct": round(optimal_gain_pct, 2),
                    "optimal_reward_to_risk": optimal_rr,
                    "estimated_hold_time": hold_time,
                    "targets": targets_breakdown,
                },
                "news_sentiment": nlp_result.get("overall_sentiment", "NEUTRAL"),
                "ml_score": ai_res
            }
            
            # Dynamic market-hours cache (60s open, 1 hour closed)
            await cache_set(cache_key, result, ttl=get_dynamic_screener_ttl())
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
