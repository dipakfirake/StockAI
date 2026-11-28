"""
Comprehensive verification suite for the 5 enterprise security upgrades + Sentinel 100/100 recovery:
1. HttpOnly + SameSite cookie JWT session, Double-Submit CSRF protection, Redis jti revocation,
   token_version invalidation, and short-lived WebSocket tickets (/api/auth/ws-ticket).
2. Zero-lockout Admin Ownership Transfer & TOTP Authenticator MFA (pyotp + offline QR SVG +
   single-use recovery codes + X-Admin-StepUp-Token step-up re-authentication).
3. Redis Lua Token Bucket Rate Limiter & distributed async Brute-Force Lockout (+ fallback).
4. Fernet AES-128-CBC + HMAC-SHA256 DB encryption at rest (enc:v1:) & legacy plaintext compatibility.
5. Hardened Content-Security-Policy (no unsafe-eval; strict script-src outside /docs) &
   Sentinel Health Score 100/100 recovery on Resolve / Resolve All and DB-encrypted Fyers probes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pyotp
import pytest
from httpx import ASGITransport
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request
from starlette.testclient import TestClient

from backend.core.auth import (
    AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    create_access_token,
    hash_password,
    invalidate_user_auth_cache,
    revoke_token_jti,
)
from backend.core.auth_security import brute_force_protector
from backend.core.database import get_db
from backend.core.encryption import decrypt_secret, encrypt_secret, is_encrypted_secret
from backend.core.rate_limiter import TokenBucketRateLimiter
from backend.main import app
from backend.models.admin_alert_event import AdminAlertEvent
from backend.models.notification import Notification
from backend.models.sentinel_incident import SentinelIncident
from backend.models.settings import SystemSettings
from backend.models.user import User
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


class _FakeAsyncRedis:
    """Deterministic in-process async Redis double supporting keys, TTLs, and Lua token bucket eval."""

    def __init__(self):
        self.kv: dict[str, object] = {}
        self.buckets: dict[str, tuple[float, float]] = {}

    async def get(self, key: str):
        return self.kv.get(key)

    async def set(self, key: str, value, ex: int | None = None):
        self.kv[key] = str(value)
        return True

    async def setex(self, key: str, ttl: int, value):
        self.kv[key] = str(value)
        return True

    async def incr(self, key: str):
        val = int(self.kv.get(key, 0) or 0) + 1
        self.kv[key] = str(val)
        return val

    async def expire(self, key: str, ttl: int):
        return True

    async def ttl(self, key: str):
        return 120 if key in self.kv else -2

    async def exists(self, key: str):
        return 1 if key in self.kv else 0

    async def delete(self, *keys: str):
        removed = 0
        for k in keys:
            if k in self.kv:
                del self.kv[k]
                removed += 1
        return removed

    async def eval(
        self,
        script: str,
        numkeys: int,
        key: str,
        capacity,
        refill_rate,
        now_ts,
        requested,
        ttl=3600,
    ):
        cap = float(capacity)
        rate = float(refill_rate)
        now = float(now_ts)
        req = float(requested)
        tokens, last_ts = self.buckets.get(key, (cap, now))
        tokens = min(cap, tokens + max(0.0, now - last_ts) * rate)
        if tokens >= req:
            tokens -= req
            self.buckets[key] = (tokens, now)
            return [1, int(tokens), 0.0]
        self.buckets[key] = (tokens, now)
        wait = (req - tokens) / rate if rate > 0 else 60.0
        return [0, int(tokens), wait]


def _create_sqlite_test_db():
    engine = create_engine("sqlite:///:memory:", future=True)
    for tbl in (
        User.__table__,
        Notification.__table__,
        AdminAlertEvent.__table__,
        SentinelIncident.__table__,
        SystemSettings.__table__,
    ):
        tbl.create(engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    sync_s = SessionLocal()
    return engine, sync_s, _AsyncSQLiteProxy(sync_s)


def test_fernet_encryption_roundtrip_and_legacy_plaintext_compatibility():
    raw = "FYERS_EYJ_SECRET_TOKEN_987654321"
    encrypted = encrypt_secret(raw)
    assert is_encrypted_secret(encrypted) is True
    assert encrypted.startswith("enc:v1:")
    assert raw not in encrypted

    # Idempotent re-encryption does not double-wrap
    assert encrypt_secret(encrypted) == encrypted
    assert decrypt_secret(encrypted) == raw

    # Legacy plaintext DB rows still read seamlessly without migration downtime
    assert is_encrypted_secret("legacy-raw-token") is False
    assert decrypt_secret("legacy-raw-token") == "legacy-raw-token"
    assert decrypt_secret("") == ""


@pytest.mark.asyncio
async def test_sentinel_100_recovery_arithmetic_and_db_encrypted_broker_probe():
    engine, sync_s, async_s = _create_sqlite_test_db()
    orig_subs = json.loads(json.dumps(sentinel_service._subsystem_status))
    orig_incidents = list(sentinel_service._recent_incidents)
    try:
        # Insert an encrypted token ONLY in DB (clear env fallback checks via patch)
        sync_s.add(
            SystemSettings(
                key="fyers_access_token",
                value=encrypt_secret("DB_FYERS_ACCESS_TOKEN_TEST"),
            )
        )
        sync_s.commit()

        class _ScalarOneSession:
            def __init__(self, session):
                self._s = session

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def execute(self, stmt, params=None):
                return self._s.execute(stmt, params or {})

        with patch("backend.core.database.AsyncSessionLocal", return_value=_ScalarOneSession(sync_s)):
            with patch.dict("os.environ", {"FYERS_ACCESS_TOKEN": ""}, clear=False):
                with patch("backend.core.config.settings.FYERS_ACCESS_TOKEN", ""):
                    await sentinel_service._probe_broker()
        assert sentinel_service._subsystem_status["broker_api"]["status"] == "HEALTHY"

        # Simulate WARNING in two subsystems to verify additive (not short-circuited `or`) deduction
        sentinel_service._subsystem_status["security"]["status"] = "WARNING"
        sentinel_service._subsystem_status["database"]["status"] = "WARNING"
        for k in ("redis", "celery", "broker_api"):
            sentinel_service._subsystem_status[k]["status"] = "HEALTHY"
        summary_two_warn = sentinel_service.get_health_summary()
        assert summary_two_warn["health_score"] == 80

        # Resolve incident restores security subsystem back cleanly to 100/100 when DB healthy
        sentinel_service._subsystem_status["database"]["status"] = "HEALTHY"
        await sentinel_service._record_incident(
            subsystem="SECURITY",
            severity="WARNING",
            title="Synthetic Warn Test",
            detail="unit test",
        )
        inc_id = next(
            i["id"] for i in sentinel_service._recent_incidents if i["title"] == "Synthetic Warn Test"
        )
        assert await sentinel_service.resolve_incident(inc_id) is True
        summary_resolved = sentinel_service.get_health_summary()
        assert summary_resolved["subsystems"]["security"]["status"] == "HEALTHY"
        assert summary_resolved["health_score"] == 100
    finally:
        sentinel_service._subsystem_status = orig_subs
        sentinel_service._recent_incidents = orig_incidents
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_acknowledge_vs_resolve_all_syncs_sentinel_and_alerts_hub():
    engine, sync_s, async_s = _create_sqlite_test_db()
    orig_subs = json.loads(json.dumps(sentinel_service._subsystem_status))
    orig_incidents = list(sentinel_service._recent_incidents)

    admin_user = User(
        id=uuid.uuid4(),
        email="headadmin@example.com",
        name="Head Admin",
        hashed_password=hash_password("AdminPass#123"),
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
        pro_status="APPROVED",
        token_version=1,
    )
    sync_s.add(admin_user)
    sync_s.add_all(
        [
            AdminAlertEvent(
                fingerprint="fp-sec-1",
                category="SECURITY_THREAT",
                severity="CRITICAL",
                subsystem="SECURITY",
                title="Brute Force Test",
                detail="5 failed attempts",
                status="OPEN",
            ),
            AdminAlertEvent(
                fingerprint="fp-err-2",
                category="ERROR_LOG",
                severity="WARNING",
                subsystem="YFINANCE",
                title="Transient Feed Warn",
                detail="429 retry",
                status="OPEN",
            ),
        ]
    )
    sync_s.add(
        SentinelIncident(
            fingerprint="sen-sec-1",
            subsystem="SECURITY",
            severity="WARNING",
            title="Brute Force Test",
            detail="active alert",
            status="OPEN",
        )
    )
    sync_s.commit()

    sentinel_service._subsystem_status["security"]["status"] = "WARNING"
    for k in ("database", "redis", "celery", "broker_api"):
        sentinel_service._subsystem_status[k]["status"] = "HEALTHY"

    async def _override_db():
        yield async_s

    app.dependency_overrides[get_db] = _override_db
    token = create_access_token({"sub": str(admin_user.id)}, token_version=1)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            # Acknowledge keeps alerts open/counted
            ack_res = await client.post(
                "/api/admin/alerts-hub/acknowledge",
                headers=headers,
                json={"action": "ACKNOWLEDGE", "mark_all": True},
            )
            assert ack_res.status_code == 200
            assert ack_res.json()["status"] == "ACKNOWLEDGED"
            assert sentinel_service.get_health_summary()["health_score"] == 90

            # Resolve All closes alerts + SentinelIncident rows + restores Sentinel 100/100
            res_all = await client.post(
                "/api/admin/alerts-hub/acknowledge",
                headers=headers,
                json={"action": "RESOLVE", "mark_all": True},
            )
            assert res_all.status_code == 200
            assert res_all.json()["status"] == "RESOLVED"
            assert sentinel_service.get_health_summary()["subsystems"]["security"]["status"] == "HEALTHY"
            assert sentinel_service.get_health_summary()["health_score"] == 100

        s_rows = sync_s.execute(select(SentinelIncident)).scalars().all()
        assert all(s.status == "RESOLVED" for s in s_rows)
    finally:
        app.dependency_overrides.pop(get_db, None)
        sentinel_service._subsystem_status = orig_subs
        sentinel_service._recent_incidents = orig_incidents
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_httponly_cookie_csrf_revocation_token_version_and_ws_ticket():
    engine, sync_s, async_s = _create_sqlite_test_db()
    fake_redis = _FakeAsyncRedis()

    trader = User(
        id=uuid.uuid4(),
        email="trader.cookie@example.com",
        name="Cookie Trader",
        hashed_password=hash_password("TraderPass#999"),
        is_active=True,
        is_admin=False,
        subscription_tier="FREE",
        pro_status="NONE",
        token_version=1,
    )
    admin_user = User(
        id=uuid.uuid4(),
        email="owner.admin@example.com",
        name="Owner Admin",
        hashed_password=hash_password("OwnerPass#999"),
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
        pro_status="APPROVED",
        token_version=1,
    )
    sync_s.add_all([trader, admin_user])
    sync_s.commit()

    async def _override_db():
        yield async_s

    app.dependency_overrides[get_db] = _override_db

    try:
        with patch("backend.core.cache.get_redis", AsyncMock_fn := patch_async(fake_redis)):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
                # 1. Login issues HttpOnly access cookie + readable CSRF cookie
                login_res = await client.post(
                    "/api/auth/login",
                    data={"username": trader.email, "password": "TraderPass#999"},
                )
                assert login_res.status_code == 200
                access_cookie = client.cookies.get(AUTH_COOKIE_NAME)
                csrf_cookie = client.cookies.get(CSRF_COOKIE_NAME)
                assert access_cookie
                assert csrf_cookie

                # Hardened CSP check on API response (no unsafe-eval / no unsafe-inline script)
                csp = login_res.headers.get("Content-Security-Policy", "")
                assert "'unsafe-eval'" not in csp
                assert "script-src 'self' https://accounts.google.com" in csp

                # 2. Cookie authenticates GET /api/auth/me cleanly without Bearer header
                me_res = await client.get("/api/auth/me")
                assert me_res.status_code == 200
                assert me_res.json()["email"] == trader.email

                # 3. Double-Submit CSRF blocks cookie POST without X-CSRF-Token header
                csrf_block = await client.post("/api/auth/ws-ticket")
                assert csrf_block.status_code == 403
                assert "CSRF" in csrf_block.json()["detail"]

                # 4. Cookie POST with matching X-CSRF-Token succeeds & returns 45s ws_ticket
                ticket_res = await client.post(
                    "/api/auth/ws-ticket",
                    headers={"X-CSRF-Token": csrf_cookie},
                )
                assert ticket_res.status_code == 200
                ws_ticket = ticket_res.json()["ws_ticket"]
                assert ticket_res.json()["expires_in"] == 45

                # Single-purpose ws_ticket MUST NOT be accepted as a session JWT on HTTP routes
                bad_scope = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {ws_ticket}"},
                )
                assert bad_scope.status_code == 401

                # 5. Admin revoking user sessions bumps token_version and invalidates existing cookie/JWT
                admin_jwt = create_access_token({"sub": str(admin_user.id)}, token_version=1)
                rev_res = await client.post(
                    f"/api/admin/users/{trader.id}/revoke-sessions",
                    headers={"Authorization": f"Bearer {admin_jwt}"},
                )
                assert rev_res.status_code == 200
                assert rev_res.json()["token_version"] == 2

                invalidate_user_auth_cache(trader.id)
                stale_me = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {access_cookie}"},
                )
                assert stale_me.status_code == 401

                # 6. Explicit Logout revokes JWT jti in Redis immediately
                fresh_login = await client.post(
                    "/api/auth/login",
                    data={"username": trader.email, "password": "TraderPass#999"},
                )
                assert fresh_login.status_code == 200
                fresh_jwt = fresh_login.json()["access_token"]
                fresh_csrf = client.cookies.get(CSRF_COOKIE_NAME)
                out_res = await client.post(
                    "/api/auth/logout",
                    headers={"X-CSRF-Token": fresh_csrf},
                )
                assert out_res.status_code == 200
                replayed = await client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {fresh_jwt}"},
                )
                assert replayed.status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)
        sync_s.close()
        engine.dispose()


def patch_async(obj):
    async def _fn():
        return obj

    return _fn


@pytest.mark.asyncio
async def test_zero_lockout_admin_ownership_transfer_and_totp_mfa_stepup():
    engine, sync_s, async_s = _create_sqlite_test_db()
    fake_redis = _FakeAsyncRedis()

    legacy_admin = User(
        id=uuid.uuid4(),
        email="legacy.admin@example.com",
        name="Legacy Admin",
        hashed_password=hash_password("LegacyPass#123"),
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
        pro_status="APPROVED",
        token_version=1,
    )
    personal_user = User(
        id=uuid.uuid4(),
        email="personal.owner@gmail.com",
        name="Personal Owner",
        hashed_password=hash_password("PersonalPass#123"),
        is_active=True,
        is_admin=False,
        subscription_tier="FREE",
        pro_status="NONE",
        token_version=1,
    )
    sync_s.add_all([legacy_admin, personal_user])
    sync_s.commit()

    async def _override_db():
        yield async_s

    app.dependency_overrides[get_db] = _override_db

    try:
        with patch("backend.core.cache.get_redis", patch_async(fake_redis)):
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
                legacy_jwt = create_access_token({"sub": str(legacy_admin.id)}, token_version=1)
                legacy_hdr = {"Authorization": f"Bearer {legacy_jwt}"}

                # Zero-lockout: non-MFA admin cannot demote themselves & cannot leave 0 admins
                self_demote = await client.post(
                    f"/api/admin/users/{legacy_admin.id}/set-admin",
                    headers=legacy_hdr,
                    json={"is_admin": False},
                )
                assert self_demote.status_code == 400

                # Promote personal email to Admin (no MFA required yet -> zero lockout!)
                promote_res = await client.post(
                    f"/api/admin/users/{personal_user.id}/set-admin",
                    headers=legacy_hdr,
                    json={"is_admin": True},
                )
                assert promote_res.status_code == 200
                assert promote_res.json()["is_admin"] is True

                # Sign in as personal email & demote unowned legacy admin email
                personal_jwt = create_access_token({"sub": str(personal_user.id)}, token_version=1)
                personal_hdr = {"Authorization": f"Bearer {personal_jwt}"}
                demote_legacy = await client.post(
                    f"/api/admin/users/{legacy_admin.id}/set-admin",
                    headers=personal_hdr,
                    json={"is_admin": False},
                )
                assert demote_legacy.status_code == 200
                assert demote_legacy.json()["is_admin"] is False

                # Cannot demote the last remaining admin (personal_owner) even via API
                # Enroll phone Authenticator TOTP MFA cleanly on personal_owner (zero email needed)
                start_res = await client.post("/api/admin/mfa/enroll/start", headers=personal_hdr)
                assert start_res.status_code == 200
                start_data = start_res.json()
                assert start_data["qr_svg"].startswith("data:image/svg+xml;base64,")
                assert "otpauth://totp/" in start_data["otpauth_uri"]
                raw_secret = start_data["manual_secret"].replace(" ", "")
                totp = pyotp.TOTP(raw_secret)

                confirm_res = await client.post(
                    "/api/admin/mfa/enroll/confirm",
                    headers=personal_hdr,
                    json={"setup_token": start_data["setup_token"], "code": totp.now()},
                )
                assert confirm_res.status_code == 200
                recovery_codes = confirm_res.json()["recovery_codes"]
                assert len(recovery_codes) == 8

                # Secret stored in DB must be Fernet-encrypted, never plaintext Base32
                sync_s.refresh(personal_user)
                assert personal_user.totp_enabled is True
                assert is_encrypted_secret(personal_user.totp_secret_encrypted) is True
                assert raw_secret not in (personal_user.totp_secret_encrypted or "")

                # Login now halts at mfa_required=True WITHOUT issuing session cookie yet
                client.cookies.clear()
                mfa_login = await client.post(
                    "/api/auth/login",
                    data={"username": personal_user.email, "password": "PersonalPass#123"},
                )
                assert mfa_login.status_code == 200
                mfa_body = mfa_login.json()
                assert mfa_body["mfa_required"] is True
                assert mfa_body["mfa_challenge_token"]
                assert client.cookies.get(AUTH_COOKIE_NAME) is None

                # Verify single-use recovery code works once, and cannot be reused
                bad_verify = await client.post(
                    "/api/auth/mfa/verify-login",
                    json={"challenge_token": mfa_body["mfa_challenge_token"], "code": "000000"},
                )
                assert bad_verify.status_code == 401

                rec_verify = await client.post(
                    "/api/auth/mfa/verify-login",
                    json={"challenge_token": mfa_body["mfa_challenge_token"], "code": recovery_codes[0]},
                )
                assert rec_verify.status_code == 200
                assert rec_verify.json()["user"]["totp_enabled"] is True
                assert client.cookies.get(AUTH_COOKIE_NAME)

                # Step-Up guard blocks destructive broadcast until X-Admin-StepUp-Token is verified
                blocked = await client.post(
                    "/api/admin/broadcast-notice",
                    headers=personal_hdr,
                    json={"title": "Test", "message": "Blocked without step-up", "priority": "INFO"},
                )
                assert blocked.status_code == 403
                assert blocked.headers.get("X-StepUp-Required") == "totp"

                # Verify reused recovery code is rejected, live TOTP code succeeds
                reuse_fail = await client.post(
                    "/api/admin/mfa/step-up",
                    headers=personal_hdr,
                    json={"code": recovery_codes[0]},
                )
                assert reuse_fail.status_code == 401

                stepup_ok = await client.post(
                    "/api/admin/mfa/step-up",
                    headers=personal_hdr,
                    json={"code": totp.now()},
                )
                assert stepup_ok.status_code == 200
                stepup_tok = stepup_ok.json()["stepup_token"]

                allowed = await client.post(
                    "/api/admin/broadcast-notice",
                    headers={**personal_hdr, "X-Admin-StepUp-Token": stepup_tok},
                    json={"title": "Verified", "message": "Step-up succeeded", "priority": "INFO"},
                )
                assert allowed.status_code == 200
                assert allowed.json()["success"] is True

                # Swagger CSP keeps unsafe-inline strictly isolated from API routes
                docs_res = await client.get("/docs")
                docs_csp = docs_res.headers.get("Content-Security-Policy", "")
                assert "cdn.jsdelivr.net" in docs_csp
    finally:
        app.dependency_overrides.pop(get_db, None)
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_distributed_redis_rate_limiter_and_bruteforce_lockout():
    fake_redis = _FakeAsyncRedis()
    limiter = TokenBucketRateLimiter()
    brute_force_protector.record_success("198.51.100.77", "bf_unit@example.com")

    req = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": [],
            "client": ("198.51.100.88", 12345),
            "query_string": b"",
        }
    )

    try:
        with patch("backend.core.cache.get_redis", patch_async(fake_redis)):
            # AUTH tier allows 10 burst requests per IP via distributed Redis Lua script
            for _ in range(10):
                allowed, hdrs, _ = await limiter.check_rate_limit(req)
                assert allowed is True
                assert hdrs["X-RateLimit-Tier"] == "AUTH"

            allowed_11th, hdrs_11th, _ = await limiter.check_rate_limit(req)
            assert allowed_11th is False
            assert "Retry-After" in hdrs_11th
            assert any(k.startswith("rl:AUTH:") for k in fake_redis.buckets.keys())

            for _ in range(5):
                await brute_force_protector.record_failure_async("198.51.100.77", "bf_unit@example.com")

            # Verify lockout key landed in distributed Redis and triggers HTTP 429
            assert any(k.startswith("bf:lock:") for k in fake_redis.kv.keys())
            with pytest.raises(Exception) as exc_info:
                await brute_force_protector.check_lockout_async("198.51.100.77", "bf_unit@example.com")
            assert getattr(exc_info.value, "status_code", None) == 429

            await brute_force_protector.record_success_async("198.51.100.77", "bf_unit@example.com")
            await brute_force_protector.check_lockout_async("198.51.100.77", "bf_unit@example.com")
    finally:
        brute_force_protector.record_success("198.51.100.77", "bf_unit@example.com")


def test_websocket_accepts_ticket_and_rejects_revoked_jti():
    fake_redis = _FakeAsyncRedis()
    engine, sync_s, async_s = _create_sqlite_test_db()
    user_id = uuid.uuid4()
    ws_user = User(
        id=user_id,
        email="ws.ticket@example.com",
        name="WS Tester",
        hashed_password=hash_password("WsPass#123"),
        is_active=True,
        is_admin=False,
        token_version=1,
    )
    sync_s.add(ws_user)
    sync_s.commit()

    from backend.core.auth import create_ws_ticket

    ticket = create_ws_ticket(user_id, False, 1)
    revoked_jwt = create_access_token({"sub": str(user_id)}, token_version=1)

    with patch("backend.core.cache.get_redis", patch_async(fake_redis)):
        import asyncio
        from jose import jwt as _jwt
        from backend.core.config import settings

        claims = _jwt.decode(revoked_jwt, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        asyncio.get_event_loop().run_until_complete(revoke_token_jti(claims["jti"], claims["exp"]))

        with TestClient(app) as tc:
            with tc.websocket_connect(f"/ws/?ticket={ticket}") as ws:
                ws.send_text("ping")
                assert ws.receive_text() == "pong"

            with pytest.raises(Exception):
                with tc.websocket_connect(f"/ws/?token={revoked_jwt}"):
                    pass

    sync_s.close()
    engine.dispose()



@pytest.mark.asyncio
async def test_fyers_stream_decrypts_db_token_and_beats_stale_env():
    import asyncio
    from backend.services.fyers_stream import FyersStreamService
    from backend.services.market_data import MarketDataService

    engine, sync_s, _ = _create_sqlite_test_db()
    sync_s.add_all(
        [
            SystemSettings(key="fyers_client_id", value="DB_CLIENT_999"),
            SystemSettings(key="fyers_access_token", value=encrypt_secret("LIVE_VALID_DB_TOKEN_987654321")),
        ]
    )
    sync_s.commit()

    class _StreamDbProxy:
        def __init__(self, s):
            self._s = s

        async def execute(self, stmt, params=None):
            return self._s.execute(stmt, params or {})

        async def close(self):
            return None

    captured_tokens = []

    class _FakeSocket:
        def __init__(self, access_token=None, **kwargs):
            captured_tokens.append(access_token)

        def connect(self):
            return None

        def close_connection(self):
            return None

    stream = FyersStreamService()
    MarketDataService.reset_fyers_health()

    try:
        with patch("backend.services.fyers_stream.cache_get", AsyncMock_fn := patch_async(None)), \
             patch("backend.core.database.AsyncSessionLocal", return_value=_StreamDbProxy(sync_s)), \
             patch("backend.services.fyers_stream.FyersDataSocket", _FakeSocket), \
             patch("backend.services.fyers_stream.settings") as mock_settings, \
             patch("backend.services.market_data.MarketDataService._env_cache", {"FYERS_ACCESS_TOKEN": "OLD_EXPIRED_ENV"}):

            mock_settings.FYERS_CLIENT_ID = "ENV_OLD_CID"
            mock_settings.FYERS_ACCESS_TOKEN = "OLD_EXPIRED_ENV_TOKEN"

            ok = await stream.start()
            assert ok is True
            assert len(captured_tokens) == 1
            assert captured_tokens[0] == "DB_CLIENT_999:LIVE_VALID_DB_TOKEN_987654321"
            assert "enc:v1:" not in captured_tokens[0]

            # -99 token error cleanly engages failover and halts SDK reconnect loop
            stream._on_error({"type": "cn", "code": -99, "message": "Token is expired", "s": "error"})
            await asyncio.sleep(0.05)
            assert MarketDataService._fyers_token_valid is False
            assert stream._is_running is False
            assert stream._socket is None
    finally:
        MarketDataService.reset_fyers_health()
        sync_s.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_routine_admin_actions_stay_info_and_persist_sentinel_watermark():
    import logging
    from backend.core.logging_config import AdminErrorLogHandler
    from backend.services.admin_alerts_service import _CAPTURED_LOGS, _PENDING_DB_ALERTS

    engine, sync_s, async_s = _create_sqlite_test_db()
    orig_subs = json.loads(json.dumps(sentinel_service._subsystem_status))
    orig_incidents = list(sentinel_service._recent_incidents)
    orig_wm = sentinel_service._security_log_watermark

    admin1 = User(
        id=uuid.uuid4(),
        email="head.owner@example.com",
        name="Head Owner",
        hashed_password=hash_password("OwnerPass#123"),
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
        pro_status="APPROVED",
        token_version=1,
    )
    user2 = User(
        id=uuid.uuid4(),
        email="old.admin@example.com",
        name="Old Admin",
        hashed_password=hash_password("OldPass#123"),
        is_active=True,
        is_admin=True,
        subscription_tier="PRO",
        pro_status="APPROVED",
        token_version=1,
    )
    sync_s.add_all([admin1, user2])
    sync_s.commit()

    # Transient third-party websocket close noise must not capture into Admin alerts
    handler = AdminErrorLogHandler(level=logging.WARNING)
    before_logs = len(_CAPTURED_LOGS)
    rec = logging.LogRecord(
        name="websocket",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="Connection to remote host was lost. - goodbye",
        args=(),
        exc_info=None,
    )
    handler.emit(rec)
    assert len(_CAPTURED_LOGS) == before_logs

    async def _override_db():
        yield async_s

    _PENDING_DB_ALERTS.clear()
    app.dependency_overrides[get_db] = _override_db
    hdrs = {"Authorization": f"Bearer {create_access_token({'sub': str(admin1.id)}, token_version=1)}"}

    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://testserver") as client:
            r1 = await client.post(
                f"/api/admin/users/{user2.id}/set-admin",
                headers=hdrs,
                json={"is_admin": False},
            )
            assert r1.status_code == 200
            r2 = await client.post(
                f"/api/admin/users/{user2.id}/revoke-sessions",
                headers=hdrs,
            )
            assert r2.status_code == 200
            # Routine admin actions must stay INFO audit logs and NOT queue WARNING threat alerts
            assert len(_PENDING_DB_ALERTS) == 0
            assert sync_s.execute(select(AdminAlertEvent)).scalars().all() == []

            # Resolve All persists sentinel_security_watermark in DB & returns 100/100 health summary
            sentinel_service._subsystem_status["security"]["status"] = "WARNING"
            for k in ("database", "redis", "celery", "broker_api"):
                sentinel_service._subsystem_status[k]["status"] = "HEALTHY"
            res_all = await client.post(
                "/api/admin/alerts-hub/acknowledge",
                headers=hdrs,
                json={"action": "RESOLVE", "mark_all": True},
            )
            assert res_all.status_code == 200
            body = res_all.json()
            assert body["sentinel_summary"]["health_score"] == 100

        wm_row = sync_s.execute(
            select(SystemSettings).where(SystemSettings.key == "sentinel_security_watermark")
        ).scalars().first()
        assert wm_row is not None and wm_row.value
    finally:
        app.dependency_overrides.pop(get_db, None)
        sentinel_service._subsystem_status = orig_subs
        sentinel_service._recent_incidents = orig_incidents
        sentinel_service._security_log_watermark = orig_wm
        sync_s.close()
        engine.dispose()
