"""API Router for Enterprise System Validator & Cybersecurity Threat Scanner."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List

from backend.services.system_validator import system_validator
from backend.models.user import User
from backend.api.admin import require_admin
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/validator", tags=["System Validator & Cybersecurity Scanner"])


@router.get("/status")
async def get_validator_status() -> Dict[str, Any]:
    """Get the most recent system validation & cybersecurity audit report."""
    return system_validator.get_latest_report()


@router.get("/history")
async def get_validator_history() -> List[Dict[str, Any]]:
    """Get chronological history of the last 20 validation suite runs."""
    return system_validator.get_history()


@router.post("/run")
async def trigger_full_validation_suite(
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Trigger an interactive on-demand full system & cybersecurity validation sweep."""
    log_security_event(
        event_type="SYSTEM_VALIDATOR_SUITE_RUN",
        severity="INFO",
        user_id=str(current_user.id),
        details={"triggered_by": current_user.email, "trigger": "MANUAL_ADMIN"},
    )
    report = await system_validator.run_all_tests(trigger_source=f"ADMIN:{current_user.email}")
    return report


@router.post("/run/{test_id}")
async def trigger_single_test(
    test_id: str,
    current_user: User = Depends(require_admin),
) -> Dict[str, Any]:
    """Trigger an individual targeted system or cybersecurity test."""
    res = await system_validator.run_single_test(test_id)
    return res
