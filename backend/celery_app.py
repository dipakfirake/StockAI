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
from celery.signals import worker_process_shutdown, task_failure

from backend.core.config import settings

celery_app = Celery(
    "ai_stock_research",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "backend.tasks.market_tasks",
        "backend.tasks.alert_tasks",
        "backend.tasks.trading_tasks",
        "backend.tasks.swing_audit_tasks",
        "backend.tasks.maintenance_tasks",
    ],
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
    worker_send_task_events=True,
    task_send_sent_event=True,
    broker_heartbeat=30,
    event_queue_expires=60,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=1,
    broker_transport_options={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5, "socket_timeout": 1.0, "socket_connect_timeout": 1.0},
    result_backend_transport_options={"max_retries": 1, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5, "socket_timeout": 1.0, "socket_connect_timeout": 1.0},
)

# Beat schedule — periodic tasks
celery_app.conf.beat_schedule = {
    # Data ingestion: every 3 minutes, Mon–Fri 09:15–15:30 IST
    "ingest-market-data": {
        "task": "backend.tasks.market_tasks.ingest_watchlist_stocks",
        "schedule": 180.0,  # every 3 minutes
        "options": {"expires": 160},
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
    # Periodic Sector Screener Pre-Warming: ensures Redis always has fresh high-conviction ML setups
    "prewarm-nifty50-screener": {
        "task": "backend.tasks.market_tasks.run_sector_screener_task",
        "schedule": 900.0,
        "kwargs": {"sector": "NIFTY_50", "force_refresh": True},
        "options": {"expires": 850},
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
    # Automated EOD Market Close Pipeline (15:35 IST / 10:05 UTC Mon-Fri):
    # 1. Fresh Swing Screener scan -> 2. Auto-catalog high-score setups -> 3. Sync 11-Day Prices & Excel
    "eod-swing-screener-and-audit-sync": {
        "task": "backend.tasks.swing_audit_tasks.run_eod_screener_and_audit_sync",
        "schedule": crontab(hour=10, minute=5, day_of_week="1-5"),
    },
    # Auto Square-off Intraday: 15:20 IST
    "square-off-intraday": {
        "task": "backend.tasks.trading_tasks.square_off_intraday",
        "schedule": crontab(hour=9, minute=50),  # 15:20 IST = 09:50 UTC
    },
    # Secondary Swing Trade Audit Sync: 15:45 IST (10:15 UTC) Mon-Fri
    "sync-swing-trade-audits": {
        "task": "backend.tasks.swing_audit_tasks.sync_swing_trade_audits",
        "schedule": crontab(hour=10, minute=15, day_of_week="1-5"),
    },
    # Nightly Portable Database Snapshot + Automated DR Restore Drill: 02:30 IST (21:00 UTC)
    "nightly-db-backup-and-dr-drill": {
        "task": "backend.tasks.maintenance_tasks.run_nightly_backup_and_dr_check",
        "schedule": crontab(hour=21, minute=0),
    },
}


@task_failure.connect
def _on_celery_task_failure(sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **extra):
    """Capture background Celery task crashes directly into Admin Failure & Error Log Hub."""
    try:
        from backend.services.admin_alerts_service import record_captured_log, schedule_admin_alert_nonblocking

        task_name = getattr(sender, "name", None) or str(sender or "celery.task")
        err_str = f"{type(exception).__name__}: {exception}" if exception else "Unknown Celery failure"
        tb_str = str(getattr(einfo, "traceback", "") or "")
        record_captured_log(
            level="ERROR",
            logger_name="celery.worker",
            message=f"Task {task_name} ({task_id}) failed: {err_str}",
            traceback_text=tb_str,
            module_func=task_name,
        )
        schedule_admin_alert_nonblocking(
            category="CELERY_FAILURE",
            subsystem="CELERY",
            severity="CRITICAL",
            title=f"Celery Task Failed: {task_name}",
            detail=f"Task ID: {task_id}\nError: {err_str}\n{tb_str[:800]}".strip(),
            suggested_action="Inspect Celery Worker logs & Flower dashboard for worker saturation or upstream errors.",
            trace_id=str(task_id) if task_id else None,
            metadata={"task_name": task_name, "error": err_str},
        )
    except Exception:
        pass


@worker_process_shutdown.connect
def _on_celery_worker_shutdown(**kwargs):
    """Dispose persistent worker event loop, Redis pools, and DB engine on exit."""
    try:
        from backend.core.celery_async import close_worker_loops
        close_worker_loops()
    except Exception:
        pass
