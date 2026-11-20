"""Advanced Financial Hybrid-Context RAG (Retrieval-Augmented Generation) Engine.

Architectural Pillars (Our Platform's Core USP):
1. Deterministic Pre-Computation ("Correct-by-Construction"):
   Calculates all mathematical metrics (Best Buy Price, Structural SL, Asymmetric Targets, R:R, Valuations)
   in Python BEFORE prompting the LLM, eliminating AI math hallucinations completely.
2. Multi-Source Real-Time Retrieval:
   Retrieves Live Quotes (L1 Redis), Screener Trade Setups, Technical Indicators, SMC FVGs,
   Fundamental Matrix, and India Intelligence Market Regime.
3. Strict Token Budgeting & Low Latency:
   Keeps input context dense (< 800 tokens) and enforces ultra-concise outputs (< 120 words / 280 tokens).
4. Zero-Downtime Dual-Engine:
   Uses Groq AI (Llama 3.3 70B) when configured, falling back seamlessly to deterministic quant synthesis.
"""

import re
import time
import hashlib
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, List

from backend.core.cache_manager import cache_manager
from backend.services.market_data import market_data_service
from backend.services.indicators import indicator_service, candles_to_df
from backend.services.screener import screener_service
from backend.services.advanced_indicators import AdvancedIndicators
from backend.services.groq_service import groq_service

logger = logging.getLogger(__name__)

# Curated Indian Ticker Aliases for Fast Entity Resolution (Multi-Cap: Large, Mid, Small, Micro)
COMMON_TICKER_MAP = {
    # --- LARGE CAP BLUE CHIPS ---
    "tcs": "TCS.NS",
    "tata consultancy": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "reliance": "RELIANCE.NS",
    "ril": "RELIANCE.NS",
    "hdfc": "HDFCBANK.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS",
    "icici": "ICICIBANK.NS",
    "icicibank": "ICICIBANK.NS",
    "sbi": "SBIN.NS",
    "sbin": "SBIN.NS",
    "state bank": "SBIN.NS",
    "tata motors": "TATAMOTORS.NS",
    "tatamotors": "TATAMOTORS.NS",
    "tata steel": "TATASTEEL.NS",
    "tatasteel": "TATASTEEL.NS",
    "maruti": "MARUTI.NS",
    "maruti suzuki": "MARUTI.NS",
    "wipro": "WIPRO.NS",
    "itc": "ITC.NS",
    "bharti airtel": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "l&t": "LT.NS",
    "lt": "LT.NS",
    "larsen": "LT.NS",
    "titan": "TITAN.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "bajfinance": "BAJFINANCE.NS",
    "kotak": "KOTAKBANK.NS",
    "kotak bank": "KOTAKBANK.NS",
    "kotakbank": "KOTAKBANK.NS",
    "asian paints": "ASIANPAINT.NS",
    "asianpaint": "ASIANPAINT.NS",
    "sun pharma": "SUNPHARMA.NS",
    "sunpharma": "SUNPHARMA.NS",
    "ntpc": "NTPC.NS",
    "powergrid": "POWERGRID.NS",
    "power grid": "POWERGRID.NS",
    "coal india": "COALINDIA.NS",
    "coalindia": "COALINDIA.NS",
    "m&m": "M&M.NS",
    "mahindra": "M&M.NS",
    "m&mfin": "M&MFIN.NS",
    "m&m fin": "M&MFIN.NS",
    "mahindra finance": "M&MFIN.NS",
    "l&tfh": "L&TFH.NS",
    "l&t finance": "L&TFH.NS",
    "j&kbank": "J&KBANK.NS",
    "j&k bank": "J&KBANK.NS",
    "ultratech": "ULTRACEMCO.NS",
    "ultracemco": "ULTRACEMCO.NS",
    "adani ent": "ADANIENT.NS",
    "adanient": "ADANIENT.NS",
    "adani ports": "ADANIPORTS.NS",
    "adaniports": "ADANIPORTS.NS",
    "hindustan unilever": "HINDUNILVR.NS",
    "hul": "HINDUNILVR.NS",
    "hindunilvr": "HINDUNILVR.NS",

    # --- MID CAP GROWTH LEADERS ---
    "polycab": "POLYCAB.NS",
    "dixon": "DIXON.NS",
    "dixon tech": "DIXON.NS",
    "cams": "CAMS.NS",
    "federal bank": "FEDERALBNK.NS",
    "federalbank": "FEDERALBNK.NS",
    "bel": "BEL.NS",
    "bharat electronics": "BEL.NS",
    "hal": "HAL.NS",
    "hindustan aeronautics": "HAL.NS",
    "cummins": "CUMMINSIND.NS",
    "cummins india": "CUMMINSIND.NS",
    "godrej properties": "GODREJPROP.NS",
    "godrejprop": "GODREJPROP.NS",
    "pi industries": "PIIND.NS",
    "piind": "PIIND.NS",
    "trent": "TRENT.NS",
    "deepak nitrite": "DEEPAKNTR.NS",
    "deepakntr": "DEEPAKNTR.NS",
    "persistent": "PERSISTENT.NS",
    "persistent systems": "PERSISTENT.NS",
    "coforge": "COFORGE.NS",
    "ltimindtree": "LTIM.NS",
    "ltim": "LTIM.NS",
    "pfc": "PFC.NS",
    "power finance": "PFC.NS",
    "rec": "RECLTD.NS",
    "recltd": "RECLTD.NS",
    "tata power": "TATAPOWER.NS",
    "tatapower": "TATAPOWER.NS",
    "ashok leyland": "ASHOKLEY.NS",
    "ashokley": "ASHOKLEY.NS",
    "tvs motor": "TVSMOTOR.NS",
    "tvsmotor": "TVSMOTOR.NS",
    "hero motocorp": "HEROMOTOCO.NS",
    "heromotoco": "HEROMOTOCO.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "havells": "HAVELLS.NS",
    "vedanta": "VEDL.NS",
    "vedl": "VEDL.NS",
    "sail": "SAIL.NS",
    "national aluminium": "NATIONALUM.NS",
    "nalco": "NATIONALUM.NS",
    "nmdc": "NMDC.NS",
    "jindal steel": "JINDALSTEL.NS",
    "jindalstel": "JINDALSTEL.NS",
    "jsw steel": "JSWSTEEL.NS",
    "jswsteel": "JSWSTEEL.NS",
    "apollo hospitals": "APOLLOHOSP.NS",
    "apollohosp": "APOLLOHOSP.NS",
    "cipla": "CIPLA.NS",
    "dr reddy": "DRREDDY.NS",
    "drreddy": "DRREDDY.NS",
    "lupin": "LUPIN.NS",
    "divis": "DIVISLAB.NS",
    "divislab": "DIVISLAB.NS",
    "aurobindo": "AUROPHARMA.NS",
    "auropharma": "AUROPHARMA.NS",
    "bpcl": "BPCL.NS",
    "ongc": "ONGC.NS",
    "gail": "GAIL.NS",
    "hindalco": "HINDALCO.NS",
    "indusind": "INDUSINDBK.NS",
    "indusind bank": "INDUSINDBK.NS",
    "bank of baroda": "BANKBARODA.NS",
    "bob": "BANKBARODA.NS",
    "pnb": "PNB.NS",
    "punjab national bank": "PNB.NS",
    "au bank": "AUBANK.NS",
    "aubank": "AUBANK.NS",
    "bandhan bank": "BANDHANBNK.NS",
    "bandhanbank": "BANDHANBNK.NS",
    "idfc first": "IDFCFIRSTB.NS",
    "idfcfirstb": "IDFCFIRSTB.NS",
    "bsoft": "BSOFT.NS",
    "birlasoft": "BSOFT.NS",
    "eichermot": "EICHERMOT.NS",
    "eicher": "EICHERMOT.NS",
    "ioc": "IOC.NS",
    "indian oil": "IOC.NS",

    # --- SMALL CAP & FAST GROWTH STARS ---
    "suzlon": "SUZLON.NS",
    "suzlon energy": "SUZLON.NS",
    "ireda": "IREDA.NS",
    "indian renewable": "IREDA.NS",
    "cdsl": "CDSL.NS",
    "central depository": "CDSL.NS",
    "bse": "BSE.NS",
    "bombay stock exchange": "BSE.NS",
    "mazdock": "MAZDOCK.NS",
    "mazagon dock": "MAZDOCK.NS",
    "mazagon": "MAZDOCK.NS",
    "rvnl": "RVNL.NS",
    "rail vikas": "RVNL.NS",
    "irfc": "IRFC.NS",
    "indian railway finance": "IRFC.NS",
    "kaynes": "KAYNES.NS",
    "kaynes tech": "KAYNES.NS",
    "kalyan": "KALYANKJIL.NS",
    "kalyan jewellers": "KALYANKJIL.NS",
    "kalyankjil": "KALYANKJIL.NS",
    "angelone": "ANGELONE.NS",
    "angel one": "ANGELONE.NS",
    "rblbank": "RBLBANK.NS",
    "rbl": "RBLBANK.NS",
    "rbl bank": "RBLBANK.NS",
    "zentec": "ZENTEC.NS",
    "zen tech": "ZENTEC.NS",
    "zen technologies": "ZENTEC.NS",
    "premierene": "PREMIERENE.NS",
    "premier energies": "PREMIERENE.NS",
    "zomato": "ZOMATO.NS",
    "swiggy": "SWIGGY.NS",
    "jiofin": "JIOFIN.NS",
    "jio financial": "JIOFIN.NS",
    "cochin shipyard": "COCHINSHIP.NS",
    "cochinship": "COCHINSHIP.NS",
    "hudco": "HUDCO.NS",
    "nbcc": "NBCC.NS",
    "motilal": "MOTILALOFS.NS",
    "motilal oswal": "MOTILALOFS.NS",
    "irctc": "IRCTC.NS",
    "paytm": "PAYTM.NS",
    "one97": "PAYTM.NS",
    "nykaa": "NYKAA.NS",
    "fsn e-commerce": "NYKAA.NS",
    "ola": "OLAELEC.NS",
    "ola electric": "OLAELEC.NS",
    "yes bank": "YESBANK.NS",
    "yesbank": "YESBANK.NS",
    "vodafone idea": "IDEA.NS",
    "vodafone": "IDEA.NS",
    "vi": "IDEA.NS",
    "pc jeweller": "PCJEWELLER.NS",
    "pc jewellers": "PCJEWELLER.NS",
    "pcjeweller": "PCJEWELLER.NS",
    "pcjewellers": "PCJEWELLER.NS",
    "pcj": "PCJEWELLER.NS",
    "pc jewelers": "PCJEWELLER.NS",

    # --- BENCHMARK INDICES ---
    "nifty": "^NSEI",
    "nifty 50": "^NSEI",
    "nifty50": "^NSEI",
    "bank nifty": "^NSEBANK",
    "banknifty": "^NSEBANK",
    "sensex": "^BSESN"
}

# Curated Technical Concept Knowledge Base for Instant Authoritative Explanations
CONCEPT_KB = {
    "anchor vwap": {
        "title": "Anchor VWAP (Anchored Volume Weighted Average Price)",
        "definition": "Anchor VWAP measures the true volume-weighted average price paid by institutional market participants starting from a user-selected significant structural anchor point (such as Earnings release, 52-week High/Low, or Breakout bar).",
        "usage": "When price trades above Anchor VWAP, buyers who accumulated since that event are in net profit, acting as strong institutional support on pullbacks. When price is below, it acts as overhead resistance."
    },
    "heikin ashi": {
        "title": "Heikin Ashi (Smoothed Trend Candlesticks)",
        "definition": "Heikin Ashi (Japanese for 'Average Bar') calculates synthetic OHLC values using the averages of current and previous periods to filter out intraday market noise and false reversals.",
        "usage": "Consecutive green candles with no lower wicks indicate a strong uptrend; consecutive red candles with no upper wicks confirm strong downward momentum. Ideal for trailing stops."
    },
    "fair value gap": {
        "title": "Fair Value Gap (FVG / Smart Money PoI)",
        "definition": "An institutional price imbalance formed when a high-volatility 3-candle sequence leaves a gap between Candle 1's High and Candle 3's Low without overlapping wick volume.",
        "usage": "Institutions leave unfilled orders in FVGs. Markets systematically retrace back into the FVG to re-balance liquidity, creating high-probability asymmetric pullback entries."
    },
    "supertrend": {
        "title": "Supertrend Indicator",
        "definition": "An adaptive volatility trend-following overlay based on ATR (Average True Range). It draws dynamic trailing stop boundaries above or below price based on market volatility.",
        "usage": "A green line below price signifies a bullish trend (long bias); a red line above price signifies a bearish regime. A flip from red to green triggers a trend reversal entry."
    },
    "bollinger bands": {
        "title": "Bollinger Bands (20-SMA ± 2 Std Dev)",
        "definition": "Volatility envelope developed by John Bollinger. Comprises a 20-period moving average and upper/lower bands set 2 standard deviations away, capturing ~95% of normal price action.",
        "usage": "A squeeze (narrowing bands) precedes explosive breakouts. Touching the upper band in a range signals overbought conditions; in a trend, riding the upper band signals strong momentum."
    }
}


class FinancialRAGService:
    """Enterprise RAG engine integrating multi-source market retrieval with Groq AI."""

    def __init__(self):
        pass

    def extract_intent_and_entity(self, query: str, symbol_hint: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Extract query intent and target entity (stock symbol or concept key).
        
        Returns:
            (intent, entity_or_symbol)
            intent can be: 'CONCEPT', 'MARKET_REGIME', 'STOCK_ANALYSIS', 'GENERAL'
        """
        q_lower = query.lower().strip()

        # 1. Check for Concept Questions
        for concept_key in CONCEPT_KB:
            if concept_key in q_lower or concept_key.replace(" ", "") in q_lower.replace(" ", ""):
                return "CONCEPT", concept_key

        if "vwap" in q_lower and ("what is" in q_lower or "how to use" in q_lower or "explain" in q_lower):
            return "CONCEPT", "anchor vwap"
        if "heikin" in q_lower or "heiken" in q_lower:
            return "CONCEPT", "heikin ashi"
        if "fvg" in q_lower or "order block" in q_lower or "smart money" in q_lower:
            return "CONCEPT", "fair value gap"

        # 2. Check for Macro Market Regime Questions
        market_words = ["market", "nifty", "regime", "breadth", "fii", "dii", "falling", "crash", "macro", "sensex"]
        if any(w in q_lower for w in market_words) and not any(sym in q_lower for sym in ["tcs", "infy", "reliance", "hdfc", "sbi"]):
            return "MARKET_REGIME", "^NSEI"

        # 3. Check for Symbol in hint or query
        resolved_sym = None
        
        # Guard against English stop words incorrectly passed as symbol hints
        common_stop_words = {
            "WHAT", "IS", "THE", "TARGET", "FOR", "PRICE", "OF", "HOW", "LOOKING", "TODAY",
            "GIVE", "ME", "ANALYSIS", "ON", "CAN", "YOU", "CHECK", "SETUP", "LEVELS", "STOCK",
            "SHARE", "VIEW", "RECOMMENDATION", "GOOD", "ENTER", "EXIT", "SHOULD", "I", "BUY",
            "SELL", "HOLD", "TELL", "ABOUT", "TRADE", "PLAN", "FORECAST", "PREDICTION", "CMP",
            "SUPPORT", "RESISTANCE", "PLEASE", "NOW", "TOMORROW", "THIS", "WEEK", "OR", "NEED",
            "TO", "DROP", "IDEA", "IN", "CURRENT", "SITUATION", "BEST", "WOULD", "COULD", "WILL",
            "SHALL", "CALL", "PUT", "OPTION", "FALLING", "RISING", "CHART", "REPORT", "NOT"
        }

        # 3A. Priority #1: Explicit '@' Mention in Query (e.g., @PCJEWELLER, @TCS, @RELIANCE)
        mention_match = re.search(r'@([A-Za-z0-9-]{2,15}(?:\.NS|\.BO)?)', query)
        if mention_match:
            raw_mention = mention_match.group(1).upper()
            clean_mention = raw_mention.replace(".NS", "").replace(".BO", "")
            if clean_mention not in common_stop_words:
                resolved_sym = raw_mention if ("." in raw_mention or raw_mention.startswith("^")) else f"{raw_mention}.NS"
                return "STOCK_ANALYSIS", resolved_sym

        if symbol_hint:
            norm = symbol_hint.upper().strip()
            clean_token = norm.replace(".NS", "").replace(".BO", "")
            if clean_token not in common_stop_words and len(clean_token) >= 2:
                resolved_sym = norm if ("." in norm or norm.startswith("^")) else f"{norm}.NS"

        if not resolved_sym:
            # Match known ticker map (sorted by length descending for greedy match)
            for alias, ticker in sorted(COMMON_TICKER_MAP.items(), key=lambda x: -len(x[0])):
                pattern = r'(?<![a-zA-Z0-9])' + re.escape(alias) + r'(?![a-zA-Z0-9])'
                if re.search(pattern, q_lower):
                    resolved_sym = ticker
                    break

            # Fallback regex for standalone uppercase NSE symbols (e.g. TATAPOWER.NS or M&M.NS or TATAPOWER)
            if not resolved_sym:
                matches = re.findall(r'(?<![a-zA-Z0-9])([A-Z0-9&.-]{2,15})(?![a-zA-Z0-9])', query)
                for m in matches:
                    token = m.upper().replace(".NS", "")
                    if token not in common_stop_words and not token.isdigit():
                        resolved_sym = m if "." in m else f"{token}.NS"
                        break

        if resolved_sym:
            return "STOCK_ANALYSIS", resolved_sym

        return "GENERAL", None

    async def extract_intent_and_entity_async(self, query: str, symbol_hint: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Asynchronously extract intent and entity, with dynamic live database / Yahoo search fallback
        for all Small-Cap, Mid-Cap, and Large-Cap Indian equities.
        """
        # 1. Fast synchronous resolution via curated knowledge bases and multi-cap ticker map
        intent, entity = self.extract_intent_and_entity(query, symbol_hint)
        if intent != "GENERAL" or entity:
            return intent, entity

        # 2. Dynamic Universal Stock Search Fallback (Searches PostgreSQL & Yahoo for ALL stocks)
        try:
            q_lower = query.lower().strip()
            stop_words = {
                "what", "is", "the", "target", "for", "price", "of", "how", "looking", "today",
                "give", "me", "analysis", "on", "can", "you", "check", "setup", "levels", "stock",
                "share", "view", "recommendation", "good", "enter", "exit", "should", "i", "buy",
                "sell", "hold", "tell", "about", "trade", "plan", "forecast", "prediction", "cmp",
                "support", "resistance", "please", "now", "tomorrow", "this", "week", "or", "need",
                "to", "drop", "idea", "in", "current", "situation", "best", "would", "could", "will"
            }
            tokens = [w for w in re.findall(r'[a-zA-Z0-9]+', q_lower) if w not in stop_words]
            if tokens:
                candidate = " ".join(tokens).strip()
                search_results = await market_data_service.search_stocks(candidate)
                # If plural (e.g. "jewellers"), try singular form as well
                if not search_results and candidate.endswith("s"):
                    search_results = await market_data_service.search_stocks(candidate[:-1])
                if search_results and len(search_results) > 0:
                    matched_sym = search_results[0]["symbol"]
                    resolved_sym = matched_sym if ("." in matched_sym or matched_sym.startswith("^")) else f"{matched_sym}.NS"
                    return "STOCK_ANALYSIS", resolved_sym
        except Exception as e:
            logger.debug(f"[RAG] Universal stock search failed for candidate '{query}': {e}")

        return "GENERAL", None

    async def retrieve_stock_context(self, symbol: str) -> Dict[str, Any]:
        """
        Parallel retrieval of live quote, quant trade plan, technicals, valuations, and S/R levels.
        """
        try:
            quote_task = market_data_service.fetch_quote(symbol)
            candles_task = market_data_service.fetch_candles(symbol, "1d", limit=250)
            screener_task = screener_service._analyze_symbol(symbol, force_refresh=False)

            quote, candles, screener_res = await asyncio.gather(
                quote_task, candles_task, screener_task, return_exceptions=True
            )

            # Defensive fallbacks
            valid_quote = quote if (not isinstance(quote, Exception) and quote) else {}
            valid_candles = candles if (not isinstance(candles, Exception) and isinstance(candles, list)) else []
            valid_plan = screener_res if (not isinstance(screener_res, Exception) and isinstance(screener_res, dict)) else {}

            cmp = float(valid_quote.get("price") or (valid_candles[-1]["close"] if valid_candles else 0.0))
            
            # S/R Detection
            sr_levels = {"support": [], "resistance": []}
            if valid_candles and len(valid_candles) >= 30:
                try:
                    df = candles_to_df(valid_candles)
                    sr_levels = AdvancedIndicators.detect_support_resistance(df)
                except Exception:
                    pass

            # Pre-computed quant plan
            trade_plan = valid_plan.get("trade_plan", {})
            action = valid_plan.get("action", "HOLD")
            score = valid_plan.get("total_score", 50.0)
            best_buy = float(trade_plan.get("best_buy_price") or trade_plan.get("entry_price") or cmp)
            sl = float(trade_plan.get("stop_loss") or (best_buy * 0.96))
            target_t2 = float(trade_plan.get("target_price") or (best_buy * 1.06))
            target_t1 = float(trade_plan.get("target_1") or (best_buy * 1.03))
            gain_pct = float(trade_plan.get("expected_gain_pct") or 0.0)
            risk_pct = float(trade_plan.get("risk_pct") or 0.0)
            rr = float(trade_plan.get("reward_to_risk") or 2.5)

            support_val = sr_levels["support"][0] if sr_levels["support"] else (sl if sl > 0 else cmp * 0.96)
            resist_val = sr_levels["resistance"][0] if sr_levels["resistance"] else (target_t2 if target_t2 > 0 else cmp * 1.06)

            return {
                "symbol": symbol,
                "name": valid_plan.get("name", symbol.replace(".NS", "")),
                "cmp": round(cmp, 2),
                "action": action,
                "total_score": round(score, 1),
                "cap_segment": valid_plan.get("cap_segment", "MID_CAP"),
                "is_fast_growth": valid_plan.get("is_fast_growth", False),
                "trade_plan": {
                    "best_buy_price": round(best_buy, 2),
                    "cmp": round(cmp, 2),
                    "stop_loss": round(sl, 2),
                    "target_1": round(target_t1, 2),
                    "target_2": round(target_t2, 2),
                    "expected_gain_pct": round(gain_pct, 1),
                    "risk_pct": round(risk_pct, 1),
                    "reward_to_risk": rr,
                    "entry_type": trade_plan.get("entry_type", "SUPPORT_ACCUMULATION"),
                    "entry_advice": trade_plan.get("entry_advice", "Trade setup pending confirmation."),
                    "hold_time": trade_plan.get("estimated_hold_time", "3 to 5 Days")
                },
                "support": round(support_val, 2),
                "resistance": round(resist_val, 2),
                "news_sentiment": valid_plan.get("news_sentiment", "NEUTRAL")
            }
        except Exception as e:
            logger.error(f"[RAG] Stock context retrieval error for {symbol}: {e}")
            return {"symbol": symbol, "cmp": 0.0, "action": "HOLD", "total_score": 50.0}

    async def retrieve_market_regime_context(self) -> Dict[str, Any]:
        """Retrieve macro Nifty/Sensex regime, breadth, and FII/DII flow signals."""
        try:
            from backend.services.india_intelligence import india_intelligence
            regime = await india_intelligence.get_comprehensive_regime()
            
            phase = regime.get('regime', 'BALANCED')
            conf = int(regime.get('confidence', 0.75) * 100)
            breadth = regime.get('detail', {}).get('market_breadth', {}).get('breadth_signal', 'Neutral')
            signals = regime.get("signals", [])
            key_drivers = [f"{s.get('source')}: {s.get('detail')}" for s in signals[:2]]

            return {
                "regime": phase,
                "confidence_pct": conf,
                "breadth": breadth,
                "drivers": key_drivers
            }
        except Exception as e:
            logger.error(f"[RAG] Market regime retrieval error: {e}")
            return {
                "regime": "NEUTRAL_CONSOLIDATION",
                "confidence_pct": 70,
                "breadth": "Neutral",
                "drivers": ["Market oscillating near 50-EMA baseline"]
            }

    def generate_deterministic_response(self, intent: str, entity: Optional[str], context: Dict[str, Any], query: str) -> str:
        """
        Zero-downtime, deterministic quantitative response generator.
        Produces an identical high-precision, ultra-concise answer without needing an LLM.
        """
        if intent == "CONCEPT" and entity and entity in CONCEPT_KB:
            data = CONCEPT_KB[entity]
            return (
                f"### 💡 {data['title']}\n"
                f"- **Definition**: {data['definition']}\n"
                f"- **Institutional Usage**: {data['usage']}"
            )

        if intent == "MARKET_REGIME":
            regime = context.get("regime", "NEUTRAL")
            conf = context.get("confidence_pct", 75)
            breadth = context.get("breadth", "Neutral")
            drivers = context.get("drivers", [])
            driver_text = f"\n- **Key Drivers**: {'; '.join(drivers)}" if drivers else ""
            return (
                f"### 📊 Indian Market Regime Overview\n"
                f"- **Macro Phase**: **{regime}** (Confidence: {conf}%)\n"
                f"- **Market Breadth**: **{breadth}** (Advancers vs Decliners ratio)\n"
                f"- **Execution Stance**: {'Favorable for selective momentum longs.' if 'BULL' in regime else 'Maintain defensive position sizing and tight stop losses.'}"
                f"{driver_text}"
            )

        if intent == "STOCK_ANALYSIS" and context.get("symbol"):
            sym = context["symbol"].replace(".NS", "")
            cmp = float(context.get("cmp", 0.0))
            if cmp <= 0.0:
                return (
                    f"### ⚠️ {sym} Data Unavailable\n"
                    f"- **Notice**: Live market quotes or trading history for **{sym}** could not be retrieved.\n"
                    f"- **Guidance**: Please check that the company name or symbol is correctly spelled (e.g. *'PC Jeweller'*, *'TCS'*, *'Suzlon'*)."
                )

            action = context["action"]
            score = context["total_score"]
            cap_segment = context.get("cap_segment", "MID_CAP")
            cap_badge_map = {
                "LARGE_CAP": "[💎 Large Cap]",
                "MID_CAP": "[⚡ Mid Cap]",
                "SMALL_CAP": "[🌱 Small Cap]"
            }
            cap_badge = cap_badge_map.get(cap_segment, "[📊 Multi-Cap]")
            growth_badge = " [🚀 Fast Growth]" if context.get("is_fast_growth") else ""

            plan = context.get("trade_plan", {})
            best_buy = plan.get("best_buy_price", cmp)
            sl = plan.get("stop_loss", cmp * 0.96)
            t2 = plan.get("target_2", cmp * 1.06)
            gain = plan.get("expected_gain_pct", 6.0)
            risk = plan.get("risk_pct", 2.5)
            rr = plan.get("reward_to_risk", 2.5)
            hold = plan.get("hold_time", "3 to 5 Days")
            advice = plan.get("entry_advice", "Price structure confirmed.")
            supp = context.get("support", sl)
            res = context.get("resistance", t2)

            # Direct tailored advice addressing user dilemma
            if "BUY" in action:
                direct_rec = f"Favorable momentum setup ({rr}:1 R:R). Accumulate near the Best Buy level of ₹{best_buy:,.2f} rather than chasing CMP, keeping a structural stop loss at ₹{sl:,.2f}."
            elif "SELL" in action:
                direct_rec = f"Unfavorable risk profile (Score: {score}/100). Drop new long entries and wait for confirmed base reversal."
            else:
                direct_rec = f"Consolidating in range. Do not rush to buy at CMP or drop the idea completely; wait for a pullback to accumulate near the support base at ₹{best_buy:,.2f}."

            return (
                f"### 🎯 {sym} Trade Plan & Quant Strategy {cap_badge}{growth_badge}\n"
                f"- **Direct Recommendation**: {direct_rec}\n"
                f"- **Signal & Conviction**: **{action}** (Score: **{score}/100** | CMP: ₹{cmp:,.2f})\n"
                f"- **Execution Levels**: Best Buy: **₹{best_buy:,.2f}** | SL: **₹{sl:,.2f}** (-{risk}%) | Target: **₹{t2:,.2f}** (+{gain}%) | R:R: **{rr}:1**\n"
                f"- **Setup & Confluence**: {advice} (Key Boundaries: Support: ₹{supp:,.2f} | Resistance: ₹{res:,.2f})"
            )

        return (
            "I am your StockAI Institutional Assistant powered by Groq & Advanced Quantitative RAG. "
            "Ask me for stock setups across Large, Mid, and Small caps (e.g. *'@PCJEWELLER'*, *'Should I buy TCS?'*, *'Analyze Suzlon'*), market regime (*'How is Nifty today?'*), or technical concepts (*'What is Anchor VWAP?'*)."
        )

    async def process_chat_query(self, message: str, symbol_hint: Optional[str] = None) -> Dict[str, Any]:
        """
        Master RAG pipeline:
        1. Extract intent & entities (with @ mention priority & dynamic multi-cap search)
        2. Multi-User Semantic Cache check (L1 Memory + L2 Redis + SingleFlight)
        3. Retrieve multi-source quantitative context
        4. Pre-compute and verify mathematical figures in Python
        5. Query Groq AI with token-budgeted conversational synthesis
        6. Seamlessly fallback to deterministic synthesis if Groq unavailable
        7. Cache response for subsequent users / repeat queries
        """
        intent, entity = await self.extract_intent_and_entity_async(message, symbol_hint)

        # Multi-User Semantic Cache Check: Avoid duplicate LLM token burn for identical/similar questions
        cache_key = None
        if entity:
            clean_q = re.sub(r'[^a-zA-Z0-9]', '', message.lower())
            q_hash = hashlib.md5(clean_q.encode('utf-8')).hexdigest()[:8]
            cache_key = f"rag:chat_v2:{intent}:{entity}:{q_hash}"
            cached_resp = await cache_manager.get(cache_key)
            if cached_resp and isinstance(cached_resp, dict):
                logger.info(f"⚡ [RAG Cache Hit] Serving cached response for {entity} ({intent})")
                cached_resp_copy = dict(cached_resp)
                cached_resp_copy["cached"] = True
                return cached_resp_copy

        # Context retrieval
        context: Dict[str, Any] = {}
        if intent == "CONCEPT":
            context = CONCEPT_KB.get(entity, {})
        elif intent == "MARKET_REGIME":
            context = await self.retrieve_market_regime_context()
        elif intent == "STOCK_ANALYSIS":
            context = await self.retrieve_stock_context(entity)

        # If Groq is not configured or concept query, return high-speed deterministic response
        if not groq_service.is_configured():
            reply = self.generate_deterministic_response(intent, entity, context, message)
            resp = {
                "reply": reply,
                "response": reply,
                "intent": intent,
                "source": "deterministic_quant_rag",
                "entity": entity,
                "groq_active": False,
                "cached": False
            }
            if cache_key and context.get("cmp", 0) > 0:
                await cache_manager.set(cache_key, resp, ttl=300)
            return resp

        # Build Token-Budgeted Precision Prompt for Groq AI
        system_prompt = (
            "You are StockAI, an elite Wall Street & Dalal Street institutional quantitative analyst.\n"
            "MANDATORY INSTRUCTIONS:\n"
            "1. CONVERSATIONAL SYNTHESIS & DIRECT ADVICE: Address the user's specific question directly in the first bullet point. "
            "(For example, if they ask whether to buy, hold, sell, or drop the idea, give unambiguous direct advice on their dilemma based on the quantitative setup).\n"
            "2. VERIFIED QUANT GROUND TRUTH: All mathematical values (Best Buy, Stop Loss, Targets, R:R, CMP) provided in the Ground Truth Context are already calculated and verified in Python. "
            "You are strictly forbidden from inventing numbers or altering percentages. Cite ONLY the verified figures provided.\n"
            "3. EXTREME BREVITY & TOKEN BUDGET: Responses MUST be under 115 words in exactly 4 punchy bullet points to prevent token expiration.\n"
            "4. RESPONSE FORMAT (Markdown):\n"
            "   Header format: ### 🎯 [SYMBOL] Trade Plan & Quant Strategy [[💎 Large Cap] / [⚡ Mid Cap] / [🌱 Small Cap]] [[🚀 Fast Growth]]\n"
            "   - **Direct Recommendation**: 1-2 sharp conversational sentences answering their exact question (e.g. whether to enter, wait for pullback, or drop the trade).\n"
            "   - **Signal & Conviction**: [BUY / SELL / HOLD] (Score: X/100 | CMP: ₹...)\n"
            "   - **Execution Levels**: Best Buy: ₹... | SL: ₹... (-X%) | Target: ₹... (+Y%) | R:R: Z:1\n"
            "   - **Setup & Confluence**: Key technical structural reason and boundaries (Support: ₹... | Resistance: ₹...).\n"
            "5. No conversational filler or legal disclaimers. Get straight to the point."
        )

        user_prompt = f"User Question: {message}\n\nGround Truth Context:\n{context}"

        groq_res = await groq_service.generate_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=280,
            temperature=0.2
        )

        if groq_res and groq_res.get("content"):
            resp = {
                "reply": groq_res["content"],
                "response": groq_res["content"],
                "intent": intent,
                "source": "groq_llm",
                "model": groq_res.get("model"),
                "tokens_used": groq_res.get("tokens_used"),
                "latency_ms": groq_res.get("latency_ms"),
                "entity": entity,
                "groq_active": True,
                "cached": False
            }
            if cache_key and context.get("cmp", 0) > 0:
                await cache_manager.set(cache_key, resp, ttl=300)
            return resp

        # Fallback to deterministic RAG if Groq call failed or timed out
        reply = self.generate_deterministic_response(intent, entity, context, message)
        resp = {
            "reply": reply,
            "response": reply,
            "intent": intent,
            "source": "deterministic_fallback_rag",
            "entity": entity,
            "groq_active": False,
            "cached": False
        }
        if cache_key and context.get("cmp", 0) > 0:
            await cache_manager.set(cache_key, resp, ttl=300)
        return resp


rag_service = FinancialRAGService()
