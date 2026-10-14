"""Unit tests for Enterprise System Validator & Cybersecurity Threat Scanner."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.services.system_validator import system_validator
from backend.models.user import User


@pytest.mark.asyncio
async def test_system_validator_suite_execution():
    """Verify system validator executes full 10-point suite with 0 failures."""
    report = await system_validator.run_all_tests(trigger_source="TEST_RUNNER")
    assert report is not None
    assert "suite_id" in report
    assert report["total_tests"] == 10
    assert report["failed_tests"] == 0
    assert report["passed_tests"] >= 8
    assert len(report["results"]) == 10


@pytest.mark.asyncio
async def test_system_validator_single_tests():
    """Verify individual test dispatching by ID."""
    res_sec = await system_validator.run_single_test("SEC-001")
    assert res_sec["test_id"] == "SEC-001"
    assert res_sec["status"] == "PASSED"

    res_rbac = await system_validator.run_single_test("SEC-004")
    assert res_rbac["test_id"] == "SEC-004"
    assert res_rbac["status"] == "PASSED"


@pytest.mark.asyncio
async def test_validator_api_public_and_protected_routes():
    """Verify validator routes are guarded by admin authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Unauthenticated access must be rejected with 401 Unauthorized
        res_status = await client.get("/api/validator/status")
        assert res_status.status_code == 401

        res_hist = await client.get("/api/validator/history")
        assert res_hist.status_code == 401

        res_unauth = await client.post("/api/validator/run")
        assert res_unauth.status_code in (401, 403)

        # Authenticated Admin access via dependency override
        admin_mock = User(
            email="admin_auditor@test.com",
            name="Admin Auditor",
            hashed_password="mock_hashed_pw",
            is_admin=True,
            subscription_tier="PRO",
            is_active=True,
        )
        from backend.api.admin import require_admin
        app.dependency_overrides[require_admin] = lambda: admin_mock
        try:
            res_admin_status = await client.get("/api/validator/status")
            assert res_admin_status.status_code == 200
            data = res_admin_status.json()
            assert "overall_status" in data

            res_admin_hist = await client.get("/api/validator/history")
            assert res_admin_hist.status_code == 200
            assert isinstance(res_admin_hist.json(), list)
        finally:
            app.dependency_overrides.pop(require_admin, None)
