"""
Admin-Only Operational, Security Threat & Application Error-Log Alert Hub Service.

Unifies:
1. Structured Cybersecurity Audit Events (`backend/logs/security_audit.log` & live hook)
2. Runtime Python `ERROR` / `CRITICAL` / `WARNING` Log Capture ("wrong logs" radar)
3. Sentinel Watchdog Subsystem Incidents (Database, Redis, Celery, Fyers Feed, APIs)
4. Celery Worker & Scheduler Crash Captures

All log details are redacted before storage and strictly scoped behind `require_admin`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.admin_alert_event import AdminAlertEvent

IST_TZ = timezone(timedelta(hours=5, minutes=30))

_SECRET_PATTERNS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.=]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"(password|secret|access_token|api_key|token)\s*[:=]\s*['\"]?[^\s,'\"\}]+", re.IGNORECASE), r"\1=[REDACTED]"),
    (re.compile(r"postgresql(?:\+asyncpg)?://[^:\s]+:[^@\s]+@", re.IGNORECASE), "postgresql://[USER]:[REDACTED]@"),
    (re.compile(r"redis://:[^@\s]+@", re.IGNORECASE), "redis://:[REDACTED]@"),
]

# Thread-safe bounded ring buffers for fast Admin Ops UI inspection without DB overhead on every warning
_LOCK = threading.Lock()
_CAPTURED_LOGS: deque[dict[str, Any]] = deque(maxlen=250)
_PENDING_DB_ALERTS: deque[dict[str, Any]] = deque(maxlen=200)
_FLUSH_SCHEDULED = False


def redact_sensitive_text(text: str | None, max_len: int = 1200) -> str:
    if not text:
        return ""
    cleaned = str(text)
    for pattern, repl in _SECRET_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned


def _format_ist(dt: datetime | None) -> str | None:
    if not isinstance(dt, datetime):
        return None
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST_TZ).strftime("%d %b %Y, %I:%M:%S %p IST")


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def serialize_admin_alert(ev: AdminAlertEvent) -> dict[str, Any]:
    first_dt = ev.first_seen_at if (ev.first_seen_at and ev.first_seen_at.tzinfo) else (ev.first_seen_at.replace(tzinfo=timezone.utc) if ev.first_seen_at else None)
    last_dt = ev.last_seen_at if (ev.last_seen_at and ev.last_seen_at.tzinfo) else (ev.last_seen_at.replace(tzinfo=timezone.utc) if ev.last_seen_at else None)
    return {
        "id": str(ev.id),
        "fingerprint": ev.fingerprint,
        "category": ev.category,
        "subsystem": ev.subsystem,
        "severity": ev.severity,
        "title": ev.title,
        "detail": ev.detail,
        "suggested_action": ev.suggested_action,
        "trace_id": ev.trace_id,
        "ip_address": ev.ip_address,
        "user_id_ref": ev.user_id_ref,
        "occurrence_count": int(ev.occurrence_count or 1),
        "is_seen": bool(ev.is_seen),
        "is_read": bool(ev.is_read),
        "status": ev.status or "OPEN",
        "metadata": _safe_json_loads(ev.metadata_json),
        "first_seen_at": first_dt.isoformat() if first_dt else None,
        "last_seen_at": last_dt.isoformat() if last_dt else None,
        "last_seen_ist": _format_ist(last_dt),
        "acknowledged_by": ev.acknowledged_by,
        "acknowledged_at": ev.acknowledged_at.isoformat() if ev.acknowledged_at else None,
        "resolved_by": ev.resolved_by,
        "resolved_at": ev.resolved_at.isoformat() if ev.resolved_at else None,
    }


def record_captured_log(
    *,
    level: str,
    logger_name: str,
    message: str,
    traceback_text: str | None = None,
    module_func: str | None = None,
) -> dict[str, Any]:
    """Store sanitized WARNING/ERROR/CRITICAL runtime log in the bounded Admin ring buffer."""
    now = datetime.now(timezone.utc)
    clean_msg = redact_sensitive_text(message, max_len=600)
    clean_tb = redact_sensitive_text(traceback_text, max_len=1000) if traceback_text else None
    sig = hashlib.sha256(f"{level}:{logger_name}:{clean_msg[:160]}".encode("utf-8")).hexdigest()[:16]

    entry = {
        "id": sig,
        "level": level.upper(),
        "logger": logger_name,
        "location": module_func,
        "message": clean_msg,
        "traceback": clean_tb,
        "timestamp": now.isoformat(),
        "timestamp_ist": _format_ist(now),
        "count": 1,
    }
    with _LOCK:
        # Collapse back-to-back identical error logs cleanly
        for existing in list(_CAPTURED_LOGS)[:15]:
            if existing["id"] == sig:
                existing["count"] += 1
                existing["timestamp"] = entry["timestamp"]
                existing["timestamp_ist"] = entry["timestamp_ist"]
                if clean_tb:
                    existing["traceback"] = clean_tb
                return dict(existing)
        _CAPTURED_LOGS.appendleft(entry)
    return entry


def get_recent_captured_logs(level: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    with _LOCK:
        items = list(_CAPTURED_LOGS)
    if level and level.upper() != "ALL":
        target = level.upper()
        items = [i for i in items if i.get("level") == target]
    return items[:limit]


def read_security_audit_tail(limit: int = 80) -> list[dict[str, Any]]:
    """Read structured entries from the canonical security audit log path safely."""
    from backend.core.audit_logger import AUDIT_LOG_PATH

    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    out: list[dict[str, Any]] = []
    try:
        with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-max(10, limit):]
        for raw in reversed(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                ts = parsed.get("timestamp")
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else None
                parsed["timestamp_ist"] = _format_ist(dt)
                out.append(parsed)
            except Exception:
                out.append({"event_type": "RAW_AUDIT_LINE", "severity": "INFO", "details": {"raw": redact_sensitive_text(raw, 400)}})
    except Exception:
        return []
    return out


async def record_admin_alert_async(
    db: AsyncSession,
    *,
    category: str,
    subsystem: str,
    severity: str,
    title: str,
    detail: str,
    suggested_action: str | None = None,
    trace_id: str | None = None,
    ip_address: str | None = None,
    user_id_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    broadcast: bool = True,
) -> AdminAlertEvent | None:
    """Deduplicated upsert of an admin-only alert event and WebSocket notification push."""
    clean_title = redact_sensitive_text(title, 250)
    clean_detail = redact_sensitive_text(detail, 2000)
    fp = hashlib.sha256(f"{category}:{subsystem}:{clean_title}".encode("utf-8")).hexdigest()[:64]
    now = datetime.now(timezone.utc)

    res = await db.execute(select(AdminAlertEvent).where(AdminAlertEvent.fingerprint == fp))
    ev = res.scalars().first()
    if ev:
        ev.occurrence_count = int(ev.occurrence_count or 1) + 1
        ev.last_seen_at = now
        ev.detail = clean_detail
        ev.severity = severity
        if trace_id:
            ev.trace_id = trace_id
        if ip_address and ip_address != "unknown":
            ev.ip_address = ip_address
        if metadata:
            ev.metadata_json = json.dumps(metadata)
        ev.is_seen = False
        ev.is_read = False
        if ev.status == "RESOLVED":
            ev.status = "OPEN"
    else:
        ev = AdminAlertEvent(
            id=uuid.uuid4(),
            fingerprint=fp,
            category=category,
            subsystem=subsystem,
            severity=severity,
            title=clean_title,
            detail=clean_detail,
            suggested_action=redact_sensitive_text(suggested_action, 490) if suggested_action else None,
            trace_id=trace_id,
            ip_address=ip_address,
            user_id_ref=user_id_ref,
            occurrence_count=1,
            is_seen=False,
            is_read=False,
            status="OPEN",
            metadata_json=json.dumps(metadata or {}),
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(ev)

    await db.flush()
    serialized = serialize_admin_alert(ev)

    if broadcast:
        try:
            from backend.api.websocket import broadcast_admin_alert
            await broadcast_admin_alert({"type": "ADMIN_ALERT_NEW", "alert": serialized})
        except Exception:
            pass
    return ev


async def _flush_pending_admin_alerts() -> None:
    global _FLUSH_SCHEDULED
    batch: list[dict[str, Any]] = []
    with _LOCK:
        while _PENDING_DB_ALERTS:
            batch.append(_PENDING_DB_ALERTS.popleft())
        _FLUSH_SCHEDULED = False

    if not batch:
        return
    try:
        from backend.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            for item in batch:
                await record_admin_alert_async(session, **item)
            await session.commit()
    except Exception:
        # Never recursively log inside alert persistence fallback
        pass


def schedule_admin_alert_nonblocking(
    *,
    category: str,
    subsystem: str,
    severity: str,
    title: str,
    detail: str,
    suggested_action: str | None = None,
    trace_id: str | None = None,
    ip_address: str | None = None,
    user_id_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Queue an admin alert safely from synchronous contexts (logging handlers, audit logger, Celery signals)
    and drain asynchronously onto the running asyncio event loop without deadlocks or recursion.
    """
    global _FLUSH_SCHEDULED
    payload = {
        "category": category,
        "subsystem": subsystem,
        "severity": severity,
        "title": title,
        "detail": detail,
        "suggested_action": suggested_action,
        "trace_id": trace_id,
        "ip_address": ip_address,
        "user_id_ref": user_id_ref,
        "metadata": metadata,
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    with _LOCK:
        _PENDING_DB_ALERTS.append(payload)
        if loop and loop.is_running() and not _FLUSH_SCHEDULED:
            _FLUSH_SCHEDULED = True
            try:
                loop.create_task(_flush_pending_admin_alerts())
            except Exception:
                _FLUSH_SCHEDULED = False


async def drain_pending_admin_alerts(db: AsyncSession) -> int:
    """Drain any buffered sync-thread alerts (e.g. startup/Celery thread) on admin hub poll."""
    global _FLUSH_SCHEDULED
    batch: list[dict[str, Any]] = []
    with _LOCK:
        while _PENDING_DB_ALERTS:
            batch.append(_PENDING_DB_ALERTS.popleft())
        _FLUSH_SCHEDULED = False
    if not batch:
        return 0
    for item in batch:
        await record_admin_alert_async(db, **item)
    return len(batch)


async def fetch_admin_alerts_hub_summary(
    db: AsyncSession,
    *,
    category: str | None = None,
    severity: str | None = None,
    unseen_only: bool = False,
    status_filter: str | None = None,
    search: str | None = None,
    limit: int = 80,
) -> dict[str, Any]:
    await drain_pending_admin_alerts(db)

    all_rows = (
        await db.execute(select(AdminAlertEvent).order_by(desc(AdminAlertEvent.last_seen_at)).limit(250))
    ).scalars().all()

    unseen_count = 0
    unread_count = 0
    open_count = 0
    critical_count = 0
    counts_by_category: dict[str, int] = {}

    for r in all_rows:
        if not r.is_seen:
            unseen_count += 1
        if not r.is_read:
            unread_count += 1
        if (r.status or "OPEN") != "RESOLVED":
            open_count += 1
            if r.severity == "CRITICAL":
                critical_count += 1
        cat_key = r.category or "SYSTEM_FAILURE"
        counts_by_category[cat_key] = counts_by_category.get(cat_key, 0) + (0 if r.is_seen else 1)

    filtered = []
    q_search = search.strip().lower() if search else ""
    for r in all_rows:
        if category and category.upper() != "ALL" and (r.category or "").upper() != category.upper():
            continue
        if severity and severity.upper() != "ALL" and (r.severity or "").upper() != severity.upper():
            continue
        if unseen_only and r.is_seen:
            continue
        if status_filter and status_filter.upper() != "ALL" and (r.status or "OPEN").upper() != status_filter.upper():
            continue
        item = serialize_admin_alert(r)
        if q_search:
            haystack = " ".join([
                str(item.get("title") or ""),
                str(item.get("detail") or ""),
                str(item.get("subsystem") or ""),
                str(item.get("ip_address") or ""),
                str(item.get("trace_id") or ""),
            ]).lower()
            if q_search not in haystack:
                continue
        filtered.append(item)
        if len(filtered) >= limit:
            break

    return {
        "unseen_count": unseen_count,
        "unread_count": unread_count,
        "open_count": open_count,
        "critical_count": critical_count,
        "counts_by_category": counts_by_category,
        "alerts": filtered,
        "recent_logs": get_recent_captured_logs(limit=60),
        "security_audit_tail": read_security_audit_tail(limit=50),
    }
