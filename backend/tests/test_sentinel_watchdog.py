"""Unit tests for 24/7 Autonomous Sentinel & Threat Watchdog."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.services.sentinel import sentinel_service


@pytest.mark.asyncio
async def test_sentinel_health_summary():
    """Verify Sentinel generates a structured aggregate health score."""
    summary = sentinel_service.get_health_summary()
    assert "health_score" in summary
    assert "overall_status" in summary
    assert "subsystems" in summary
    assert "database" in summary["subsystems"]
    assert "redis" in summary["subsystems"]
    assert "celery" in summary["subsystems"]
    assert "broker_api" in summary["subsystems"]
    assert "security" in summary["subsystems"]
    assert 0 <= summary["health_score"] <= 100


@pytest.mark.asyncio
async def test_sentinel_full_system_audit_run():
    """Verify Sentinel can execute a full-stack audit across all subsystems."""
    result = await sentinel_service.run_full_system_audit()
    assert result["audit_runs"] >= 0
    assert result["overall_status"] in ["OPERATIONAL", "DEGRADED_PERFORMANCE", "CRITICAL_OUTAGE"]


@pytest.mark.asyncio
async def test_sentinel_api_endpoints():
    """Verify public and admin Sentinel API endpoints."""
    from backend.core.auth import get_current_user
    from backend.api.admin import require_admin
    from backend.models.user import User

    mock_admin = MagicMock(spec=User, id="admin-uuid", email="admin@stockai.com", is_admin=True)
    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[require_admin] = lambda: mock_admin

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Get status
            res1 = await client.get("/api/sentinel/status")
            assert res1.status_code == 200
            data1 = res1.json()
            assert "health_score" in data1
            assert "subsystems" in data1

            # 2. Get incidents list
            res2 = await client.get("/api/sentinel/incidents")
            assert res2.status_code == 200
            assert "incidents" in res2.json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_sentinel_incident_deduplication_and_resolution():
    """Verify Sentinel deduplicates repeated errors and marks them resolved."""
    # Record synthetic incident
    await sentinel_service._record_incident(
        subsystem="API_ENDPOINT",
        severity="WARNING",
        title="Synthetic Test Anomaly",
        detail="Testing deduplication and incident ledger",
        suggested_action="No action needed - automated test",
    )

    incidents = sentinel_service.get_health_summary()["recent_incidents"]
    match = next((i for i in incidents if i["title"] == "Synthetic Test Anomaly"), None)
    assert match is not None
    incident_id = match["id"]

    # Record second occurrence - should increment occurrence_count
    await sentinel_service._record_incident(
        subsystem="API_ENDPOINT",
        severity="WARNING",
        title="Synthetic Test Anomaly",
        detail="Testing deduplication and incident ledger",
    )

    incidents_updated = sentinel_service.get_health_summary()["recent_incidents"]
    match_updated = next((i for i in incidents_updated if i["id"] == incident_id), None)
    assert match_updated is not None
    assert match_updated["occurrence_count"] >= 2

    # Resolve incident
    resolved = await sentinel_service.resolve_incident(incident_id, resolved_by="test_runner")
    assert resolved is True
    match_resolved = next((i for i in sentinel_service.get_health_summary()["recent_incidents"] if i["id"] == incident_id), None)
    assert match_resolved["status"] == "RESOLVED"
