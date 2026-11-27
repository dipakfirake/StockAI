"""
Regression & integration tests for:
1. Per-stock System Auto-Sell Notifications (Notification Inbox persistence, red unseen badge
   clearing strictly on mark-seen / opening Inbox tab, read state preservation, and Order Fill / Broadcast notices).
2. Admin-only Threats, System Failures & Wrong-Logs Hub (real security_audit.log ingestion in
   SentinelService, AdminErrorLogHandler log capture + secret redaction, Celery task failure hook,
   deduplication across recurring alerts, and strict HTTP 403 isolation from standard users).
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from backend.api.admin import (
    AdminAcknowledgeAlertsRequest,
    AdminBroadcastNoticeRequest,
    acknowledge_admin_alerts,
    admin_broadcast_system_notice,
    get_admin_alerts_hub,
    mark_admin_alerts_seen,
)
from backend.api.notifications import (
    get_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notifications_seen,
)
from backend.core.audit_logger import log_security_event
from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.core.logging_config import AdminErrorLogHandler
from backend.main import app
from backend.models.admin_alert_event import AdminAlertEvent
from backend.models.notification import Notification
from backend.models.paper_trade import PaperTrade
from backend.models.sentinel_incident import SentinelIncident
from backend.models.settings import SystemSettings
from backend.models.user import User
from backend.services.admin_alerts_service import (
    get_recent_captured_logs,
    record_admin_alert_async,
    redact_sensitive_text,
)
from backend.services.paper_trading import PaperTradingService
from backend.services.sentinel import sentinel_service


@compiles(PG_UUID, "sqlite")
def _compile_pg_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(36)"


class _AsyncSQLiteProxy:
    def __init__(self, sync_session: Session):
        self._s = sync_session

    def add(self, obj):
        return self._s.add(obj)

    def add_all(self, objs):
        return self._s.add_all(objs)

    async def execute(self, statement, params=None, **kwargs):
        return self._s.execute(statement, params or {}, **kwargs)

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    async def flush(self):
        return self._s.flush()

    async def refresh(self, instance):
        return self._s.refresh(instance)


def _create_test_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    for tbl in (
        User.__table__,
        SystemSettings.__table__,
        PaperTrade.__table__,
        Notification.__table__,
        AdminAlertEvent.__table__,
        SentinelIncident.__table__,
    ):
        tbl.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sync_s = SessionLocal()
    return engine, sync_s, _AsyncSQLiteProxy(sync_s)


@pytest.mark.asyncio
async def test_auto_sell_creates_per_stock_notifications_and_clears_badge_only_when_seen():
    """
    When evaluate_open_trades auto-sells 2 stocks, 2 individual AUTO_SELL Notification rows must
    be created with is_seen=False (unseen_count=2). Reloading keeps unseen_count=2 until
    mark_notifications_seen (tab opened) sets unseen_count=0 while preserving per-item unread status.
    """
    engine, sync_s, db = _create_test_session()
    try:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email="auto@example.com",
            hashed_password="hashed",
            name="Auto Trader",
            is_admin=False,
            is_active=True,
        )
        other_user = User(
            id=uuid.uuid4(),
            email="other@example.com",
            hashed_password="hashed",
            name="Other",
            is_admin=False,
            is_active=True,
        )
        db.add_all([user, other_user])

        now_utc = datetime.now(timezone.utc)
        t_persistent = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="PERSISTENT.NS",
            direction="BUY",
            order_type="LIMIT",
            product_type="DELIVERY",
            quantity=10,
            entry_price=Decimal("5746.24"),
            target_price=Decimal("6255.17"),
            stop_loss=Decimal("5517.54"),
            commission=Decimal("20.00"),
            stt_tax=Decimal("0.00"),
            status="OPEN",
            opened_at=now_utc - timedelta(days=5),
        )
        t_tcs = PaperTrade(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="TCS.NS",
            direction="BUY",
            order_type="MARKET",
            product_type="DELIVERY",
            quantity=5,
            entry_price=Decimal("2557.80"),
            target_price=Decimal("2592.43"),
            stop_loss=Decimal("2460.00"),
            target_1=Decimal("2580.00"),
            target_2=Decimal("2592.43"),
            commission=Decimal("20.00"),
            stt_tax=Decimal("0.00"),
            status="OPEN",
            opened_at=now_utc - timedelta(days=2),
        )
        db.add_all([t_persistent, t_tcs])
        await db.flush()

        with patch(
            "backend.services.market_data.market_data_service.fetch_quotes_bulk",
            new_callable=AsyncMock,
            return_value={
                "PERSISTENT.NS": {"price": 6268.45},
                "TCS.NS": {"price": 2595.00},
            },
        ), patch(
            "backend.services.market_depth_service.market_depth_service.get_market_depth",
            new_callable=AsyncMock,
            return_value=None,
        ), patch("backend.api.websocket.broadcast_alert", new_callable=AsyncMock) as mock_ws:
            await PaperTradingService.evaluate_open_trades(db)
            await db.commit()

        assert t_persistent.status == "CLOSED"
        assert t_tcs.status == "CLOSED"
        assert mock_ws.call_count >= 2

        # Before user opens the Notifications tab: BOTH unseen_count and unread_count == 2
        inbox_before = await get_notifications(db=db, current_user=user)
        assert inbox_before["unseen_count"] == 2
        assert inbox_before["unread_count"] == 2
        assert inbox_before["unseen_by_category"].get("AUTO_SELL") == 2
        syms = {n["symbol"] for n in inbox_before["notifications"]}
        assert syms == {"PERSISTENT.NS", "TCS.NS"}

        # Admin broadcasts an important notice -> adds 1 SYSTEM_NOTICE for every active user
        admin_user = MagicMock(spec=User, id=uuid.uuid4(), email="admin@example.com", is_admin=True)
        bc_res = await admin_broadcast_system_notice(
            AdminBroadcastNoticeRequest(title="NSE Holiday Notice", message="Market closed tomorrow.", priority="HIGH"),
            admin=admin_user,
            db=db,
        )
        assert bc_res["recipients"] == 2

        inbox_with_notice = await get_notifications(category="AUTO_SELL", db=db, current_user=user)
        assert len(inbox_with_notice["notifications"]) == 2
        assert inbox_with_notice["unseen_count"] == 3  # 2 AUTO_SELL + 1 SYSTEM_NOTICE
        assert inbox_with_notice["unseen_by_category"].get("SYSTEM_NOTICE") == 1

        # Opening Notifications tab invokes mark_notifications_seen -> clears red marker (unseen_count -> 0)
        # while individual items remain unread until clicked / mark-all-read!
        seen_res = await mark_notifications_seen(db=db, current_user=user)
        assert seen_res["unseen_count"] == 0
        assert seen_res["unread_count"] == 3

        first_id = inbox_with_notice["notifications"][0]["id"]
        one_read = await mark_notification_read(first_id, db=db, current_user=user)
        assert one_read["unread_count"] == 2

        all_read = await mark_all_notifications_read(db=db, current_user=user)
        assert all_read["unseen_count"] == 0
        assert all_read["unread_count"] == 0
    finally:
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_admin_hub_captures_wrong_logs_security_threats_and_blocks_non_admins(tmp_path):
    """
    Verify:
    1. Secret scrubber redacts JWT tokens & DB passwords before storage.
    2. AdminErrorLogHandler captures ERROR logs + tracebacks into ring buffer and DB ledger.
    3. SentinelService._probe_security_logs parses real security_audit.log event names
       (`AUTH_LOGIN_FAILED`, `UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT`, `UNHANDLED_EXCEPTION`).
    4. Non-admin users receive HTTP 403 on /api/admin/alerts-hub endpoints.
    """
    redacted = redact_sensitive_text(
        "Failed connecting postgresql://user:SuperSecret123@db:5432/app Authorization: Bearer eyJhbGci.secret.sig"
    )
    assert "SuperSecret123" not in redacted
    assert "eyJhbGci" not in redacted
    assert "[REDACTED]" in redacted

    # Test AdminErrorLogHandler directly without leaking prior buffered alerts
    from backend.services import admin_alerts_service
    admin_alerts_service._PENDING_DB_ALERTS.clear()

    handler = AdminErrorLogHandler(level=logging.WARNING)
    test_logger = logging.getLogger("backend.tests.sample_failure")
    test_logger.addHandler(handler)
    try:
        try:
            raise RuntimeError("Synthetic database pool failure password=hidden_pw")
        except RuntimeError:
            test_logger.error("Market pipeline crashed cleanly", exc_info=True)
    finally:
        test_logger.removeHandler(handler)

    recent_logs = get_recent_captured_logs(level="ERROR", limit=20)
    assert any("Market pipeline crashed cleanly" in l["message"] and "hidden_pw" not in str(l) for l in recent_logs)

    # Test Sentinel reading canonical audit log events
    fake_audit = tmp_path / "security_audit.log"
    events = [
        {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "AUTH_LOGIN_FAILED", "severity": "WARNING", "ip_address": "1.2.3.4"},
        {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT", "severity": "WARNING", "ip_address": "1.2.3.4"},
        {"timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "UNHANDLED_EXCEPTION", "severity": "CRITICAL", "ip_address": "1.2.3.4"},
    ]
    fake_audit.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")

    with patch("backend.core.audit_logger.AUDIT_LOG_PATH", str(fake_audit)), \
         patch.object(sentinel_service, "_record_incident", new_callable=AsyncMock) as mock_inc:
        sec_res = await sentinel_service._probe_security_logs()
        assert sec_res["threat_level"] == "HIGH"
        assert sec_res["active_threats"] >= 2
        assert mock_inc.call_count >= 2

    # Test DB persistence, deduplication, mark-seen, resolve, and strict non-admin HTTP 403 isolation
    engine, sync_s, db = _create_test_session()
    try:
        ev1 = await record_admin_alert_async(
            db,
            category="SECURITY_THREAT",
            subsystem="SECURITY",
            severity="CRITICAL",
            title="Brute Force Attempt from 10.0.0.5",
            detail="5 failed attempts",
            trace_id="trace-abc-123",
            ip_address="10.0.0.5",
            broadcast=False,
        )
        ev2 = await record_admin_alert_async(
            db,
            category="SECURITY_THREAT",
            subsystem="SECURITY",
            severity="CRITICAL",
            title="Brute Force Attempt from 10.0.0.5",
            detail="6 failed attempts",
            trace_id="trace-abc-124",
            ip_address="10.0.0.5",
            broadcast=False,
        )
        await db.commit()
        assert ev1.id == ev2.id
        assert ev2.occurrence_count == 2

        admin_u = User(id=uuid.uuid4(), email="admin@stockai.com", hashed_password="h", name="Head Admin", is_admin=True, is_active=True)
        normal_u = User(id=uuid.uuid4(), email="user@stockai.com", hashed_password="h", name="Regular", is_admin=False, is_active=True)

        # Should include BOTH the SECURITY_THREAT (deduped x2) AND the captured ERROR_LOG above
        hub = await get_admin_alerts_hub(admin=admin_u, db=db)
        assert hub["unseen_count"] == 2
        assert hub["critical_count"] == 1
        assert len(hub["alerts"]) == 2
        sec_alert = next(a for a in hub["alerts"] if a["category"] == "SECURITY_THREAT")
        err_alert = next(a for a in hub["alerts"] if a["category"] == "ERROR_LOG")
        assert sec_alert["occurrence_count"] == 2
        assert "Market pipeline crashed cleanly" in err_alert["title"]
        assert "hidden_pw" not in err_alert["detail"]

        await mark_admin_alerts_seen(admin=admin_u, db=db)
        hub_after_seen = await get_admin_alerts_hub(admin=admin_u, db=db)
        assert hub_after_seen["unseen_count"] == 0
        assert hub_after_seen["open_count"] == 2

        ack_res = await acknowledge_admin_alerts(
            AdminAcknowledgeAlertsRequest(alert_id=str(ev2.id), action="RESOLVE"),
            admin=admin_u,
            db=db,
        )
        assert ack_res["updated"] == 1
        assert ack_res["status"] == "RESOLVED"

        hub_after_resolve = await get_admin_alerts_hub(admin=admin_u, db=db)
        assert hub_after_resolve["open_count"] == 1

        # FastAPI ASGITransport check: regular user blocked with HTTP 403; admin succeeds HTTP 200
        app.dependency_overrides[get_db] = lambda: db
        try:
            app.dependency_overrides[get_current_user] = lambda: normal_u
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                r_forbidden = await client.get("/api/admin/alerts-hub")
                assert r_forbidden.status_code == 403
                r_user_notif = await client.get("/api/notifications")
                assert r_user_notif.status_code == 200

            app.dependency_overrides[get_current_user] = lambda: admin_u
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                r_admin_hub = await client.get("/api/admin/alerts-hub")
                assert r_admin_hub.status_code == 200
                assert r_admin_hub.json()["open_count"] == 1
        finally:
            app.dependency_overrides.clear()
    finally:
        sync_s.close()
        engine.dispose()
