"""API Router for 24/7 Sentinel System Surveillance & Bug Ledger."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from backend.services.sentinel import sentinel_service
from backend.models.user import User
from backend.api.auth import get_current_user

router = APIRouter(prefix="/sentinel", tags=["Sentinel 24/7 Watchdog"])


class ResolveIncidentSchema(BaseModel):
    incident_id: str = Field(description="UUID of the incident to mark resolved")


@router.get("/status")
async def get_sentinel_status():
    """Get real-time 24/7 surveillance health score, component latencies, and open bug counts."""
    return sentinel_service.get_health_summary()


@router.get("/incidents")
async def get_sentinel_incidents():
    """Get recent bug and threat incidents detected by Sentinel."""
    summary = sentinel_service.get_health_summary()
    return {
        "open_count": summary["open_incident_count"],
        "incidents": summary["recent_incidents"],
    }


@router.post("/audit-now")
async def run_immediate_audit(current_user: User = Depends(get_current_user)):
    """Trigger an immediate full-stack diagnostic audit across all subsystems."""
    summary = await sentinel_service.run_full_system_audit()
    return {
        "message": "Full-stack diagnostic audit completed successfully",
        "result": summary,
    }


@router.post("/resolve")
async def resolve_incident(
    req: ResolveIncidentSchema,
    current_user: User = Depends(get_current_user),
):
    """Mark an incident as investigated and resolved."""
    success = await sentinel_service.resolve_incident(
        incident_id=req.incident_id,
        resolved_by=current_user.email,
    )
    return {
        "success": success,
        "incident_id": req.incident_id,
        "status": "RESOLVED" if success else "NOT_FOUND",
    }
