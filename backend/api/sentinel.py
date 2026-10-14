"""API Router for 24/7 Sentinel System Surveillance & Bug Ledger."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from backend.services.sentinel import sentinel_service
from backend.models.user import User
from backend.api.admin import require_admin
from backend.core.auth import get_current_user
from backend.core.audit_logger import log_security_event

router = APIRouter(prefix="/sentinel", tags=["Sentinel 24/7 Watchdog"])


class ResolveIncidentSchema(BaseModel):
    incident_id: str = Field(description="UUID of the incident to mark resolved")


@router.get("/status")
async def get_sentinel_status(
    current_user: User = Depends(get_current_user),
):
    """
    Get 24/7 surveillance health status.
    Admins receive full diagnostic breakdown; standard users receive sanitized summary.
    """
    is_admin = bool(current_user.is_admin or current_user.email.lower().strip() == "admin@stockai.com")
    summary = sentinel_service.get_health_summary()
    if is_admin:
        return summary
    return {
        "overall_health_score": summary.get("overall_health_score", 100.0),
        "overall_status": summary.get("overall_status", "NORMAL"),
        "open_incident_count": summary.get("open_incident_count", 0),
        "monitoring_active": summary.get("monitoring_active", True),
    }


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
