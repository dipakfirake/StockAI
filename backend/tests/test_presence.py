"""
Tests for the Real-Time Presence Service and API Endpoints.
Verifies sliding-window TTL, instant leave detection, fallback resilience, and endpoint responses.
"""

import pytest
import time
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.presence import PresenceService, PRESENCE_TTL_SECONDS


@pytest.fixture
def clean_presence_service():
    """Create an isolated PresenceService instance with in-memory fallback enabled."""
    service = PresenceService()
    return service


@pytest.mark.asyncio
async def test_presence_heartbeat_and_leave_in_memory():
    """Test that heartbeat increments count and leave decrements count in memory."""
    service = PresenceService()
    
    # Mock get_redis to return None so it tests the resilient in-memory fallback
    with patch("backend.services.presence.get_redis", new=AsyncMock(return_value=None)):
        c1 = await service.record_heartbeat("session_a")
        assert c1 == 1

        c2 = await service.record_heartbeat("session_b")
        assert c2 == 2

        # Re-heartbeating existing session should not increase count
        c2_dup = await service.record_heartbeat("session_a")
        assert c2_dup == 2

        # Leave session_a
        c_after_leave = await service.record_leave("session_a")
        assert c_after_leave == 1

        # Leave session_b
        c_final = await service.record_leave("session_b")
        assert c_final == 0


@pytest.mark.asyncio
async def test_presence_sliding_window_pruning():
    """Test that sessions older than PRESENCE_TTL_SECONDS are pruned."""
    service = PresenceService()

    with patch("backend.services.presence.get_redis", new=AsyncMock(return_value=None)):
        # Inject an old session older than TTL
        old_time = time.time() - (PRESENCE_TTL_SECONDS + 10)
        service._local_sessions["stale_session"] = old_time
        service._local_sessions["fresh_session"] = time.time()

        # get_active_count should prune the stale session
        active = await service.get_active_count()
        assert active == 1
        assert "stale_session" not in service._local_sessions
        assert "fresh_session" in service._local_sessions


@pytest.mark.asyncio
async def test_presence_redis_pipeline_interaction():
    """Test interaction with Redis pipeline when Redis is active."""
    service = PresenceService()

    mock_redis = MagicMock()
    mock_redis.zcard = AsyncMock(return_value=3)
    mock_pipe = MagicMock()
    mock_pipe.zadd = MagicMock()
    mock_pipe.hset = MagicMock()
    mock_pipe.zrangebyscore = MagicMock()
    mock_pipe.zremrangebyscore = MagicMock()
    mock_pipe.zcard = MagicMock()
    mock_pipe.zrem = MagicMock()
    # execute returns list of results: [zadd_res, hset_res, stale_ids]
    mock_pipe.execute = AsyncMock(return_value=[1, 1, []])
    mock_redis.pipeline = MagicMock(return_value=mock_pipe)

    with patch("backend.services.presence.get_redis", new=AsyncMock(return_value=mock_redis)):
        count = await service.record_heartbeat("test_redis_session")
        assert count == 3
        mock_pipe.zadd.assert_called_once()
        mock_redis.zcard.assert_called_once()


def test_presence_api_endpoints():
    """Test FastAPI presence endpoints via TestClient."""
    client = TestClient(app)

    # 1. Heartbeat
    resp = client.post("/api/presence/heartbeat", json={"session_id": "client_tab_1"})
    assert resp.status_code == 200
    data = resp.json()
    assert "count" in data
    assert data["count"] >= 1
    assert data["status"] == "active"

    # 2. Get Count
    resp = client.get("/api/presence/count")
    assert resp.status_code == 200
    assert "count" in resp.json()

    # 3. Leave (JSON body)
    resp = client.post("/api/presence/leave", json={"session_id": "client_tab_1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "left"

    # 4. Leave with beacon plain string / raw bytes fallback
    resp = client.post(
        "/api/presence/leave",
        content='{"session_id": "client_tab_2"}',
        headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "left"

    # 5. Get Users requires authentication (401/403)
    resp = client.get("/api/presence/users")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_presence_get_live_users_in_memory():
    """Test detailed user metadata retrieval without database queries."""
    service = PresenceService()

    with patch("backend.services.presence.get_redis", new=AsyncMock(return_value=None)):
        await service.record_heartbeat("sess_admin", {
            "user_id": "u1",
            "user_name": "Dipak",
            "user_email": "admin@stockai.com",
            "role": "ADMIN",
            "path": "/chart",
            "device": "Desktop"
        })
        await service.record_heartbeat("sess_guest", {
            "user_name": "Guest 1234",
            "role": "GUEST",
            "path": "/pricing",
            "device": "Mobile"
        })

        res = await service.get_live_users()
        assert res["count"] == 2
        assert len(res["users"]) == 2
        names = [u["user_name"] for u in res["users"]]
        assert "Dipak" in names
        assert "Guest 1234" in names

