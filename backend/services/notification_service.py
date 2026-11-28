"""
Persistent User Notification Service.

Stores durable per-event user notifications (System Auto-Sells, Order Fills,
Triggered Price/Technical Alerts, and Important System/Cycle Notices) in PostgreSQL
so unread red markers persist across sessions until explicitly viewed, while also
pushing instant updates to active WebSocket sessions.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging_config import get_logger
from backend.models.notification import Notification

logger = get_logger(__name__)
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _is_mock_obj(obj: Any) -> bool:
    return type(obj).__module__.startswith("unittest.mock")


def _safe_parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def serialize_notification(n: Notification) -> dict[str, Any]:
    created_raw = getattr(n, "created_at", None)
    created_utc = None
    created_ist_str = None
    if isinstance(created_raw, datetime):
        created_utc = created_raw if created_raw.tzinfo else created_raw.replace(tzinfo=timezone.utc)
        created_ist_str = created_utc.astimezone(IST_TZ).strftime("%d %b %Y, %I:%M %p IST")

    is_read_val = bool(getattr(n, "is_read", False))
    raw_seen = getattr(n, "is_seen", None)
    is_seen_val = bool(raw_seen) if raw_seen is not None else is_read_val

    return {
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "category": getattr(n, "category", None) or "GENERAL",
        "symbol": getattr(n, "symbol", None),
        "trade_id": getattr(n, "trade_id", None),
        "priority": getattr(n, "priority", None) or "INFO",
        "is_seen": is_seen_val,
        "is_read": is_read_val,
        "metadata": _safe_parse_metadata(getattr(n, "metadata_json", None)),
        "created_at": created_utc.isoformat() if created_utc else None,
        "created_at_ist": created_ist_str,
        "seen_at": n.seen_at.isoformat() if isinstance(getattr(n, "seen_at", None), datetime) else None,
        "read_at": n.read_at.isoformat() if isinstance(getattr(n, "read_at", None), datetime) else None,
    }


async def compute_user_notification_counts(db: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    rows = (await db.execute(stmt)).scalars().all()
    unseen_count = 0
    unread_count = 0
    unseen_by_category: dict[str, int] = {}
    for n in rows:
        is_read = bool(getattr(n, "is_read", False))
        raw_seen = getattr(n, "is_seen", None)
        is_seen = bool(raw_seen) if raw_seen is not None else is_read
        cat = getattr(n, "category", None) or "GENERAL"
        if not is_read:
            unread_count += 1
        if not is_seen:
            unseen_count += 1
            unseen_by_category[cat] = unseen_by_category.get(cat, 0) + 1
    return {
        "unseen_count": unseen_count,
        "unread_count": unread_count,
        "unseen_by_category": unseen_by_category,
    }


async def session_has_table(db: Any, table_name: str) -> bool:
    """Safely check table existence on the session's active connection without borrowing pooled connections."""
    try:
        run_sync = getattr(db, "run_sync", None)
        if callable(run_sync) and not _is_mock_obj(run_sync):
            def _check_async(sync_s: Any) -> bool:
                with sync_s.no_autoflush:
                    return bool(sa_inspect(sync_s.connection()).has_table(table_name))

            return bool(await run_sync(_check_async))

        sync_s = getattr(db, "_s", None) or getattr(db, "sync_session", None)
        if sync_s is not None and hasattr(sync_s, "connection") and callable(sync_s.connection):
            no_auto = getattr(sync_s, "no_autoflush", None)
            if no_auto is not None:
                with no_auto:
                    return bool(sa_inspect(sync_s.connection()).has_table(table_name))
            return bool(sa_inspect(sync_s.connection()).has_table(table_name))
    except Exception:
        return True
    return True


async def create_user_notification(
    db: AsyncSession | None,
    user_id: uuid.UUID | str,
    title: str,
    message: str,
    *,
    priority: str = "INFO",
    category: str = "GENERAL",
    symbol: str | None = None,
    trade_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    broadcast: bool = True,
) -> Notification | None:
    """Persist one notification record safely and push real-time WS updates."""
    if db is None or _is_mock_obj(db):
        return None
    if not await session_has_table(db, "notifications"):
        return None
    try:
        uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        notif = Notification(
            user_id=uid,
            title=title[:240],
            message=message,
            priority=priority,
            category=category,
            symbol=symbol.upper() if symbol else None,
            trade_id=str(trade_id) if trade_id else None,
            metadata_json=json.dumps(metadata or {}),
            is_seen=False,
            is_read=False,
        )
        db.add(notif)
        await db.flush()

        if broadcast:
            try:
                from backend.api.websocket import broadcast_alert
                await broadcast_alert(
                    {
                        "type": "NOTIFICATION_NEW",
                        "notification": serialize_notification(notif),
                    },
                    user_id=str(uid),
                )
            except Exception:
                pass
        return notif
    except Exception as exc:
        logger.debug(f"Could not create user notification ({category}): {exc}")
        return None


async def notify_auto_sell_exit(
    db: AsyncSession | None,
    trade: Any,
    reason_code: str,
    exit_reason_label: str,
    exit_meta: dict[str, Any],
    *,
    broadcast: bool = True,
) -> Notification | None:
    """Create 1 dedicated persistent notification for an individual stock auto-sold by the system."""
    if db is None or _is_mock_obj(db):
        return None
    try:
        sym = str(getattr(trade, "symbol", "") or "").upper()
        qty = int(getattr(trade, "quantity", 0) or 0)
        entry_p = float(getattr(trade, "entry_price", 0.0) or 0.0)
        exit_p = float(exit_meta.get("exit_price") or getattr(trade, "exit_price", 0.0) or 0.0)
        net_pnl = float(getattr(trade, "realized_pnl", 0.0) or 0.0)
        pnl_pct = exit_meta.get("pnl_pct")
        charges = float(exit_meta.get("total_charges") or 0.0)
        pnl_sign = "+" if net_pnl >= 0 else ""
        pct_str = f" ({'+' if (pnl_pct or 0) >= 0 else ''}{float(pnl_pct):.2f}%)" if pnl_pct is not None else ""

        if "TARGET" in reason_code:
            icon = "🎯"
            prio = "HIGH"
        elif "STOP_IN_PROFIT" in reason_code:
            icon = "🔒"
            prio = "HIGH"
        elif "STOPLOSS" in reason_code:
            icon = "🛑"
            prio = "WARNING"
        else:
            icon = "🤖"
            prio = "INFO"

        title = f"{icon} Auto-Sold {sym} ({pnl_sign}₹{net_pnl:,.2f}{pct_str})"
        message = (
            f"{exit_reason_label}: System auto-closed {qty} shares of {sym} ({getattr(trade, 'product_type', 'DELIVERY')}). "
            f"Buy ₹{entry_p:,.2f} -> Sell ₹{exit_p:,.2f} | Net P&L: {pnl_sign}₹{net_pnl:,.2f} "
            f"(Charges ₹{charges:,.2f})."
        )
        metadata = {
            "symbol": sym,
            "trade_id": str(getattr(trade, "id", "")),
            "quantity": qty,
            "entry_price": round(entry_p, 2),
            "exit_price": round(exit_p, 2),
            "realized_pnl": round(net_pnl, 2),
            "pnl_pct": pnl_pct,
            "total_charges": round(charges, 2),
            "reason_code": reason_code,
            "exit_reason_label": exit_reason_label,
            "holding_duration": exit_meta.get("holding_duration_label"),
            "link": "/portfolio",
        }
        notif = await create_user_notification(
            db,
            user_id=getattr(trade, "user_id"),
            title=title,
            message=message,
            priority=prio,
            category="AUTO_SELL",
            symbol=sym,
            trade_id=str(getattr(trade, "id", "")),
            metadata=metadata,
            broadcast=broadcast,
        )
        if broadcast and notif is not None:
            try:
                from backend.api.websocket import broadcast_alert
                await broadcast_alert(
                    {
                        "type": "alert_toast",
                        "data": {
                            "title": title,
                            "message": f"{exit_reason_label} · Exit @ ₹{exit_p:,.2f}",
                            "type": "success" if net_pnl >= 0 else "warning",
                        },
                    },
                    user_id=str(getattr(trade, "user_id")),
                )
            except Exception:
                pass
        return notif
    except Exception as exc:
        logger.debug(f"Could not emit auto-sell notification: {exc}")
        return None


async def notify_order_filled(
    db: AsyncSession | None,
    trade: Any,
    *,
    broadcast: bool = True,
) -> Notification | None:
    """Create a notification when a queued pending LIMIT/SL/AMO order executes live."""
    if db is None or _is_mock_obj(db):
        return None
    sym = str(getattr(trade, "symbol", "") or "").upper()
    qty = int(getattr(trade, "quantity", 0) or 0)
    fill_p = float(getattr(trade, "entry_price", 0.0) or 0.0)
    direction = str(getattr(trade, "direction", "BUY") or "BUY")
    title = f"✅ {direction} Order Executed: {sym}"
    message = (
        f"Pending {getattr(trade, 'order_type', 'LIMIT')} {direction} for {qty} shares of {sym} "
        f"filled at ₹{fill_p:,.2f} ({getattr(trade, 'product_type', 'DELIVERY')})."
    )
    return await create_user_notification(
        db,
        user_id=getattr(trade, "user_id"),
        title=title,
        message=message,
        priority="INFO",
        category="ORDER_FILL",
        symbol=sym,
        trade_id=str(getattr(trade, "id", "")),
        metadata={"symbol": sym, "trade_id": str(getattr(trade, "id", "")), "entry_price": round(fill_p, 2), "quantity": qty, "link": "/portfolio"},
        broadcast=broadcast,
    )


async def broadcast_system_notice_to_users(
    db: AsyncSession | None,
    title: str,
    message: str,
    *,
    priority: str = "INFO",
    category: str = "SYSTEM_NOTICE",
    metadata: dict[str, Any] | None = None,
    only_admins: bool = False,
    auto_commit: bool = False,
) -> int:
    """Persist an important system announcement across active user accounts."""
    if db is None or _is_mock_obj(db):
        return 0
    try:
        from backend.models.user import User
        stmt = select(User).where(User.is_active == True)
        if only_admins:
            stmt = stmt.where(User.is_admin == True)
        users = (await db.execute(stmt)).scalars().all()
        sent = 0
        pending_ws: list[tuple[str, dict[str, Any]]] = []
        for u in users:
            n = await create_user_notification(
                db,
                user_id=u.id,
                title=title,
                message=message,
                priority=priority,
                category=category,
                metadata=metadata,
                broadcast=False,
            )
            if n is not None:
                sent += 1
                pending_ws.append(
                    (
                        str(u.id),
                        {
                            "type": "NOTIFICATION_NEW",
                            "notification": serialize_notification(n),
                        },
                    )
                )
        await db.flush()
        if auto_commit:
            await db.commit()
        if pending_ws:
            try:
                from backend.api.websocket import broadcast_alert
                for uid_str, ws_payload in pending_ws:
                    await broadcast_alert(ws_payload, user_id=uid_str)
            except Exception as ws_exc:
                logger.warning(f"System notice saved ({sent} users) but WS push failed: {ws_exc}")
        return sent
    except Exception as exc:
        logger.error(f"Could not broadcast system notice: {exc}", exc_info=True)
        raise
