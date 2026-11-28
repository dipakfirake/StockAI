"""Scheduled database snapshot & Disaster Recovery verification Celery tasks."""

from __future__ import annotations

from backend.celery_app import celery_app
from backend.core.celery_async import run_in_worker_loop
from backend.core.logging_config import get_logger
from backend.core.backup_dr import (
    create_database_snapshot,
    run_restore_drill,
    record_verified_drill,
)

logger = get_logger(__name__)


async def _run_nightly_backup_and_dr_async():
    snapshot = await create_database_snapshot(include_candles=False)
    drill = await run_restore_drill(snapshot["path"])
    record_verified_drill(drill)
    logger.info(
        "[DR] Nightly snapshot %s created (%s rows, %s bytes) and restore drill PASSED.",
        snapshot["filename"],
        snapshot["total_rows"],
        snapshot["size_bytes"],
    )
    return {"snapshot": snapshot, "drill": drill}


@celery_app.task(name="backend.tasks.maintenance_tasks.run_nightly_backup_and_dr_check")
def run_nightly_backup_and_dr_check():
    """Create compressed DB snapshot and run an isolated restore verification drill."""
    try:
        return run_in_worker_loop(_run_nightly_backup_and_dr_async())
    except Exception as exc:
        logger.error("[DR] Nightly backup/restore drill failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}
