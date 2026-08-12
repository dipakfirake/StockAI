"""
Celery application and task definitions.

Tasks:
- ingest_market_data: periodic OHLCV ingestion (every 1 min during market hours)
- evaluate_alerts: periodic alert evaluation (every 30 seconds)
- run_backtest_task: async backtest execution

Schedule:
- Only runs Mon–Fri, 09:15–15:30 IST (NSE market hours)
- Respects NSE holidays
"""

from celery import Celery
from celery.schedules import crontab

from backend.core.config import settings

celery_app = Celery(
    "ai_stock_research",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.tasks.market_tasks", "backend.tasks.alert_tasks", "backend.tasks.trading_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Beat schedule — periodic tasks
celery_app.conf.beat_schedule = {
    # Data ingestion: every 1 minute, Mon–Fri 09:15–15:30 IST
    "ingest-market-data": {
        "task": "backend.tasks.market_tasks.ingest_watchlist_stocks",
        "schedule": 60.0,  # every 60 seconds
        "options": {"expires": 55},
    },
    # Alert evaluation: every 30 seconds
    "evaluate-alerts": {
        "task": "backend.tasks.alert_tasks.evaluate_all_alerts",
        "schedule": 30.0,
        "options": {"expires": 25},
    },
    # Bulk Market Analysis: every 15 minutes during market hours
    "bulk-market-analysis": {
        "task": "backend.tasks.market_tasks.analyze_market_bulk",
        "schedule": 900.0, # 15 minutes
    },
    # Paper Trading evaluation: every 60 seconds
    "evaluate-paper-trades": {
        "task": "backend.tasks.trading_tasks.evaluate_paper_trades",
        "schedule": 60.0,
        "options": {"expires": 55},
    },
    # Daily EOD processing: 15:35 IST
    "eod-processing": {
        "task": "backend.tasks.market_tasks.end_of_day_processing",
        "schedule": crontab(hour=10, minute=5),  # 15:35 IST = 10:05 UTC
    },
    # Auto Square-off Intraday: 15:20 IST
    "square-off-intraday": {
        "task": "backend.tasks.trading_tasks.square_off_intraday",
        "schedule": crontab(hour=9, minute=50),  # 15:20 IST = 09:50 UTC
    },
}
