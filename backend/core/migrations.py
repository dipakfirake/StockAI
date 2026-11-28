"""Zero-drift schema migration verification and baseline bootstrapping utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.core.logging_config import get_logger

logger = get_logger(__name__)

BASELINE_REVISION = "20261128_0001"
ALEMBIC_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def get_head_revision() -> str:
    """Discover the latest migration revision ID in `backend/alembic/versions`."""
    if not ALEMBIC_VERSIONS_DIR.exists():
        return BASELINE_REVISION
    files = sorted(
        f.name for f in ALEMBIC_VERSIONS_DIR.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("__")
    )
    if not files:
        return BASELINE_REVISION
    latest = files[-1]
    parts = latest.split("_", 2)
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{parts[0]}_{parts[1]}"
    return BASELINE_REVISION


async def ensure_baseline_stamped_or_upgraded(conn: Any) -> None:
    """
    Ensure existing production/dev databases record the baseline Alembic version cleanly
    without failing on already-created tables (`create_all` bootstrap compatibility).
    """
    head_rev = get_head_revision()
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY"
            ")"
        )
    )
    existing = (await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()
    if not existing:
        await conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": head_rev},
        )
        logger.info("[Migrations] Stamped database schema baseline at revision %s", head_rev)


def ensure_baseline_stamped_or_upgraded_sync(conn: Any) -> None:
    """Synchronous variant of baseline stamping for stdlib SQLite / sync connections."""
    head_rev = get_head_revision()
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY"
            ")"
        )
    )
    existing = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    if not existing:
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": head_rev},
        )
        logger.info("[Migrations] Stamped database schema baseline at revision %s", head_rev)


async def get_schema_migration_status(target_engine: Optional[AsyncEngine | Engine] = None) -> Dict[str, Any]:
    """Inspect live `alembic_version` state vs code repository head revision."""
    if target_engine is None:
        from backend.core.database import engine as default_engine
        target_engine = default_engine

    head_rev = get_head_revision()
    versions_count = 0
    if ALEMBIC_VERSIONS_DIR.exists():
        versions_count = len([
            f for f in ALEMBIC_VERSIONS_DIR.iterdir()
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("__")
        ])

    current_rev: Optional[str] = None
    status = "unknown"
    try:
        if isinstance(target_engine, Engine):
            with target_engine.connect() as conn:
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
        else:
            async with target_engine.connect() as conn:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).scalar_one_or_none()
        current_rev = str(row) if row else None
        if current_rev == head_rev:
            status = "in_sync"
        elif current_rev is None:
            status = "unstamped"
        else:
            status = "upgrade_pending"
    except Exception as exc:
        status = f"unavailable ({type(exc).__name__})"

    return {
        "current_revision": current_rev,
        "head_revision": head_rev,
        "versions_count": versions_count,
        "in_sync": current_rev == head_rev,
        "status": status,
    }
