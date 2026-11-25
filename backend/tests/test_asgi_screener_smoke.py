import asyncio
import os
import time
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.core.auth import get_current_user, get_current_user_fast

def create_mock_user():
    user = MagicMock()
    user.id = 1
    user.email = "admin@test.com"
    user.is_active = True
    user.is_superuser = True
    return user

@pytest.mark.asyncio
async def test_fastapi_asgi_screener_scan_and_poll():
    mock_u = create_mock_user()
    app.dependency_overrides[get_current_user] = lambda: mock_u
    app.dependency_overrides[get_current_user_fast] = lambda: mock_u
    
    with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": ""}):
        with patch("backend.tasks.market_tasks.run_sector_screener_task.apply_async") as mock_apply:
            mock_apply.return_value = MagicMock(id="celery-mock-id")
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. Health check
                r_health = await client.get("/health/live")
                assert r_health.status_code == 200

                # 2. Async Screener Scan Start
                r_scan = await client.post("/api/market/screener/scan", params={"sector": "NIFTY_50"})
                data_scan = r_scan.json()
                job_id = data_scan.get("job_id")
                assert r_scan.status_code in (200, 202), f"Expected 200 or 202, got {r_scan.status_code}: {data_scan}"
                assert job_id is not None
                assert mock_apply.called, "Celery apply_async should be invoked"

                # 3. Async Screener Job Poll
                r_poll = await client.get(f"/api/market/screener/scan/{job_id}")
                data_poll = r_poll.json()
                assert r_poll.status_code == 200
                assert "cached_data" not in data_poll, "Running poll should strip cached_data to avoid payload bloat"
                assert data_poll.get("job_id") == job_id
