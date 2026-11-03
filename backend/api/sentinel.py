"""API Router for 24/7 Sentinel System Surveillance & Bug Ledger."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from backend.services.sentinel import sentinel_service
from backend.models.user import User
from backend.api.admin import require_admin
from backend.core.auth import get_current_user
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/sentinel", tags=["Sentinel 24/7 Watchdog"], dependencies=[Depends(require_admin)])


class ResolveIncidentSchema(BaseModel):
    incident_id: str = Field(description="UUID of the incident to mark resolved")


@router.get("/status")
async def get_sentinel_status(
    current_user: User = Depends(require_admin),
):
    """
    Get 24/7 surveillance health status (Strictly Admin only).
    """
    return sentinel_service.get_health_summary()


@router.get("/incidents")
async def get_sentinel_incidents(
    current_user: User = Depends(require_admin),
):
    """Get recent bug and threat incidents detected by Sentinel (Admin only)."""
    summary = sentinel_service.get_health_summary()
    return {
        "open_count": summary["open_incident_count"],
        "incidents": summary["recent_incidents"],
    }


@router.post("/audit-now")
async def run_immediate_audit(
    current_user: User = Depends(require_admin),
):
    """Trigger an immediate full-stack diagnostic audit across all subsystems (Admin only)."""
    log_security_event(
        event_type="SENTINEL_MANUAL_AUDIT",
        severity="INFO",
        user_id=str(current_user.id),
        details={"triggered_by": current_user.email},
    )
    summary = await sentinel_service.run_full_system_audit()
    return summary


@router.post("/resolve")
async def resolve_incident(
    req: ResolveIncidentSchema,
    current_user: User = Depends(require_admin),
):
    """Mark an incident as investigated and resolved (Admin only)."""
    success = await sentinel_service.resolve_incident(
        incident_id=req.incident_id,
        resolved_by=current_user.email,
    )
    log_security_event(
        event_type="SENTINEL_INCIDENT_RESOLVED",
        severity="INFO",
        user_id=str(current_user.id),
        details={"incident_id": req.incident_id, "resolved_by": current_user.email, "success": success},
    )
    return {
        "success": success,
        "incident_id": req.incident_id,
        "status": "RESOLVED" if success else "NOT_FOUND",
    }


@router.post("/resolve/{incident_id}")
async def resolve_incident_by_path(
    incident_id: str,
    current_user: User = Depends(require_admin),
):
    """Mark an incident as investigated and resolved via path parameter (Admin only)."""
    success = await sentinel_service.resolve_incident(
        incident_id=incident_id,
        resolved_by=current_user.email,
    )
    log_security_event(
        event_type="SENTINEL_INCIDENT_RESOLVED",
        severity="INFO",
        user_id=str(current_user.id),
        details={"incident_id": incident_id, "resolved_by": current_user.email, "success": success},
    )
    return {
        "success": success,
        "incident_id": incident_id,
        "status": "RESOLVED" if success else "NOT_FOUND",
    }
