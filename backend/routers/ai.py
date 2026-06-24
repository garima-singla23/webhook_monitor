# routers/ai.py
# ─────────────────────────────────────────────
# API routes for AI features (Phase 4):
# - failure diagnoses (health checks + deliveries)
# - plain-English payload summaries
#
# Phase 7: scoped by ownership — diagnose-now in particular
# would otherwise let anyone burn YOUR Groq API quota by
# spamming diagnoses against endpoints they don't even own.
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from database import (
    get_endpoint,
    get_diagnoses_for_endpoint,
    get_webhook_event,
)
from services.ai_diagnosis import diagnose_failure
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


async def _get_owned_endpoint_or_404(endpoint_id: str, user: AuthUser) -> dict:
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint or endpoint.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.get("/endpoint/{endpoint_id}/diagnoses")
async def get_endpoint_diagnoses(
    endpoint_id: str,
    limit: int = 20,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get recent AI diagnoses for an endpoint — only if it
    belongs to the current user.

    Example: GET /api/ai/endpoint/abc123/diagnoses
    Authorization: Bearer <token>
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)
    diagnoses = await get_diagnoses_for_endpoint(endpoint_id, limit)

    return {
        "success": True,
        "endpoint_id": endpoint_id,
        "count": len(diagnoses),
        "diagnoses": diagnoses
    }


@router.get("/event/{event_id}/summary")
async def get_event_summary(
    event_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get the AI-generated plain-English summary for one event —
    only if it belongs to one of the current user's endpoints.

    Example: GET /api/ai/event/abc123/summary
    Authorization: Bearer <token>
    """
    event = await get_webhook_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Events don't carry user_id directly — check via their endpoint
    endpoint = await get_endpoint(event["endpoint_id"])
    if not endpoint or endpoint.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Event not found")

    return {
        "success": True,
        "event_id": event_id,
        "readable": event.get("readable"),
        "ai_summary": event.get("ai_summary"),
        "has_ai_summary": event.get("ai_summary") is not None
    }


@router.post("/diagnose-now")
async def diagnose_now(
    endpoint_id: str,
    source: str,
    status_code: int | None = None,
    response_time_ms: int | None = None,
    error_message: str = "Unknown error",
    user: AuthUser = Depends(get_current_user)
):
    """
    Manually trigger an AI diagnosis for testing purposes — only
    if the endpoint belongs to the current user. This is the route
    most worth locking down: without ownership checks, anyone could
    call this repeatedly against any endpoint_id and burn through
    your Groq API quota for free.

    Example:
    POST /api/ai/diagnose-now?endpoint_id=abc123&source=health_check
         &status_code=500&error_message=Connection refused
    Authorization: Bearer <token>
    """
    endpoint = await _get_owned_endpoint_or_404(endpoint_id, user)

    diagnosis = await diagnose_failure(
        endpoint_id=endpoint_id,
        source=source,
        source_id=None,
        failure_data={
            "source": source,
            "provider": endpoint.get("provider", "generic"),
            "status_code": status_code,
            "response_time_ms": response_time_ms,
            "error_message": error_message,
            "consecutive_failures": 3,
        }
    )

    return {
        "success": True,
        "diagnosis": diagnosis
    }