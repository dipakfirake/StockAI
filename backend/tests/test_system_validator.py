"""Unit tests for Enterprise System Validator & Cybersecurity Threat Scanner."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.services.system_validator import system_validator


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
    """Verify public status endpoint and admin authentication guard."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Public status
        res_status = await client.get("/api/validator/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "overall_status" in data

        # Public history
        res_hist = await client.get("/api/validator/history")
        assert res_hist.status_code == 200
        assert isinstance(res_hist.json(), list)

        # Protected run endpoint (without auth token should return 401/403)
        res_unauth = await client.post("/api/validator/run")
        assert res_unauth.status_code in (401, 403)
