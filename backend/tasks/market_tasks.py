"""Market data Celery tasks — periodic OHLCV ingestion."""

import asyncio
from backend.celery_app import celery_app
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
            for sym in NSE_NIFTY50_SYMBOLS:
                total_inserted += await ingest_candles(sym, "1d", period="5d")
                await asyncio.sleep(1.5)  # Rate limiting delay for yfinance
            return total_inserted
        total = asyncio.run(_run_all())
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
        asyncio.run(_eod_processing_async())
        return {"status": "EOD processing complete"}
    except Exception as e:
        logger.error(f"EOD processing failed: {e}")
        return {"error": str(e)}

async def _eod_processing_async():
    from backend.core.cache import redis_client
    from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS, ingest_candles
    from backend.services.market_data import market_data_service
    from backend.services.indicators import indicator_service
    
    # 1. Clear caches to ensure fresh data for the next day
    if redis_client:
        await redis_client.flushdb()
        logger.info("EOD: Redis cache cleared")
        
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
        results = asyncio.run(_analyze_market_bulk_async())
        return {"status": "Bulk analysis complete", "stocks_analyzed": len(results)}
    except Exception as e:
        logger.error(f"Bulk analysis failed: {e}")
        return {"error": str(e)}

async def _analyze_market_bulk_async():
    from backend.services.screener import ScreenerService
    from backend.core.cache import cache_set
    from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS
    
    # Run the screener on a large subset (using NIFTY 50 for stability, can be expanded to 500)
    screener_results = await ScreenerService.run_screener(NSE_NIFTY50_SYMBOLS)
    
    # Save the entire massive JSON payload to Redis
    await cache_set("screener:bulk:latest", screener_results, ttl=3600)
    logger.info(f"Bulk analysis finished for {len(screener_results)} stocks and cached to Redis")
    return screener_results
