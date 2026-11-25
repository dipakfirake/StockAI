"""Celery tasks for automated EOD Swing Screener scan & 11-day Swing Trade Audit updates."""

import asyncio
import concurrent.futures
from backend.celery_app import celery_app
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def _run_async(coro):
    """Safely execute coroutine whether an event loop is running or not."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()


async def run_eod_screener_and_audit_sync_async():
    """
    Asynchronous implementation of automated End-of-Day (EOD) Market Close Pipeline:
    1. Runs fresh market scan via Swing Screener on liquid market symbols.
    2. Auto-catalogs high-conviction swing recommendations (score >= 70) into active 11-day audit cycle.
    3. Executes 'Sync 11-Day Prices' (update_daily_prices) to evaluate today's closing prices,
       stops, targets, and Coupled Ratchet thresholds.
    4. Generates a freshly stamped .xlsx audit workbook with up-to-the-minute PnL.
    """
    from backend.core.database import AsyncSessionLocal
    from backend.services.screener import ScreenerService
    from backend.services.swing_audit_service import swing_audit_service
    from backend.data.ingestion.candle_ingestion import NSE_NIFTY50_SYMBOLS

    # Phase 1: Fresh market scan across ALL 10 screener sectors (Oil & Resources, Small Momentum, Midcap, Nifty 50, Banking, IT, etc.)
    logger.info("EOD Pipeline Step 1/3: Running fresh multi-sector Swing Screener scan across all universes...")
    screener_data = await ScreenerService.run_all_sectors_screener(force_refresh=True, min_score=70.0, pace_seconds=0.30)
    buy_candidates = screener_data.get("buy_stocks", []) if isinstance(screener_data, dict) else []
    logger.info(f"EOD Pipeline: Found {len(buy_candidates)} BUY candidate(s) across all {screener_data.get('total_scanned', 0)} symbols scanned.")

    cataloged_count = 0
    async with AsyncSessionLocal() as db:
        # Phase 2: Auto-catalog elite high-conviction recommendations (score >= 78.0, top 5 platform-wide)
        logger.info("EOD Pipeline Step 2/3: Cataloging elite high-conviction trades (score >= 78) into active audit cycle...")
        eligible_candidates = [
            item for item in buy_candidates
            if float(item.get("total_score", 0.0) or 0.0) >= 78.0 and item.get("trade_plan") and item.get("symbol")
        ]
        eligible_candidates.sort(key=lambda x: float(x.get("total_score", 0.0) or 0.0), reverse=True)
        top_candidates = eligible_candidates[:5]  # Strict limit: max 5 highest-conviction trades per day

        for item in top_candidates:
            try:
                score = float(item.get("total_score", 0.0) or 0.0)
                plan = item.get("trade_plan")
                sym = item.get("symbol")
                await swing_audit_service.track_swing_trade(
                    db=db,
                    symbol=sym,
                    trade_plan=plan,
                    company_name=item.get("name") or sym,
                    total_score=score
                )
                cataloged_count += 1
            except Exception as cat_err:
                logger.warning(f"Could not auto-catalog {item.get('symbol')}: {cat_err}")

        # Phase 3: Sync 11-Day Prices across all active trades & generate Excel workbook
        logger.info("EOD Pipeline Step 3/3: Synchronizing 11-day prices and generating Excel workbook...")
        sync_result = await swing_audit_service.update_daily_prices(db)
        logger.info(f"EOD Pipeline complete. Cataloged: {cataloged_count}, Sync result: {sync_result}")
        return {
            "status": "success",
            "screener_candidates": len(buy_candidates),
            "cataloged_count": cataloged_count,
            "sync_result": sync_result
        }


@celery_app.task(name="backend.tasks.swing_audit_tasks.run_eod_screener_and_audit_sync")
def run_eod_screener_and_audit_sync():
    """
    Automated End-of-Day (EOD) Market Close Pipeline Celery Task (runs Mon-Fri at 15:35 IST / 10:05 UTC).
    """
    logger.info("Starting automated EOD Swing Screener scan & 11-day Audit sync pipeline...")
    try:
        return _run_async(run_eod_screener_and_audit_sync_async())
    except Exception as e:
        logger.error(f"EOD Screener & Audit sync pipeline failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(name="backend.tasks.swing_audit_tasks.sync_swing_trade_audits")
def sync_swing_trade_audits():
    """
    Direct price synchronization task (runs daily at 15:45 IST).
    Updates price milestones (Day 1..11), triggers SL / Target executions,
    calculates cycle PnL, and updates the Excel audit report.
    """
    logger.info("Starting automated 11-day Swing Trade Audit price sync...")
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.services.swing_audit_service import swing_audit_service

        async def _run():
            async with AsyncSessionLocal() as db:
                return await swing_audit_service.update_daily_prices(db)

        return _run_async(_run())
    except Exception as e:
        logger.error(f"Swing Audit sync failed: {e}")
        return {"error": str(e)}
