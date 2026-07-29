"""
Celery tasks for paper trading module.
"""

import asyncio
from datetime import datetime
from sqlalchemy import select
from celery.utils.log import get_task_logger
import pytz

from backend.celery_app import celery_app
from backend.core.database import AsyncSessionLocal
from backend.services.paper_trading import paper_trading_service
from backend.services.market_data import market_data_service

logger = get_task_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")


def _is_market_open() -> bool:
    """Check if NSE market is currently open (09:15–15:30 IST Mon-Fri)."""
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    market_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now_ist <= market_close


async def _evaluate_orders_async():
    if not _is_market_open():
        logger.info("Market is closed. Skipping paper trade evaluation.")
        return

    async with AsyncSessionLocal() as db:
        logger.info("Evaluating pending limit/stop orders...")
        await paper_trading_service.evaluate_pending_orders(db)
        
        logger.info("Evaluating open trades for target/SL exits...")
        await paper_trading_service.evaluate_open_trades(db)
        
        await db.commit()


async def _square_off_intraday_async():
    from backend.models.paper_trade import PaperTrade
    async with AsyncSessionLocal() as db:
        logger.info("Auto-squaring off all open INTRADAY positions...")
        
        result = await db.execute(
            select(PaperTrade).where(
                PaperTrade.status == "OPEN",
                PaperTrade.product_type == "INTRADAY"
            )
        )
        open_intraday_trades = result.scalars().all()
        
        count = 0
        for trade in open_intraday_trades:
            try:
                await paper_trading_service.close_trade(db, str(trade.id), str(trade.user_id))
                count += 1
            except Exception as e:
                logger.error(f"Failed to square off trade {trade.id}: {str(e)}")
                
        await db.commit()
        logger.info(f"Successfully squared off {count} INTRADAY trades.")


@celery_app.task(name="backend.tasks.trading_tasks.evaluate_paper_trades")
def evaluate_paper_trades():
    """
    Periodic task to evaluate pending orders and open trades against live market prices.
    Runs every minute.
    """
    asyncio.run(_evaluate_orders_async())


@celery_app.task(name="backend.tasks.trading_tasks.square_off_intraday")
def square_off_intraday():
    """
    Square off all open INTRADAY positions at 15:20 IST.
    """
    asyncio.run(_square_off_intraday_async())
