"""
Celery tasks for paper trading module.
"""

import asyncio
from datetime import datetime
from sqlalchemy import select
from celery.utils.log import get_task_logger
import pytz

from backend.celery_app import celery_app
from backend.core.celery_async import run_in_worker_loop
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
                closed_trade = await paper_trading_service.close_trade(db, str(trade.id), str(trade.user_id))
                if getattr(closed_trade, "status", None) == "CLOSED":
                    closed_trade.closed_by = "AUTO_SYSTEM"
                    closed_trade.exit_reason = "SYSTEM_AUTO_EOD_INTRADAY"
                    await paper_trading_service._deactivate_exit_alerts_if_flat(db, str(trade.user_id), trade.symbol)
                    try:
                        from backend.services.notification_service import notify_auto_sell_exit
                        exit_meta = paper_trading_service.resolve_trade_exit_details(closed_trade)
                        exit_label = paper_trading_service.EXIT_REASON_LABELS.get(
                            "SYSTEM_AUTO_EOD_INTRADAY",
                            "System Auto-Sell (15:20 IST Intraday Square-Off)",
                        )
                        await notify_auto_sell_exit(
                            db, closed_trade, "SYSTEM_AUTO_EOD_INTRADAY", exit_label, exit_meta
                        )
                    except Exception:
                        pass
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
    run_in_worker_loop(_evaluate_orders_async())


@celery_app.task(name="backend.tasks.trading_tasks.square_off_intraday")
def square_off_intraday():
    """
    Square off all open INTRADAY positions at 15:20 IST.
    """
    run_in_worker_loop(_square_off_intraday_async())
