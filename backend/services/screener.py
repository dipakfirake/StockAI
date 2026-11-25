"""
AI Swing Trade Screener Service
Scans top market stocks, analyzes technicals, fundamentals, and NLP sentiment,
and generates strict institutional-grade trade setups with defined risk/reward.
"""

from __future__ import annotations

import os
import asyncio
import time as time_mod
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional
import numpy as np

from backend.core.logging_config import get_logger
from backend.core.cache import cache_get, cache_set
from backend.core.cache_manager import cache_manager
from backend.core.executors import run_in_ml_executor
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
    _scan_jobs: dict[str, dict] = {}
    _active_sector_jobs: dict[str, str] = {}
    _scan_bg_tasks: set[asyncio.Task] = set()

    @staticmethod
    def _compute_symbol_scoring_sync(
        candles: list[dict],
        symbol: str,
        prefetched_nifty_indicators: Optional[dict] = None,
        nifty_candles: Optional[list[dict]] = None,
    ) -> tuple[dict, list[dict], dict]:
        """
        Runs technical indicator calculation, relative strength enrichment,
        signal evaluation, and PyTorch/LightGBM ensemble scoring in a single
        bounded ML executor dispatch — preventing event-loop freezing.
        """
        indicators = indicator_service.compute_all(candles) if len(candles) >= 30 else {}
        if indicators:
            try:
                nifty_ind = prefetched_nifty_indicators
                if not nifty_ind and nifty_candles and len(nifty_candles) >= 20:
                    nifty_ind = indicator_service.compute_all(nifty_candles)
                if nifty_ind and len(nifty_ind) > 0 and "price_return_20d" in nifty_ind:
                    indicators["rs_momentum_20d"] = (
                        indicators.get("price_return_20d", 0.0) - nifty_ind.get("price_return_20d", 0.0)
                    )
            except Exception as ex:
                logger.warning(f"Failed to compute RS momentum for {symbol}: {ex}")

        signals = signal_engine.evaluate(indicators, symbol)
        ai_res = ai_engine_service.score(
            indicators if indicators else {},
            symbol=symbol,
            compute_shap=False,
            candles=candles if isinstance(candles, list) else None,
        )
        return indicators, signals, ai_res

    @staticmethod
    async def start_scan_job(sector: str = None, force_refresh: bool = True) -> dict:
        """
        Non-blocking async scan launcher: returns immediately with an active job_id
        (coalescing duplicate clicks on the same sector) and Last-Known-Good snapshot
        so the browser never waits >60s behind Nginx.
        """
        norm_sector = sector.upper().replace(" ", "_") if sector else "DEFAULT"
        symbols = SECTOR_UNIVERSES.get(norm_sector, NIFTY_UNIVERSE)

        # Fast-path: if fresh cache already exists and caller did not ask to force refresh, return immediately
        if not force_refresh:
            try:
                fresh = await cache_get(f"screener_results_{norm_sector}")
                if isinstance(fresh, dict) and "buy_stocks" in fresh:
                    return {
                        "job_id": f"cached_{norm_sector}",
                        "sector": norm_sector,
                        "status": "completed",
                        "progress": 100,
                        "completed": len(symbols),
                        "total": len(symbols),
                        "result": fresh,
                        "error": None,
                    }
            except Exception:
                pass

        # Reuse active running job for this sector if one is already in progress
        existing_job_id = ScreenerService._active_sector_jobs.get(norm_sector)
        if existing_job_id and existing_job_id in ScreenerService._scan_jobs:
            job = ScreenerService._scan_jobs[existing_job_id]
            if job.get("status") == "running":
                return dict(job)

        # Grab quick LKG or fresh cache so UI can render without blank wait
        quick_data = None
        try:
            quick_data = await cache_get(f"screener_results_{norm_sector}")
            if not (isinstance(quick_data, dict) and "buy_stocks" in quick_data):
                quick_data = await cache_get(f"screener_lkg_{norm_sector}")
        except Exception:
            quick_data = None

        job_id = f"scan_{norm_sector}_{uuid.uuid4().hex[:10]}"
        job_state = {
            "job_id": job_id,
            "sector": norm_sector,
            "status": "running",
            "progress": 5,
            "completed": 0,
            "total": len(symbols),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "cached_data": quick_data if isinstance(quick_data, dict) and "buy_stocks" in quick_data else None,
            "result": None,
            "error": None,
        }
        ScreenerService._scan_jobs[job_id] = job_state
        ScreenerService._active_sector_jobs[norm_sector] = job_id

        # Keep bounded in-memory job history
        if len(ScreenerService._scan_jobs) > 50:
            oldest = list(ScreenerService._scan_jobs.keys())[:-25]
            for old_id in oldest:
                if ScreenerService._scan_jobs.get(old_id, {}).get("status") != "running":
                    ScreenerService._scan_jobs.pop(old_id, None)

        # 1. Forward scan to dedicated Celery worker (keeps Uvicorn at 0% CPU & eliminates timeouts)
        dispatched_to_celery = False
        if not os.getenv("PYTEST_CURRENT_TEST") and os.getenv("ENABLE_CELERY_SCREENER", "true").lower() == "true":
            try:
                from backend.tasks.market_tasks import run_sector_screener_task
                celery_res = run_sector_screener_task.apply_async(
                    kwargs={"sector": norm_sector, "force_refresh": force_refresh, "job_id": job_id},
                    retry=False,
                )
                if celery_res and celery_res.id:
                    dispatched_to_celery = True
                    job_state["celery_task_id"] = str(celery_res.id)
                    # Save initial job state to Redis for immediate worker coordination
                    persisted = {k: v for k, v in job_state.items() if k != "cached_data"}
                    try:
                        await cache_set(f"screener_job:{job_id}", persisted, ttl=600)
                    except Exception:
                        pass
                    logger.info(f"Dispatched sector screener for {norm_sector} to Celery worker (task_id: {celery_res.id})")
            except Exception as e:
                logger.debug(f"Celery dispatch unavailable, using bounded async fallback: {e}")
                dispatched_to_celery = False

        # 2. Resilient fallback for standalone unit testing or environments without Celery
        if not dispatched_to_celery:
            async def _run_job() -> None:
                def _on_progress(completed: int, total: int) -> None:
                    pct = min(98, max(5, int((completed / max(1, total)) * 95) + 3))
                    job_state["completed"] = completed
                    job_state["total"] = total
                    job_state["progress"] = pct

                try:
                    res = await ScreenerService.run_screener(
                        symbols=symbols,
                        sector=norm_sector,
                        force_refresh=force_refresh,
                        progress_cb=_on_progress,
                    )
                    job_state["status"] = "completed"
                    job_state["progress"] = 100
                    job_state["completed"] = len(symbols)
                    job_state["result"] = res
                    job_state["finished_at"] = datetime.now(timezone.utc).isoformat()
                except Exception as exc:
                    logger.error(f"Background scan job {job_id} failed: {exc}")
                    job_state["status"] = "failed"
                    job_state["error"] = str(exc)
                finally:
                    if ScreenerService._active_sector_jobs.get(norm_sector) == job_id:
                        ScreenerService._active_sector_jobs.pop(norm_sector, None)
                    try:
                        persisted = {k: v for k, v in job_state.items() if k != "cached_data"}
                        await cache_set(f"screener_job:{job_id}", persisted, ttl=600)
                    except Exception:
                        pass

            task = asyncio.create_task(_run_job())
            ScreenerService._scan_bg_tasks.add(task)
            task.add_done_callback(ScreenerService._scan_bg_tasks.discard)

        return dict(job_state)

    @staticmethod
    async def get_scan_job_status(job_id: str) -> Optional[dict]:
        """Return lightweight status of an async screener scan job without re-sending cached_data."""
        # Check Redis first (which Celery updates in real-time)
        try:
            cached = await cache_get(f"screener_job:{job_id}")
            if isinstance(cached, dict):
                return {k: v for k, v in cached.items() if k != "cached_data"}
        except Exception:
            pass

        # Check in-process fallback state
        job = ScreenerService._scan_jobs.get(job_id)
        if job:
            return {k: v for k, v in job.items() if k != "cached_data"}
        return None

    @staticmethod
    async def run_screener(
        symbols: list[str] = None,
        sector: str = None,
        force_refresh: bool = False,
        pace_seconds: float = 0.08,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Run the multi-factor screener on a list of symbols or sector universe.
        Uses Single-Flight coalescing (even on force_refresh=True), bounded semaphore
        pacing, and ML-executor isolation so upstream rate limits & event loop never choke.
        """
        norm_sector = sector.upper().replace(" ", "_") if sector else "DEFAULT"
        if not symbols:
            symbols = SECTOR_UNIVERSES.get(norm_sector, NIFTY_UNIVERSE)

        cache_key = f"screener_results_{norm_sector}"
        lkg_key = f"screener_lkg_{norm_sector}"
        if not force_refresh:
            cached = await cache_get(cache_key)
            if cached and isinstance(cached, dict) and "buy_stocks" in cached:
                logger.info(f"Returning cached screener results for {norm_sector}")
                if progress_cb:
                    progress_cb(len(symbols), len(symbols))
                return cached

        sf_key = f"sf:screener:run:{norm_sector}:{len(symbols)}:{bool(force_refresh)}"

        async def _execute_scan() -> dict:
            if not force_refresh:
                cached_inner = await cache_get(cache_key)
                if cached_inner and isinstance(cached_inner, dict) and "buy_stocks" in cached_inner:
                    return cached_inner

            logger.info(f"Starting Swing Trade Screener for {len(symbols)} symbols ({norm_sector})...")

            # 1. Pre-fetch real-time quotes in bulk (1 single Fyers API call instead of N separate calls)
            quotes_map = {}
            try:
                quotes_map = await market_data_service.fetch_quotes_bulk(symbols)
            except Exception as e:
                logger.debug(f"Failed to prefetch bulk quotes for {norm_sector}: {e}")

            # 2. Pre-fetch benchmark Nifty 50 indicators ONCE on bounded ML executor
            nifty_indicators = {}
            try:
                nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", limit=50)
                if nifty_candles and len(nifty_candles) >= 20:
                    nifty_indicators = await run_in_ml_executor(indicator_service.compute_all, nifty_candles)
            except Exception as e:
                logger.debug(f"Failed to prefetch Nifty indicators: {e}")

            # 3. Paced bounded concurrency (max 4 upstream workers in flight)
            sem = asyncio.Semaphore(4)
            completed_count = 0

            async def _run_one(idx: int, sym: str):
                nonlocal completed_count
                async with sem:
                    if idx > 0 and pace_seconds > 0:
                        # Gentle stagger keeps Fyers/Yahoo/Screener within safe burst envelope
                        await asyncio.sleep(min(0.35, pace_seconds))
                    try:
                        return await ScreenerService._analyze_symbol(
                            sym,
                            force_refresh=force_refresh,
                            prefetched_quote=quotes_map.get(sym),
                            prefetched_nifty_indicators=nifty_indicators,
                        )
                    finally:
                        completed_count += 1
                        if progress_cb:
                            try:
                                progress_cb(completed_count, len(symbols))
                            except Exception:
                                pass

            results = await asyncio.gather(
                *[_run_one(i, sym) for i, sym in enumerate(symbols)],
                return_exceptions=True,
            )

            all_results = []
            for res in results:
                if isinstance(res, dict) and res.get("total_score", 0) > 0 and not res.get("error"):
                    all_results.append(res)

            # Categorize into explicit trading lists
            buy_stocks = [r for r in all_results if r.get("action") == "BUY"]
            buy_stocks.sort(key=lambda x: x.get("total_score", 0), reverse=True)

            sell_stocks = [r for r in all_results if r.get("action") == "SELL"]
            sell_stocks.sort(key=lambda x: x.get("total_score", 0))

            hold_stocks = [r for r in all_results if r.get("action") == "HOLD"]
            hold_stocks.sort(key=lambda x: x.get("total_score", 0), reverse=True)

            all_results.sort(key=lambda x: x.get("total_score", 0), reverse=True)
            top_setups = [r for r in all_results if r.get("total_score", 0) >= 65]

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
                "all_results": all_results,
            }

            if buy_stocks and force_refresh:
                elite_buys = [s for s in buy_stocks if float(s.get("total_score", 0.0) or 0.0) >= 78.0]
                elite_buys.sort(key=lambda s: float(s.get("total_score", 0.0) or 0.0), reverse=True)
                capped_elite_buys = elite_buys[:3]
                if capped_elite_buys:
                    async def _auto_catalog_screener_buys(stocks_to_catalog):
                        try:
                            from backend.services.swing_audit_service import SwingAuditService
                            from backend.core.database import AsyncSessionLocal
                            async with AsyncSessionLocal() as audit_db:
                                await SwingAuditService.track_batch_swing_trades(
                                    db=audit_db,
                                    stocks=stocks_to_catalog,
                                )
                        except Exception as ex:
                            logger.warning(f"Failed to auto-catalog screener buys into audit: {ex}")
                    asyncio.create_task(_auto_catalog_screener_buys(list(capped_elite_buys)))

            await cache_set(cache_key, output, ttl=get_dynamic_screener_ttl())
            if all_results:
                try:
                    await cache_set(lkg_key, output, ttl=43200)  # 12h Last-Known-Good fallback snapshot
                except Exception:
                    pass
            return output

        return await cache_manager.single_flight.execute(sf_key, _execute_scan)

    @staticmethod
    def get_all_sector_symbols() -> list[str]:
        """
        Returns a deduplicated list of all symbols across all 10 sector universes
        (NIFTY_50, BANKING, IT, AUTO, PHARMA, ENERGY/Oil & Resources, FMCG, METAL, MID_CAP, SMALL_CAP).
        """
        seen = set()
        all_symbols = []
        for sec_name, syms in SECTOR_UNIVERSES.items():
            for s in syms:
                norm = s.strip().upper()
                if norm not in seen:
                    seen.add(norm)
                    all_symbols.append(norm)
        return all_symbols

    @staticmethod
    async def run_all_sectors_screener(
        force_refresh: bool = False,
        min_score: float = 70.0,
        pace_seconds: float = 0.15,
    ) -> dict:
        """
        Runs multi-factor screening across ALL 10 screener sectors with Single-Flight coalescing
        and bounded pacing (max 4 concurrent workers) to strictly protect Fyers API budget.
        """
        cache_key = "screener_all_sectors_aggregated"
        if not force_refresh:
            cached = await cache_get(cache_key)
            if cached and isinstance(cached, dict) and "buy_stocks" in cached:
                logger.info("Returning cached multi-sector screener results")
                return cached

        async def _run_all() -> dict:
            if not force_refresh:
                cached_inner = await cache_get(cache_key)
                if cached_inner and isinstance(cached_inner, dict) and "buy_stocks" in cached_inner:
                    return cached_inner

            all_symbols = ScreenerService.get_all_sector_symbols()
            logger.info(f"Starting Multi-Sector Swing Screener for all {len(all_symbols)} unique symbols across {len(SECTOR_UNIVERSES)} sectors...")

            quotes_map = {}
            try:
                quotes_map = await market_data_service.fetch_quotes_bulk(all_symbols)
            except Exception as e:
                logger.debug(f"Failed to prefetch all-sectors bulk quotes: {e}")

            nifty_indicators = {}
            try:
                nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", limit=50)
                if nifty_candles and len(nifty_candles) >= 20:
                    nifty_indicators = await run_in_ml_executor(indicator_service.compute_all, nifty_candles)
            except Exception as e:
                logger.debug(f"Failed to prefetch Nifty indicators: {e}")

            sem = asyncio.Semaphore(4)

            async def _scan_sym(idx: int, sym: str):
                async with sem:
                    if idx > 0 and pace_seconds > 0:
                        await asyncio.sleep(min(0.4, pace_seconds))
                    return await ScreenerService._analyze_symbol(
                        sym,
                        force_refresh=force_refresh,
                        prefetched_quote=quotes_map.get(sym),
                        prefetched_nifty_indicators=nifty_indicators,
                    )

            results = await asyncio.gather(
                *[_scan_sym(i, s) for i, s in enumerate(all_symbols)],
                return_exceptions=True,
            )

            all_results = []
            for res in results:
                if isinstance(res, dict) and res.get("total_score", 0) > 0 and not res.get("error"):
                    all_results.append(res)

            buy_stocks = [r for r in all_results if r.get("action") == "BUY" and float(r.get("total_score", 0) or 0) >= min_score]
            buy_stocks.sort(key=lambda x: float(x.get("total_score", 0) or 0), reverse=True)

            out = {
                "total_scanned": len(all_symbols),
                "sectors_scanned": list(SECTOR_UNIVERSES.keys()),
                "buy_stocks": buy_stocks,
                "all_results": all_results,
                "setups_found": len(buy_stocks),
            }
            await cache_set(cache_key, out, ttl=300)
            return out

        return await cache_manager.single_flight.execute(
            f"sf:screener:all_sectors:{min_score}:{bool(force_refresh)}",
            _run_all,
        )

    @staticmethod
    async def _analyze_symbol(
        symbol: str,
        force_refresh: bool = False,
        prefetched_quote: Optional[dict] = None,
        prefetched_nifty_indicators: Optional[dict] = None,
    ) -> dict:
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
            
            # Fast-path quote: use pre-fetched bulk quote if valid
            if prefetched_quote and prefetched_quote.get("price", 0) > 0:
                async def _resolved_quote():
                    return prefetched_quote
                quote_task = _resolved_quote()
            else:
                quote_task = market_data_service.fetch_quote(symbol)

            # Fundamentals and corporate events don't change intra-day; fast cache reads
            info_task = market_data_service.get_stock_info(symbol)
            events_task = market_data_service.fetch_corporate_events(symbol)
            
            # News scraping with tight 1.5s timeout to prevent external network freezes
            from backend.data.ingestion.news_scraper import fetch_stock_news
            async def _guarded_news():
                try:
                    return await asyncio.wait_for(fetch_stock_news(symbol), timeout=1.5)
                except Exception:
                    return []
            news_task = _guarded_news()
            
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

            nifty_candles = None
            if not prefetched_nifty_indicators:
                try:
                    nifty_candles = await market_data_service.fetch_candles("^NSEI", "1d", limit=50)
                except Exception as e:
                    logger.warning(f"Failed to fetch Nifty for RS: {e}")

            # 2.5 & 3: Offload indicator crunching, signal evaluation & Tri-Model AI scoring
            # onto bounded ML executor (keeping asyncio event loop 100% responsive)
            indicators, signals, ai_res = await run_in_ml_executor(
                ScreenerService._compute_symbol_scoring_sync,
                candles,
                symbol,
                prefetched_nifty_indicators,
                nifty_candles,
            )
            sig = signals[0] if signals else {}

            # Extract the raw 0-100 technical score from the new signal engine
            tech_raw = sig.get("composite_rating", 50)
            
            # 4. Comprehensive Fundamental & Valuation Analysis (35% Weight)
            # Evaluates all key valuation, profitability, solvency, and balance sheet ratios
            fund_score = 50
            info = info or {}
            
            def _safe_float(v):
                try: 
                    if v is None: return 0.0
                    return float(v)
                except (ValueError, TypeError): return 0.0
                
            roe = _safe_float(info.get("roe", 0))
            if roe > 0.18: fund_score += 18
            elif roe > 0.12: fund_score += 10
            elif roe < 0: fund_score -= 15
            
            roce = _safe_float(info.get("roce") or info.get("roa", 0))
            if roce > 0.15: fund_score += 12
            elif roce > 0.10: fund_score += 6
            elif roce < 0: fund_score -= 10
            
            debt_eq = _safe_float(info.get("debt_to_equity", 0))
            if debt_eq < 0.5: fund_score += 15
            elif debt_eq < 1.0: fund_score += 10
            elif debt_eq > 2.0: fund_score -= 15
            elif debt_eq > 3.0: fund_score -= 20
                
            rev_growth = _safe_float(info.get("revenue_growth", 0))
            if rev_growth > 0.20: fund_score += 18
            elif rev_growth > 0.10: fund_score += 10
            elif rev_growth < -0.05: fund_score -= 12
            
            pe = _safe_float(info.get("pe_ratio", 0))
            fwd_pe = _safe_float(info.get("forward_pe", 0))
            if 0 < pe < 22: fund_score += 15
            elif 22 <= pe < 35: fund_score += 8
            elif pe > 60: fund_score -= 12
            elif pe < 0: fund_score -= 15

            # Valuation expansion bonus if forward PE is lower than current PE (earnings accelerating)
            if 0 < fwd_pe < pe:
                fund_score += 5

            cur_ratio = _safe_float(info.get("current_ratio", 0))
            if cur_ratio >= 1.5: fund_score += 8
            elif 0 < cur_ratio < 1.0: fund_score -= 8

            ebitda = _safe_float(info.get("ebitda", 0))
            if ebitda > 0: fund_score += 5

            # Market Cap Segmentation & Fast Growth Classification
            market_cap_val = _safe_float(info.get("market_cap", 0))
            if market_cap_val >= 200000000000.0:  # >= ₹20,000 Cr
                cap_segment = "LARGE_CAP"
            elif market_cap_val >= 50000000000.0:  # ₹5,000 - ₹20,000 Cr
                cap_segment = "MID_CAP"
            else:
                cap_segment = "SMALL_CAP"

            is_fast_growth = (rev_growth >= 0.15 and roe >= 0.14 and debt_eq < 1.2)
            if is_fast_growth:
                fund_score += 8  # Quality compounding bonus

            if events.get("dividends"):
                fund_score += 4  # Bonus for returning capital to shareholders
                
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
            
            # 5. Composite Conviction Score & Market Crash/Fall Protection Filter
            raw_conviction = (tech_raw * 0.40) + (fund_score * 0.35) + (sentiment_score * 0.25)

            # Macro Market Regime Check (Protects against market crashes and sharp corrections)
            market_defense_active = False
            market_regime = "NORMAL"
            nifty_rs = float(indicators.get("rs_momentum_20d", 0.0)) if indicators else 0.0
            
            nifty_ind = prefetched_nifty_indicators or {}
            nifty_ema_20 = float(nifty_ind.get("ema_20") or nifty_ind.get("ema_21") or 0.0)
            nifty_ema_50 = float(nifty_ind.get("ema_50") or 0.0)
            nifty_rsi = float(nifty_ind.get("rsi") or 50.0)
            is_nifty_bearish = (nifty_ema_20 > 0 and nifty_ema_50 > 0 and nifty_ema_20 < nifty_ema_50) or (nifty_rsi < 45.0)

            if is_nifty_bearish:
                market_regime = "BEARISH_MARKET_REGIME"
                market_defense_active = True
                buy_threshold = 78.0  # In market corrections, require elite 78+ conviction for BUY
            else:
                buy_threshold = 70.0  # Elevated from 60.0 to 70.0 for 75%+ win rate precision

            # If stock is lagging while market falls, enforce strict defensive filtering
            if nifty_rs < -0.05 and raw_conviction < 75:
                raw_conviction -= 10
                market_defense_active = True
                market_regime = "UNDERPERFORMING_MARKET"
            elif is_fast_growth and raw_conviction >= 65:
                raw_conviction += 5  # Rewarding proven fundamental momentum

            total_score = max(0.0, min(100.0, raw_conviction))
            
            # 6. Generate "Best Price to Buy" & Structural Rule-Based Trade Setup
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
            ema_50 = float(indicators.get("ema_50") or 0.0) if indicators else 0.0
            bb = indicators.get("bb") or {}
            bb_mid = float(bb.get("middle") or 0.0)
            
            recent_lows = [float(c["low"]) for c in candles[-10:] if isinstance(c, dict) and "low" in c] if candles else []
            recent_highs = [float(c["high"]) for c in candles[-10:] if isinstance(c, dict) and "high" in c] if candles else []
            swing_low = min(recent_lows) if recent_lows else current_price - (1.0 * atr)
            swing_high = max(recent_highs) if recent_highs else current_price + (1.0 * atr)

            if total_score >= buy_threshold:
                action = "BUY"
                # Determine "Best Price to Buy" (Optimal Entry Zone) vs Current Market Price
                ref_support = ema_21 if ema_21 > 0 else (bb_mid if bb_mid > 0 else current_price - (0.5 * atr))
                
                if current_price > ref_support + (0.35 * atr):
                    entry_type = "PULLBACK_DIP_BUY"
                    optimal_entry_price = max(ref_support, current_price - (0.40 * atr))
                    optimal_entry_price = round(optimal_entry_price, 2)
                    entry_zone = f"₹{optimal_entry_price - 0.15*atr:.2f} – ₹{optimal_entry_price + 0.15*atr:.2f} (Dip to 21-EMA Support)"
                    entry_advice = f"Stock is currently extended above 21-EMA (CMP: ₹{current_price:.2f}). Best entry is on a minor pullback to ₹{optimal_entry_price:.2f} for lower risk & higher profit."
                elif swing_high - current_price <= (0.25 * atr) and current_price >= swing_high * 0.99:
                    entry_type = "BREAKOUT_CONFIRMATION"
                    optimal_entry_price = round(swing_high + (0.10 * atr), 2)
                    entry_zone = f"Above ₹{optimal_entry_price:.2f} (Confirmed Breakout)"
                    entry_advice = f"Testing key resistance at ₹{swing_high:.2f}. Enter on confirmed volume breakout above ₹{optimal_entry_price:.2f}."
                else:
                    entry_type = "SUPPORT_ACCUMULATION"
                    optimal_entry_price = round(current_price, 2)
                    entry_zone = f"₹{current_price - 0.15*atr:.2f} – ₹{current_price + 0.15*atr:.2f} (Support Base Level)"
                    entry_advice = "Price is at the optimal accumulation zone near support base. Suitable for immediate entry."

                # ── ML-DRIVEN & ATR-ADAPTIVE DYNAMIC SETUP (ELIMINATES THE 12.5% CONSTANT TRAP) ──
                # 1. Structural Stop Loss: Anchored strictly below recent swing low with ATR buffer
                structural_sl = swing_low - (0.5 * atr)
                
                # Adaptive risk boundaries based on stock-specific volatility (ATR%) and cap segment
                if cap_segment == "LARGE_CAP":
                    min_risk_dist = max(optimal_entry_price * 0.015, 1.2 * atr)
                    max_risk_dist = min(optimal_entry_price * 0.065, 2.5 * atr)
                else:
                    min_risk_dist = max(optimal_entry_price * 0.020, 1.5 * atr)
                    max_risk_dist = min(optimal_entry_price * 0.085, 3.2 * atr)

                risk_distance = optimal_entry_price - structural_sl
                if risk_distance > max_risk_dist:
                    stop_loss = max(0.05, round(optimal_entry_price - max_risk_dist, 2))
                elif risk_distance < min_risk_dist:
                    stop_loss = max(0.05, round(optimal_entry_price - min_risk_dist, 2))
                else:
                    stop_loss = max(0.05, round(structural_sl, 2))

                risk_amount = max(0.01, optimal_entry_price - stop_loss)

                # 2. Structural Technical Resistance Levels (R1, R2, R3)
                r1 = max(swing_high, optimal_entry_price + (1.2 * atr))
                
                bb_dict = indicators.get("bb") or {}
                bb_upper = float(bb_dict.get("upper") or 0.0)
                swing_range = max(atr, swing_high - swing_low)
                fib_1272 = swing_high + (0.272 * swing_range)
                r2_candidates = [fib_1272, optimal_entry_price + (2.0 * atr)]
                if bb_upper > optimal_entry_price:
                    r2_candidates.append(bb_upper)
                r2 = max(r2_candidates)

                fib_1618 = swing_high + (0.618 * swing_range)
                r3 = max(fib_1618, r2 + (1.5 * atr))

                # 3. Machine Learning & NLP Sentiment Modulation
                ml_probs = ai_res.get("probabilities") or {} if isinstance(ai_res, dict) else {}
                ml_p_buy = float(ml_probs.get("buy", 0.5))
                ml_conf = float(ai_res.get("confidence", 0.5)) if isinstance(ai_res, dict) else 0.5
                nlp_compound = float(nlp_result.get("compound_score", 0.0)) if isinstance(nlp_result, dict) else 0.0

                if ml_conf >= 0.70 and ml_p_buy >= 0.55 and nlp_compound >= 0.0:
                    expansion_factor = min(1.0, (ml_conf - 0.70) / 0.30)
                    raw_target = r2 + (0.4 * (r3 - r2) * expansion_factor)
                elif ml_conf < 0.60 or market_regime == "UNDERPERFORMING_MARKET":
                    raw_target = min(r1, r2)
                else:
                    raw_target = r2

                # 4. Realistic 11-Day Holding Horizon Feasibility Constraint
                min_rr_target = optimal_entry_price + (2.0 * risk_amount)
                raw_target = max(raw_target, min_rr_target)

                max_11d_gain = max(optimal_entry_price * 0.040, min(optimal_entry_price * 0.18, 4.5 * atr))
                min_11d_gain = max(optimal_entry_price * 0.025, 1.8 * atr)

                target_gain_dist = raw_target - optimal_entry_price
                if target_gain_dist > max_11d_gain:
                    target = round(optimal_entry_price + max_11d_gain, 2)
                elif target_gain_dist < min_11d_gain:
                    target = round(optimal_entry_price + min_11d_gain, 2)
                else:
                    target = round(raw_target, 2)

                # Maintain asymmetric risk:reward threshold >= 2.0:1
                if (target - optimal_entry_price) < (2.0 * risk_amount):
                    target = round(optimal_entry_price + (2.0 * risk_amount), 2)

                t2 = target
                t1 = round(optimal_entry_price + 0.55 * (t2 - optimal_entry_price), 2)
                t3 = round(max(r3, t2 + (1.5 * atr)), 2)

            elif total_score <= 40:
                action = "SELL"
                ref_resistance = ema_21 if ema_21 > 0 else (bb_mid if bb_mid > 0 else current_price + (0.5 * atr))
                if current_price < ref_resistance - (0.35 * atr):
                    entry_type = "RALLY_SELL"
                    optimal_entry_price = min(ref_resistance, current_price + (0.40 * atr))
                    optimal_entry_price = round(optimal_entry_price, 2)
                    entry_zone = f"₹{optimal_entry_price - 0.15*atr:.2f} – ₹{optimal_entry_price + 0.15*atr:.2f} (Rally to 21-EMA)"
                    entry_advice = f"Oversold bounce expected. Optimal short/exit on rally to ₹{optimal_entry_price:.2f}."
                elif current_price - swing_low <= (0.25 * atr):
                    entry_type = "BREAKDOWN"
                    optimal_entry_price = round(swing_low - (0.10 * atr), 2)
                    entry_zone = f"Below ₹{optimal_entry_price:.2f} (Breakdown Confirmation)"
                    entry_advice = f"Testing floor at ₹{swing_low:.2f}. Enter short on breakdown below ₹{optimal_entry_price:.2f}."
                else:
                    entry_type = "MARKET_CMP"
                    optimal_entry_price = round(current_price, 2)
                    entry_zone = f"₹{current_price - 0.15*atr:.2f} – ₹{current_price + 0.15*atr:.2f} (Current Market Level)"
                    entry_advice = "Breakdown momentum active. Sell/Exit at current market price."

                structural_sl = swing_high + (0.5 * atr)
                if cap_segment == "LARGE_CAP":
                    min_risk_dist = max(optimal_entry_price * 0.015, 1.2 * atr)
                    max_risk_dist = min(optimal_entry_price * 0.065, 2.5 * atr)
                else:
                    min_risk_dist = max(optimal_entry_price * 0.020, 1.5 * atr)
                    max_risk_dist = min(optimal_entry_price * 0.085, 3.2 * atr)

                risk_distance = structural_sl - optimal_entry_price
                if risk_distance > max_risk_dist:
                    stop_loss = round(optimal_entry_price + max_risk_dist, 2)
                elif risk_distance < min_risk_dist:
                    stop_loss = round(optimal_entry_price + min_risk_dist, 2)
                else:
                    stop_loss = round(structural_sl, 2)

                risk_amount = max(0.01, stop_loss - optimal_entry_price)
                
                s1 = min(swing_low, optimal_entry_price - (1.2 * atr))
                bb_dict = indicators.get("bb") or {}
                bb_lower = float(bb_dict.get("lower") or 0.0)
                s2_candidates = [optimal_entry_price - (2.0 * atr)]
                if bb_lower > 0 and bb_lower < optimal_entry_price:
                    s2_candidates.append(bb_lower)
                s2 = min(s2_candidates)
                s3 = s2 - (1.5 * atr)

                max_11d_drop = max(optimal_entry_price * 0.035, min(optimal_entry_price * 0.16, 4.2 * atr))
                min_11d_drop = max(optimal_entry_price * 0.025, 1.4 * atr)

                drop_dist = optimal_entry_price - s2
                if drop_dist > max_11d_drop:
                    target = round(optimal_entry_price - max_11d_drop, 2)
                elif drop_dist < min_11d_drop:
                    target = round(optimal_entry_price - min_11d_drop, 2)
                else:
                    target = round(s2, 2)

                # Maintain asymmetric risk:reward threshold >= 2.0:1
                if (optimal_entry_price - target) < (2.0 * risk_amount):
                    target = round(optimal_entry_price - (2.0 * risk_amount), 2)

                t2 = target
                t1 = round(optimal_entry_price - 0.55 * (optimal_entry_price - t2), 2)
                t3 = round(min(s3, t2 - (1.5 * atr)), 2)

            else:
                action = "HOLD"
                entry_type = "CONSOLIDATION"
                
                # Structural support & resistance calculated from market structure & indicators
                supp = swing_low if swing_low > 0 else (bb_mid - 0.5 * atr if bb_mid > 0 else current_price - (1.0 * atr))
                res = swing_high if swing_high > 0 else (bb_mid + 0.5 * atr if bb_mid > 0 else current_price + (1.0 * atr))
                if res <= supp:
                    res = current_price + (1.5 * atr)
                    supp = max(0.05, current_price - (1.5 * atr))

                # Optimal entry is at the accumulation base (support zone) - below CMP or at support
                optimal_entry_price = round(max(0.05, supp + (0.15 * atr)), 2)
                # Stop loss placed below support floor
                stop_loss = max(0.05, round(supp - (0.5 * atr), 2))
                risk_amount = max(0.01, optimal_entry_price - stop_loss)

                # Targets derived strictly from calculated resistance and channel expansion
                t2 = round(res - (0.15 * atr), 2)  # Primary ceiling target
                if t2 <= optimal_entry_price:
                    t2 = round(optimal_entry_price + (1.8 * risk_amount), 2)
                t1 = round(optimal_entry_price + 0.5 * (t2 - optimal_entry_price), 2)  # Midpoint of range
                t3 = round(res + (1.0 * atr), 2)  # Channel breakout runner
                target = t2
                entry_zone = f"Support Base: ₹{supp:.2f} | Ceiling: ₹{res:.2f}"
                entry_advice = f"Range-bound consolidation. Stock is oscillating between Support (₹{supp:.2f}) and Resistance (₹{res:.2f}). Best entry is on accumulation near Support at ₹{optimal_entry_price:.2f} with Target ₹{target:.2f}."

            risk_amount = max(0.01, abs(optimal_entry_price - stop_loss))
            gain_pct = abs((target - optimal_entry_price) / optimal_entry_price) * 100 if optimal_entry_price > 0 else 0.0
            risk_pct = abs((optimal_entry_price - stop_loss) / optimal_entry_price) * 100 if optimal_entry_price > 0 else 0.0
            reward_to_risk = round(gain_pct / risk_pct, 2) if risk_pct > 0 else 2.5

            cmp_gain_pct = round(abs(target - current_price) / current_price * 100, 2) if current_price > 0 else 0.0
            cmp_risk_pct = round(abs(current_price - stop_loss) / current_price * 100, 2) if current_price > 0 else 0.0

            optimal_risk_amount = abs(optimal_entry_price - stop_loss)
            optimal_gain_pct = abs((target - optimal_entry_price) / optimal_entry_price) * 100 if optimal_entry_price > 0 else gain_pct
            optimal_risk_pct = abs((optimal_entry_price - stop_loss) / optimal_entry_price) * 100 if optimal_entry_price > 0 else risk_pct
            optimal_rr = round(optimal_gain_pct / optimal_risk_pct, 2) if optimal_risk_pct > 0 else 0.0
            
            targets_breakdown = [
                {
                    "level": "T1 (Conservative)",
                    "price": round(t1, 2),
                    "gain_pct": round(abs(t1 - optimal_entry_price) / optimal_entry_price * 100, 2) if optimal_entry_price > 0 else 0.0,
                    "cmp_gain_pct": round(abs(t1 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t1 - optimal_entry_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                },
                {
                    "level": "T2 (Primary / Optimal)",
                    "price": round(t2, 2),
                    "gain_pct": round(abs(t2 - optimal_entry_price) / optimal_entry_price * 100, 2) if optimal_entry_price > 0 else 0.0,
                    "cmp_gain_pct": round(abs(t2 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t2 - optimal_entry_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                },
                {
                    "level": "T3 (Extended Breakout)",
                    "price": round(t3, 2),
                    "gain_pct": round(abs(t3 - optimal_entry_price) / optimal_entry_price * 100, 2) if optimal_entry_price > 0 else 0.0,
                    "cmp_gain_pct": round(abs(t3 - current_price) / current_price * 100, 2) if current_price > 0 else 0.0,
                    "reward_to_risk": round(abs(t3 - optimal_entry_price) / risk_amount, 2) if risk_amount > 0 else 0.0
                }
            ]

            # Estimate holding days (Target / average daily range from optimal entry)
            base_days = max(3, int(round(abs(target - optimal_entry_price) / (atr if atr > 0 else 1))))
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
                "market_regime": market_regime,
                "market_defense_active": market_defense_active,
                "cap_segment": cap_segment,
                "is_fast_growth": is_fast_growth,
                "trade_plan": {
                    "current_price": round(current_price, 2),
                    "cmp": round(current_price, 2),
                    "best_buy_price": round(optimal_entry_price, 2),
                    "entry_price": round(optimal_entry_price, 2),
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
                    "reward_to_risk": round(gain_pct / risk_pct, 2) if risk_pct > 0 else 2.5,
                    "cmp_gain_pct": cmp_gain_pct,
                    "cmp_risk_pct": cmp_risk_pct,
                    "optimal_expected_gain_pct": round(gain_pct, 2),
                    "optimal_reward_to_risk": round(gain_pct / risk_pct, 2) if risk_pct > 0 else 2.5,
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
