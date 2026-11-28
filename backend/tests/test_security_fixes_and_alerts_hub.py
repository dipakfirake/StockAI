"""
Regression tests for production threat/log fixes, broadcast commit ordering,
Admin Hub log/audit filtering, URL/RBAC hardening, and presence anti-spoofing.
"""

from __future__ import annotations

import errno
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from backend.api.admin import (
    AdminBroadcastNoticeRequest,
    admin_broadcast_system_notice,
    require_admin,
)
from backend.core.auth import get_current_user, get_current_user_optional
from backend.core.database import get_db
from backend.core.logging_config import AdminErrorLogHandler
from backend.main import app
from backend.models.admin_alert_event import AdminAlertEvent
from backend.models.notification import Notification
from backend.models.user import User
from backend.services.admin_alerts_service import (
    _CAPTURED_LOGS,
    fetch_admin_alerts_hub_summary,
    record_captured_log,
)
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


def _create_sqlite_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    for tbl in (User.__table__, Notification.__table__, AdminAlertEvent.__table__):
        tbl.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sync_s = SessionLocal()
    return engine, sync_s, _AsyncSQLiteProxy(sync_s)


def test_auto_trader_extract_macd_values_handles_dict_and_scalar():
    """Verify _extract_macd_values safely handles nested dicts (SBIN.NS crash) and scalars."""
    from backend.tasks.auto_trader import _extract_macd_values

    m_val, s_val = _extract_macd_values(
        {"macd": {"macd": 14.25, "signal": 11.10, "histogram": 3.15}}
    )
    assert isinstance(m_val, float) and isinstance(s_val, float)
    assert m_val == 14.25
    assert s_val == 11.10
    assert (m_val > s_val) is True

    m_flat, s_flat = _extract_macd_values({"macd": -2.5, "macd_signal": 0.5})
    assert m_flat == -2.5
    assert s_flat == 0.5

    assert _extract_macd_values({"macd": None, "macd_signal": None}) == (0.0, 0.0)
    assert _extract_macd_values(None) == (0.0, 0.0)


def test_scanner_universe_replaces_macrotech_with_lodha():
    """Verify MACROTECH.NS rename bug is resolved to LODHA.NS."""
    from backend.api.scanner import SECTOR_MAP

    realty = SECTOR_MAP["Nifty Realty"]
    assert "LODHA.NS" in realty
    assert "MACROTECH.NS" not in realty


def test_market_data_events_skips_index_calendar():
    """Verify ^-prefixed benchmark indices never call ticker.calendar (prevents Yahoo 429 spam)."""
    from backend.services.market_data import MarketDataService

    class ExplodingTicker:
        @property
        def calendar(self):
            raise AssertionError("ticker.calendar must not be called for ^NSEI index")

        @property
        def dividends(self):
            return []

    with patch("yfinance.Ticker", return_value=ExplodingTicker()):
        events = MarketDataService._fetch_yf_events_sync("^NSEI")
        assert events["earnings_date"] is None


def test_logging_filter_suppresses_noisy_yfinance_probes():
    """Verify noisy transient yfinance network errors do not clutter Admin Error Logs."""
    _CAPTURED_LOGS.clear()
    handler = AdminErrorLogHandler(level=logging.WARNING)
    yf_logger = logging.getLogger("yfinance")
    app_logger = logging.getLogger("backend.tests.real_app_err")
    yf_logger.addHandler(handler)
    app_logger.addHandler(handler)
    old_yf_level = yf_logger.level
    yf_logger.setLevel(logging.ERROR)
    try:
        yf_logger.error("429 Client Error: Too Many Requests for url: https://query2.finance.yahoo.com/...")
        yf_logger.error("$^NSEI: possibly delisted; no timezone found")
        yf_logger.error("Failed to get ticker '^NSEI' reason: Expecting value: line 1 column 1 (char 0)")
        app_logger.error("Genuine database timeout in worker")

        messages = [entry["message"] for entry in list(_CAPTURED_LOGS)]
        assert all("possibly delisted" not in m for m in messages)
        assert all("429 Client Error" not in m for m in messages)
        assert any("Genuine database timeout" in m for m in messages)
    finally:
        yf_logger.removeHandler(handler)
        app_logger.removeHandler(handler)
        yf_logger.setLevel(old_yf_level)
        _CAPTURED_LOGS.clear()


@pytest.mark.asyncio
async def test_system_validator_rbac_test_does_not_emit_false_alarm():
    """Hourly SEC-004 RBAC check verifies 403 silently without false-alarm UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT logs."""
    from backend.services.system_validator import system_validator

    with patch("backend.api.admin.log_security_event") as mock_audit:
        res = await system_validator.run_single_test("SEC-004")
        assert res["status"] == "PASSED"
        mock_audit.assert_not_called()

        # Real external non-admin call MUST still log UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT
        regular = MagicMock(spec=User, id=uuid.uuid4(), email="intruder@test.com", is_admin=False)
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(regular)
        assert exc_info.value.status_code == 403
        mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_sentinel_probe_ignores_stale_security_logs_and_honors_watermark(tmp_path):
    """Old (>30m) cumulative audit lines or resolved events before watermark must not keep re-firing threats."""
    fake_audit = tmp_path / "security_audit.log"
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()

    fake_audit.write_text(
        json.dumps(
            {
                "timestamp": stale_ts,
                "event_type": "UNAUTHORIZED_ADMIN_ACCESS_ATTEMPT",
                "severity": "WARNING",
                "ip_address": "1.1.1.1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    prev_watermark = getattr(sentinel_service, "_security_log_watermark", None)
    sentinel_service._security_log_watermark = None
    try:
        with patch("backend.core.audit_logger.AUDIT_LOG_PATH", str(fake_audit)), \
             patch.object(sentinel_service, "_record_incident", new_callable=AsyncMock) as mock_inc:
            res_stale = await sentinel_service._probe_security_logs()
            assert res_stale["active_threats"] == 0
            mock_inc.assert_not_called()

            # Add fresh entry -> triggers incident
            fake_audit.write_text(
                json.dumps(
                    {
                        "timestamp": fresh_ts,
                        "event_type": "UNHANDLED_EXCEPTION",
                        "severity": "CRITICAL",
                        "ip_address": "2.2.2.2",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            res_fresh = await sentinel_service._probe_security_logs()
            assert res_fresh["active_threats"] >= 1
            assert mock_inc.call_count >= 1

            # Setting resolve watermark suppresses already-resolved fresh entries too
            mock_inc.reset_mock()
            sentinel_service._security_log_watermark = datetime.now(timezone.utc) + timedelta(seconds=1)
            res_resolved = await sentinel_service._probe_security_logs()
            assert res_resolved["active_threats"] == 0
            mock_inc.assert_not_called()
    finally:
        sentinel_service._security_log_watermark = prev_watermark


@pytest.mark.asyncio
async def test_broadcast_commits_before_ws_and_hub_filters_logs_and_audit(tmp_path):
    """Verify broadcast commits rows before WS dispatch and Admin Hub filters recent_logs + audit tail."""
    engine, sync_s, db = _create_sqlite_session()
    call_order: list[str] = []
    orig_commit = db.commit

    async def tracked_commit():
        call_order.append("commit")
        return await orig_commit()

    db.commit = tracked_commit

    async def tracked_ws(payload, user_id=None):
        call_order.append("ws")

    try:
        admin_u = User(
            id=uuid.uuid4(),
            email="admin@stockai.com",
            hashed_password="h",
            name="Admin",
            is_admin=True,
            is_active=True,
        )
        trader_u = User(
            id=uuid.uuid4(),
            email="trader@stockai.com",
            hashed_password="h",
            name="Trader",
            is_admin=False,
            is_active=True,
        )
        db.add_all([admin_u, trader_u])
        await db.commit()
        call_order.clear()

        with patch("backend.api.websocket.broadcast_alert", side_effect=tracked_ws):
            res = await admin_broadcast_system_notice(
                AdminBroadcastNoticeRequest(
                    title="Exchange Maintenance",
                    message="NSE mock drill on Saturday.",
                    priority="HIGH",
                ),
                admin=admin_u,
                db=db,
            )
        assert res["success"] is True
        assert res["recipients"] == 2
        assert call_order[0] == "commit"
        assert "ws" in call_order[1:]

        # Verify clean link without ?tab= query param
        rows = sync_s.query(Notification).all()
        assert len(rows) == 2
        assert "Exchange Maintenance" == rows[0].title
        assert "?tab=" not in rows[0].metadata_json

        # Verify Wrong Logs & Security Audit filtering
        _CAPTURED_LOGS.clear()
        record_captured_log(level="ERROR", logger_name="backend.tasks.auto_trader", message="Dict compare failure SBIN.NS")
        record_captured_log(level="WARNING", logger_name="backend.services.cache", message="Redis latency spike")

        fake_audit = tmp_path / "security_audit.log"
        fake_audit.write_text(
            "\n".join(
                [
                    json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "severity": "CRITICAL", "event_type": "UNHANDLED_EXCEPTION", "ip_address": "10.9.8.7"}),
                    json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "severity": "INFO", "event_type": "ADMIN_LOGIN", "ip_address": "127.0.0.1"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch("backend.core.audit_logger.AUDIT_LOG_PATH", str(fake_audit)):
            hub_err = await fetch_admin_alerts_hub_summary(db, severity="ERROR", search="SBIN")
            assert len(hub_err["recent_logs"]) == 1
            assert "SBIN.NS" in hub_err["recent_logs"][0]["message"]
            assert len(hub_err["security_audit_tail"]) == 0

            hub_crit = await fetch_admin_alerts_hub_summary(db, severity="CRITICAL", search="10.9.8.7")
            assert len(hub_crit["security_audit_tail"]) == 1
            assert hub_crit["security_audit_tail"][0]["event_type"] == "UNHANDLED_EXCEPTION"
    finally:
        _CAPTURED_LOGS.clear()
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_settings_env_write_ebusy_in_place_fallback(tmp_path):
    """Verify Docker single-file bind mount EBUSY error falls back cleanly to in-place update."""
    from backend.api import settings as settings_api

    fake_env = tmp_path / ".env"
    fake_env.write_text('OTHER_KEY="keep_me"\nFYERS_ACCESS_TOKEN="old_tok"\n', encoding="utf-8")

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    mock_session = MagicMock()
    mock_session.generate_token.return_value = {"s": "ok", "access_token": "fresh_live_token_abc"}
    mock_fyers = MagicMock()
    mock_fyers.get_profile.return_value = {"s": "ok", "data": {"name": "Trader", "fy_id": "FY1"}}

    with patch("backend.api.settings._find_env_path", return_value=fake_env), \
         patch("backend.api.settings.dotenv.dotenv_values", return_value={"FYERS_CLIENT_ID": "CID123", "FYERS_SECRET_KEY": "SEC123"}), \
         patch("backend.api.settings.dotenv.set_key", side_effect=OSError(errno.EBUSY, "Device or resource busy")), \
         patch("backend.core.cache.cache_delete", new_callable=AsyncMock), \
         patch("backend.core.cache.cache_set", new_callable=AsyncMock), \
         patch("backend.api.settings.log_security_event"), \
         patch("backend.services.fyers_stream.fyers_stream_service.restart", new_callable=AsyncMock), \
         patch("fyers_apiv3.fyersModel.SessionModel", return_value=mock_session), \
         patch("fyers_apiv3.fyersModel.FyersModel", return_value=mock_fyers):
        admin_u = MagicMock(id=uuid.uuid4(), email="admin@stockai.com", is_admin=True)
        payload = settings_api.FyersTokenUpdateRequest(
            auth_input="auth_code_dummy_exchange_1234567890"
        )
        res = await settings_api.update_fyers_token(request=payload, db=mock_db, admin=admin_u)
        await settings_api.drain_bg_tasks(timeout=1.5)
        assert res["status"] == "success"

    updated_text = fake_env.read_text(encoding="utf-8")
    assert 'OTHER_KEY="keep_me"' in updated_text
    assert 'FYERS_ACCESS_TOKEN="fresh_live_token_abc"' in updated_text
    assert "old_tok" not in updated_text


@pytest.mark.asyncio
async def test_rbac_lockdown_and_presence_role_anti_spoofing():
    """Verify admin-only APIs return 403 for standard users, 401 anon, and presence ignores spoofed role."""
    regular_user = MagicMock(spec=User, id=uuid.uuid4(), email="user@stockai.com", name="Standard User", is_admin=False, is_active=True)

    try:
        # 1. Anonymous user -> 401 on protected routes, forced GUEST on presence
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides[get_current_user_optional] = lambda: None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/swing-audit/current-cycle")).status_code == 401
            assert (await client.get("/api/swing-audit/download-latest")).status_code == 401
            assert (await client.get("/api/settings/fyers/status")).status_code == 401

            with patch("backend.services.presence.presence_service.record_heartbeat", new_callable=AsyncMock, return_value=1) as mock_hb:
                hb_res = await client.post(
                    "/api/presence/heartbeat",
                    json={"session_id": "s1", "role": "ADMIN", "user_id": "spoof", "user_email": "boss@stockai.com", "user_name": "Boss"},
                )
                assert hb_res.status_code == 200
                meta = mock_hb.call_args[0][1]
                assert meta["role"] == "GUEST"
                assert meta["user_id"] is None
                assert meta["user_email"] is None

        # 2. Regular authenticated user -> 403 Forbidden on admin routes, forced USER on presence
        app.dependency_overrides[get_current_user] = lambda: regular_user
        app.dependency_overrides[get_current_user_optional] = lambda: regular_user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/settings/fyers/status")).status_code == 403
            assert (await client.post("/api/swing-audit/sync")).status_code == 403
            assert (await client.post("/api/swing-audit/recalculate")).status_code == 403
            assert (await client.post("/api/swing-audit/cycle/rollover")).status_code == 403

            with patch("backend.services.presence.presence_service.record_heartbeat", new_callable=AsyncMock, return_value=1) as mock_hb:
                hb_res = await client.post(
                    "/api/presence/heartbeat",
                    json={"session_id": "s2", "role": "ADMIN", "user_email": "spoof@stockai.com"},
                )
                assert hb_res.status_code == 200
                meta = mock_hb.call_args[0][1]
                assert meta["role"] == "USER"
                assert meta["user_id"] == str(regular_user.id)
                assert meta["user_email"] == "user@stockai.com"
    finally:
        app.dependency_overrides.clear()
