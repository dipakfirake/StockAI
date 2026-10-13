"""Unit tests for Enterprise Three-Tier Testing Matrix: Black Box, White Box, and Grey Box."""

import pytest
from backend.services.request_validator import request_validator


@pytest.mark.asyncio
async def test_black_box_paradigm_probes():
    """Verify Black Box testing: external HTTP contracts, Pydantic 422 schemas, 404, 405, and CORS preflights."""
    bb_tests = await request_validator.test_black_box_suite()
    assert len(bb_tests) >= 5
    for t in bb_tests:
        assert t.paradigm == "BLACK_BOX"
        assert t.passed is True, f"Failed Black Box probe: {t.test_id} on {t.endpoint} (status {t.actual_status})"


@pytest.mark.asyncio
async def test_grey_box_paradigm_probes():
    """Verify Grey Box testing: SQLi/XSS fuzzing, rate limiter burst bounds, unauthenticated RBAC guards."""
    gb_tests = await request_validator.test_grey_box_suite()
    assert len(gb_tests) >= 4
    for t in gb_tests:
        assert t.paradigm == "GREY_BOX"
        assert t.passed is True, f"Failed Grey Box probe: {t.test_id} on {t.endpoint} (status {t.actual_status})"


@pytest.mark.asyncio
async def test_white_box_paradigm_probes():
    """Verify White Box testing: indicator numerical sanity, division-by-zero guards, and tensor dimensions."""
    wb_tests = await request_validator.test_white_box_suite()
    assert len(wb_tests) >= 2
    for t in wb_tests:
        assert t.paradigm == "WHITE_BOX"
        assert t.passed is True, f"Failed White Box probe: {t.test_id} (status {t.actual_status})"


@pytest.mark.asyncio
async def test_master_three_tier_suite_execution():
    """Verify master runner executes all 3 paradigms with 0 failures."""
    res = await request_validator.run_all_paradigms()
    assert res["status"] == "PASSED"
    assert res["failed_probes"] == 0
    assert res["passed_probes"] >= 12
    assert "black_box" in res["paradigms"]
    assert "grey_box" in res["paradigms"]
    assert "white_box" in res["paradigms"]
