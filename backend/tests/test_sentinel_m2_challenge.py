"""Empirical challenge tests for Sentinel Admin Authorization & RBAC defenses."""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from unittest.mock import MagicMock

from backend.main import app
from backend.core.auth import get_current_user
from backend.models.user import User


@pytest.mark.asyncio
async def test_sentinel_all_five_endpoints_reject_non_admin_token():
    """Adversarially challenge that all 5 /api/sentinel/* endpoints strictly reject non-admin users with 403 Forbidden."""
    # Create mock regular (non-admin) user
    regular_user = MagicMock(spec=User)
    regular_user.id = uuid.uuid4()
    regular_user.email = "attacker_nonadmin@stockai.com"
    regular_user.is_admin = False
    regular_user.subscription_tier = "FREE"

    # Override get_current_user to simulate non-admin authenticated session
    app.dependency_overrides[get_current_user] = lambda: regular_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. GET /api/sentinel/status
            res_status = await client.get("/api/sentinel/status")
            assert res_status.status_code == 403, (
                f"GET /api/sentinel/status did not return 403 for non-admin! "
                f"Got status={res_status.status_code}, body={res_status.text}"
            )
            assert "Administrative privileges required" in res_status.text

            # 2. GET /api/sentinel/incidents
            res_incidents = await client.get("/api/sentinel/incidents")
            assert res_incidents.status_code == 403, (
                f"GET /api/sentinel/incidents did not return 403 for non-admin! "
                f"Got status={res_incidents.status_code}, body={res_incidents.text}"
            )
            assert "Administrative privileges required" in res_incidents.text

            # 3. POST /api/sentinel/audit-now
            res_audit = await client.post("/api/sentinel/audit-now")
            assert res_audit.status_code == 403, (
                f"POST /api/sentinel/audit-now did not return 403 for non-admin! "
                f"Got status={res_audit.status_code}, body={res_audit.text}"
            )
            assert "Administrative privileges required" in res_audit.text

            # 4. POST /api/sentinel/resolve
            res_resolve = await client.post(
                "/api/sentinel/resolve",
                json={"incident_id": str(uuid.uuid4())},
            )
            assert res_resolve.status_code == 403, (
                f"POST /api/sentinel/resolve did not return 403 for non-admin! "
                f"Got status={res_resolve.status_code}, body={res_resolve.text}"
            )
            assert "Administrative privileges required" in res_resolve.text

            # 5. POST /api/sentinel/resolve/{incident_id}
            fake_id = str(uuid.uuid4())
            res_resolve_path = await client.post(f"/api/sentinel/resolve/{fake_id}")
            assert res_resolve_path.status_code == 403, (
                f"POST /api/sentinel/resolve/{{id}} did not return 403 for non-admin! "
                f"Got status={res_resolve_path.status_code}, body={res_resolve_path.text}"
            )
            assert "Administrative privileges required" in res_resolve_path.text

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_sentinel_endpoints_allow_verified_admin():
    """Verify that a legitimate admin user is authorized across Sentinel endpoints."""
    admin_user = MagicMock(spec=User)
    admin_user.id = uuid.uuid4()
    admin_user.email = "lead_admin@stockai.com"
    admin_user.is_admin = True
    admin_user.subscription_tier = "PRO"

    app.dependency_overrides[get_current_user] = lambda: admin_user

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res_status = await client.get("/api/sentinel/status")
            assert res_status.status_code == 200, f"Admin status failed: {res_status.text}"
            data = res_status.json()
            assert "overall_status" in data
            assert "subsystems" in data

            res_incidents = await client.get("/api/sentinel/incidents")
            assert res_incidents.status_code == 200, f"Admin incidents failed: {res_incidents.text}"
            incidents_data = res_incidents.json()
            assert "open_count" in incidents_data
            assert "incidents" in incidents_data

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_sentinel_endpoints_reject_unauthenticated():
    """Verify unauthenticated requests without authorization header are rejected."""
    # Ensure no auth overrides
    app.dependency_overrides.pop(get_current_user, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for path in ["/api/sentinel/status", "/api/sentinel/incidents"]:
            res = await client.get(path)
            assert res.status_code in (401, 403), f"Unauthenticated {path} got {res.status_code}"

        for path in ["/api/sentinel/audit-now", "/api/sentinel/resolve", "/api/sentinel/resolve/abc"]:
            res = await client.post(path, json={"incident_id": "test"} if "resolve" in path else None)
            assert res.status_code in (401, 403), f"Unauthenticated {path} got {res.status_code}"
