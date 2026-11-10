"""Celery task for automated 11-day Swing Trade Audit updates."""

import asyncio
from backend.celery_app import celery_app
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


@celery_app.task(name="backend.tasks.swing_audit_tasks.sync_swing_trade_audits")
def sync_swing_trade_audits():
    """
    Daily scheduled task (runs post-market at 15:45 IST).
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

        res = asyncio.run(_run())
        logger.info(f"Automated Swing Audit sync completed: {res}")
        return res
    except Exception as e:
        logger.error(f"Swing Audit sync failed: {e}")
        return {"error": str(e)}
