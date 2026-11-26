"""Market data Celery tasks — periodic OHLCV ingestion."""

import asyncio
from backend.celery_app import celery_app
from backend.core.celery_async import run_in_worker_loop
from backend.core.logging_config import get_logger
from backend.data.ingestion.nse_scraper import nse_scraper

logger = get_logger(__name__)


@celery_app.task(name="backend.tasks.market_tasks.ingest_watchlist_stocks", bind=True, max_retries=3)
def ingest_watchlist_stocks(self):
    """
    Ingest latest OHLCV candles for all watchlisted stocks.
    Respects market hours — does nothing outside 09:15–15:30 IST on trading days.
    """
    if not nse_scraper.is_market_open():
        logger.debug("Market closed — skipping ingestion")
        return {"skipped": True, "reason": "Market closed"}

    try:
        from backend.data.ingestion.candle_ingestion import ingest_candles, NSE_NIFTY50_SYMBOLS
        async def _run_all():
            total_inserted = 0
            batch_size = 5
            for i in range(0, len(NSE_NIFTY50_SYMBOLS), batch_size):
                batch = NSE_NIFTY50_SYMBOLS[i:i + batch_size]
                results = await asyncio.gather(*[ingest_candles(sym, "1d", period="5d") for sym in batch], return_exceptions=True)
                for r in results:
                    if isinstance(r, int):
                        total_inserted += r
                await asyncio.sleep(0.5)
            return total_inserted
        total = run_in_worker_loop(_run_all())
        logger.info(f"Ingestion task: {total} candles updated")
        return {"inserted": total}
    except Exception as e:
        logger.error(f"Ingestion task failed: {e}")
        raise self.retry(exc=e, countdown=30)


@celery_app.task(name="backend.tasks.market_tasks.end_of_day_processing")
def end_of_day_processing():
    """End-of-day: generate daily signals, clear caches, and prepare for next day."""
    logger.info("Running end-of-day processing")
    
    # Run async logic
    try:
        run_in_worker_loop(_eod_processing_async())
        return {"status": "EOD processing complete"}
    except Exception as e:
        logger.error(f"EOD processing failed: {e}")
        return {"error": str(e)}

async def _eod_processing_async():
    from backend.core.cache import get_redis
    from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS, ingest_candles
    from backend.services.market_data import market_data_service
    from backend.services.indicators import indicator_service
    
    # 1. Clear caches to ensure fresh data for the next day
    try:
        r = await get_redis()
        await r.flushdb()
        logger.info("EOD: Redis cache cleared")
    except Exception as e:
        logger.warning(f"EOD: Could not flush Redis cache: {e}")
        
    # 2. Ingest one final time for the day to get the true EOD candle
    total_inserted = 0
    for sym in NSE_NIFTY50_SYMBOLS:
        inserted = await ingest_candles(sym, "1d", period="1d")
        total_inserted += inserted
        
        # 3. Pre-compute and cache indicators so morning load is fast
        candles = await market_data_service.fetch_candles(sym, "1d", limit=100)
        if len(candles) >= 30:
            indicator_service.compute_all(candles)
            
        await asyncio.sleep(1.5)
            
    logger.info(f"EOD: Re-ingested {total_inserted} candles and pre-computed indicators")


@celery_app.task(name="backend.tasks.market_tasks.analyze_market_bulk")
def analyze_market_bulk():
    """Run the AI Screener on a large basket of stocks and cache the results."""
    logger.info("Running bulk market analysis...")
    try:
        results = run_in_worker_loop(_analyze_market_bulk_async())
        return {"status": "Bulk analysis complete", "stocks_analyzed": len(results)}
    except Exception as e:
        logger.error(f"Bulk analysis failed: {e}")
        return {"error": str(e)}

async def _analyze_market_bulk_async():
    from backend.services.screener import ScreenerService
    from backend.core.cache import cache_set
    from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS
    
    # Run the screener on a large subset (using NIFTY 50 for stability, can be expanded to 500)
    screener_results = await ScreenerService.run_screener(NSE_NIFTY50_SYMBOLS, force_refresh=True, pace_seconds=0.30)
    
    # Save the entire massive JSON payload to Redis
    await cache_set("screener:bulk:latest", screener_results, ttl=3600)
    logger.info(f"Bulk analysis finished for {len(screener_results)} stocks and cached to Redis")
    return screener_results


@celery_app.task(name="backend.tasks.market_tasks.run_sector_screener_task", bind=True)
def run_sector_screener_task(self, sector: str = "NIFTY_50", force_refresh: bool = True, job_id: str = None):
    """
    Dedicated Celery task that executes full-pipeline AI screening for a sector universe
    in the background worker container, keeping Uvicorn at 0% CPU and zero timeouts.
    """
    logger.info(f"Celery executing sector screener for {sector} (job_id: {job_id})...")
    try:
        results = run_in_worker_loop(_run_sector_screener_async(sector=sector, force_refresh=force_refresh, job_id=job_id))
        return {
            "status": "success",
            "sector": sector,
            "job_id": job_id,
            "stocks_analyzed": len(results.get("all_results", []) if isinstance(results, dict) else []),
        }
    except Exception as e:
        logger.error(f"Celery sector screener failed for {sector}: {e}")
        if job_id:
            try:
                from backend.core.cache import cache_set
                run_in_worker_loop(cache_set(f"screener_job:{job_id}", {
                    "job_id": job_id,
                    "status": "failed",
                    "error": str(e),
                }, ttl=600))
            except Exception:
                pass
        return {"error": str(e)}


async def _run_sector_screener_async(sector: str, force_refresh: bool, job_id: str = None):
    from backend.services.screener import ScreenerService, SECTOR_UNIVERSES, NIFTY_UNIVERSE
    from backend.core.cache import cache_set
    from datetime import datetime, timezone

    norm_sector = sector.upper().replace(" ", "_") if sector else "DEFAULT"
    symbols = SECTOR_UNIVERSES.get(norm_sector, NIFTY_UNIVERSE)

    async def _progress_cb(completed: int, total: int):
        if job_id:
            pct = min(98, max(5, int((completed / max(1, total)) * 95) + 3))
            try:
                await cache_set(f"screener_job:{job_id}", {
                    "job_id": job_id,
                    "sector": norm_sector,
                    "status": "running",
                    "progress": pct,
                    "completed": completed,
                    "total": total,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, ttl=600)
            except Exception:
                pass

    def _sync_progress_cb(completed: int, total: int):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_progress_cb(completed, total))
        except Exception:
            pass

    res = await ScreenerService.run_screener(
        symbols=symbols,
        sector=norm_sector,
        force_refresh=force_refresh,
        pace_seconds=0.15,
        progress_cb=_sync_progress_cb,
    )

    if job_id:
        try:
            persisted = {
                "job_id": job_id,
                "sector": norm_sector,
                "status": "completed",
                "progress": 100,
                "completed": len(symbols),
                "total": len(symbols),
                "result": res,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
            await cache_set(f"screener_job:{job_id}", persisted, ttl=600)
        except Exception:
            pass

    return res

