"""
Adversarial Challenge & Empirical Stress Test Suite for Milestone 3 Gate
Author: Challenger 1 (E2E Concurrency & Token Lifecycle Challenger)

Adversarial Tests:
1. Warmup Governor Phase Ramp-Up Spacing (0-20s, 20-40s, 40-60s, >60s).
2. Rate Budget Resilience Under Redis Outage / Timeout.
3. Sentinel Endpoint Admin Authorization Leak Prevention (all 5 endpoints guarded).
4. Concurrent Thundering Herd Race Condition Stress (50 microsecond-simultaneous requests).
5. Token Update Under Active WebSocket Connections (session preservation).
"""

import asyncio
import datetime
import time
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.api.admin import require_admin
from backend.models.user import User
from backend.models.settings import SystemSettings
from backend.services.market_data import MarketDataService
from backend.services.fyers_stream import fyers_stream_service
from backend.api.websocket import _market_connections, _symbol_subscribers


@pytest.fixture(autouse=True)
def reset_market_data_state():
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    MarketDataService._fyers_cooldown_until = 0.0
    MarketDataService._fyers_token_valid = True
    MarketDataService._fyers_token_error_reason = ""
    MarketDataService._active_engine = "PRIMARY_FYERS"
    MarketDataService._circuit_state = "CLOSED"
    MarketDataService._canary_in_progress = False
    _market_connections.clear()
    _symbol_subscribers.clear()
    yield
    MarketDataService._fyers_request_timestamps.clear()
    MarketDataService._last_fyers_request_time = 0.0
    MarketDataService._warmup_until = 0.0
    MarketDataService._warmup_started_at = 0.0
    _market_connections.clear()
    _symbol_subscribers.clear()


# ===========================================================================
# Challenge 1: Warmup Governor Phase Ramp-Up Validation
# ===========================================================================
@pytest.mark.asyncio
async def test_warmup_governor_phase_ramp_up_spacing():
    """
    Stress-tests the warmup governor ramp-up curve across all three phases:
    - Phase 1 (0-20s): spacing required is 1.5s
    - Phase 2 (20-40s): spacing required is 0.8s
    - Phase 3 (40-60s): spacing required is 0.4s
    - Post-Warmup (>60s): spacing required is 0.25s
    """
    base_time = 100000.0
    sim_time = base_time

    def get_sim_time():
        return sim_time

    with patch("time.time", side_effect=get_sim_time):
        MarketDataService.reset_fyers_health()
        MarketDataService._warmup_started_at = base_time
        MarketDataService._warmup_until = base_time + 60.0

        # Phase 1: elapsed = 5s (in 0-20s phase). Spacing = 1.5s
        sim_time = base_time + 5.0
        res1 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res1 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Second request 1.0s later (< 1.5s) must be rejected
        sim_time = base_time + 6.0
        res2 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res2 is False, "Phase 1 must enforce 1.5s spacing"

        # Third request 1.6s later (>= 1.5s) must be admitted
        sim_time = base_time + 6.6
        res3 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res3 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Phase 2: elapsed = 25s (in 20-40s phase). Spacing = 0.8s
        # Request at 25.0s (after > 0.8s gap) succeeds
        sim_time = base_time + 25.0
        res4 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res4 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Request at 25.5s (0.5s later, < 0.8s) must be rejected
        sim_time = base_time + 25.5
        res5 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res5 is False, "Phase 2 must enforce 0.8s spacing"

        # Request at 25.9s (0.9s later, >= 0.8s) must be admitted
        sim_time = base_time + 25.9
        res6 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res6 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Phase 3: elapsed = 45s (in 40-60s phase). Spacing = 0.4s
        sim_time = base_time + 45.0
        res7 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res7 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Request at 45.2s (< 0.4s) must be rejected
        sim_time = base_time + 45.2
        res8 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res8 is False, "Phase 3 must enforce 0.4s spacing"

        # Request at 45.45s (>= 0.4s) must be admitted
        sim_time = base_time + 45.45
        res9 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res9 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Phase 4: Post-Warmup (> 60s). Spacing = 0.25s
        sim_time = base_time + 65.0
        assert MarketDataService.is_in_warmup() is False
        res10 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res10 is True
        MarketDataService._fyers_request_timestamps.append(sim_time)
        MarketDataService._last_fyers_request_time = sim_time

        # Request at 65.1s (0.1s later, < 0.25s) must be rejected
        sim_time = base_time + 65.1
        res11 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res11 is False, "Post-warmup must enforce 0.25s spacing"

        # Request at 65.3s (0.3s later, >= 0.25s) must be admitted
        sim_time = base_time + 65.3
        res12 = MarketDataService._check_in_memory_rate_budget(sim_time)
        assert res12 is True


# ===========================================================================
# Challenge 2: Redis Outage / Exception Resilience in Rate Limiting
# ===========================================================================
@pytest.mark.asyncio
async def test_rate_budget_resilience_under_redis_outage():
    """
    Simulates Redis connection failure / timeout during rate budget check.
    Verifies that MarketDataService gracefully falls back to in-memory rate limiting
    without raising an uncaught exception or dropping the request.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService.engage_warmup_governor(60.0)

    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = ConnectionError("Redis connection refused")

    with patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)):
        # First request should evaluate in-memory and succeed
        res1 = await MarketDataService.check_and_record_fyers_rate_budget()
        assert res1 is True

        # Rapid second request within warmup window must be rejected (not error out)
        res2 = await MarketDataService.check_and_record_fyers_rate_budget()
        assert res2 is False


# ===========================================================================
# Challenge 3: Strict Sentinel Admin Authorization Coverage
# ===========================================================================
@pytest.mark.asyncio
async def test_sentinel_admin_authorization_leak_prevention():
    """
    Verifies that standard non-admin users and unauthenticated users CANNOT access
    any Sentinel surveillance endpoint, preventing authorization leaks.
    """
    non_admin_user = MagicMock(spec=User)
    non_admin_user.id = uuid.uuid4()
    non_admin_user.email = "regular_user@example.com"
    non_admin_user.is_admin = False

    transport = ASGITransport(app=app)

    # 1. Non-admin user access attempt
    app.dependency_overrides[get_current_user] = lambda: non_admin_user
    # require_admin raises 403 when not admin
    from fastapi import HTTPException
    def mock_require_admin():
        if not non_admin_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return non_admin_user

    app.dependency_overrides[require_admin] = mock_require_admin

    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            endpoints = [
                ("GET", "/api/sentinel/status"),
                ("GET", "/api/sentinel/incidents"),
                ("POST", "/api/sentinel/audit-now"),
                ("POST", "/api/sentinel/resolve"),
                ("POST", f"/api/sentinel/resolve/{uuid.uuid4()}"),
            ]

            for method, ep in endpoints:
                if method == "GET":
                    resp = await client.get(ep)
                else:
                    resp = await client.post(ep, json={"incident_id": str(uuid.uuid4())})

                assert resp.status_code == 403, f"Endpoint {ep} allowed non-admin access! Status: {resp.status_code}"
    finally:
        app.dependency_overrides.clear()


# ===========================================================================
# Challenge 4: Concurrent Microsecond Thundering Herd Race Condition Stress
# ===========================================================================
@pytest.mark.asyncio
async def test_thundering_herd_microsecond_concurrency_race_condition():
    """
    Fires 50 concurrent requests simultaneously at the exact same microsecond during warmup.
    Verifies that _rate_budget_lock strictly serializes requests and prevents race conditions,
    allowing EXACTLY 1 request through to Fyers and blocking the other 49.
    """
    MarketDataService.reset_fyers_health()
    MarketDataService.engage_warmup_governor(60.0)

    mock_redis = MagicMock()
    mock_redis.pipeline.return_value.execute = AsyncMock(return_value=[0, 0, 0])

    with patch("backend.core.cache.get_redis", new=AsyncMock(return_value=mock_redis)):
        tasks = [MarketDataService.check_and_record_fyers_rate_budget() for _ in range(50)]
        results = await asyncio.gather(*tasks)

    admitted_count = sum(1 for r in results if r is True)
    rejected_count = sum(1 for r in results if r is False)

    assert admitted_count == 1, f"Expected exactly 1 admitted request, got {admitted_count}"
    assert rejected_count == 49, f"Expected 49 rejected requests, got {rejected_count}"


# ===========================================================================
# Challenge 5: Token Update Under Active WebSocket Connections
# ===========================================================================
@pytest.mark.asyncio
async def test_token_update_preserves_active_websocket_connections():
    """
    Tests that updating the Fyers token via /api/settings/fyers/update-token
    does NOT drop or corrupt active frontend WebSocket sessions in _market_connections.
    """
    mock_admin_user = MagicMock(spec=User)
    mock_admin_user.id = uuid.uuid4()
    mock_admin_user.email = "admin@example.com"
    mock_admin_user.is_admin = True

    # Register 10 active frontend WebSocket connections
    for i in range(10):
        cid = f"conn_{i}"
        mock_ws = AsyncMock()
        _market_connections[cid] = {"ws": mock_ws, "symbols": {"RELIANCE.NS"}, "user_id": f"user_{i}"}

    assert len(_market_connections) == 10

    from backend.tests.test_e2e_token_navigation_simulation import MockDbSession
    db_session = MockDbSession(mock_admin_user)

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[require_admin] = lambda: mock_admin_user
    app.dependency_overrides[get_db] = lambda: (yield db_session)

    mock_session = MagicMock()
    mock_session.generate_token.return_value = {"s": "ok", "access_token": "new_token_123"}
    mock_fyers_instance = MagicMock()
    mock_fyers_instance.get_profile.return_value = {"s": "ok", "data": {"name": "Test Trader", "fy_id": "TT123", "email_id": "t@t.com"}}

    transport = ASGITransport(app=app)
    try:
        with patch("backend.api.settings.fyersModel.SessionModel", return_value=mock_session), \
             patch("backend.api.settings.fyersModel.FyersModel", return_value=mock_fyers_instance), \
             patch.object(fyers_stream_service, "restart", new_callable=AsyncMock) as mock_restart, \
             patch("backend.core.cache.cache_set", new=AsyncMock()), \
             patch("backend.core.cache.cache_delete", new=AsyncMock()), \
             patch("backend.api.settings.cache_set", new=AsyncMock()), \
             patch("backend.api.settings.cache_delete", new=AsyncMock()), \
             patch("backend.api.settings.dotenv.set_key"):

            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                res = await client.post(
                    "/api/settings/fyers/update-token",
                    json={"auth_input": "https://trade.fyers.in/api-login/redirect-uri/index.html?auth_code=CODE123&state=none"},
                )

            assert res.status_code == 200
            # All 10 active frontend WebSocket sessions must remain intact
            assert len(_market_connections) == 10
            for i in range(10):
                assert f"conn_{i}" in _market_connections
    finally:
        app.dependency_overrides.clear()
        _market_connections.clear()
