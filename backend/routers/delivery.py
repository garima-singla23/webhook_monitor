# routers/delivery.py
# ─────────────────────────────────────────────
# API routes for delivery tracking & retry queue
# Phase 3, scoped by ownership in Phase 7
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from database import (
    get_endpoint,
    get_webhook_event,
    get_delivery_attempts,
    get_delivery_stats,
)
from services.retry_queue import get_queue_status, attempt_delivery
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


async def _get_owned_event_or_404(event_id: str, user: AuthUser) -> tuple[dict, dict]:
    """
    Webhook events don't have a user_id of their own — ownership
    is determined through the endpoint they belong to, the same
    join-through-ownership pattern used everywhere else in Phase 7.

    Returns (event, endpoint) since callers usually need both.
    """
    event = await get_webhook_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    endpoint = await get_endpoint(event["endpoint_id"])
    if not endpoint or endpoint.get("user_id") != user.id:
        # Same event_id exists, but belongs to someone else —
        # still a 404, not a 403, to avoid confirming the ID is real.
        raise HTTPException(status_code=404, detail="Event not found")

    return event, endpoint


@router.get("/queue-status")
async def queue_status(user: AuthUser = Depends(get_current_user)):
    """
    Current Redis retry queue status — global, not per-user,
    since the queue itself isn't partitioned by owner. Still
    requires being logged in, just not ownership of anything
    specific.

    Example: GET /api/delivery/queue-status
    Authorization: Bearer <token>
    """
    status = get_queue_status()
    return {"success": True, "queue": status}


@router.get("/event/{event_id}")
async def event_delivery_detail(
    event_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Full delivery history for one webhook event — only if
    it belongs to one of the current user's own endpoints.

    Example: GET /api/delivery/event/abc123
    Authorization: Bearer <token>
    """
    event, _ = await _get_owned_event_or_404(event_id, user)
    attempts = await get_delivery_attempts(event_id)

    return {
        "success": True,
        "event": event,
        "attempts": attempts,
        "attempt_count": len(attempts)
    }


@router.get("/endpoint/{endpoint_id}/stats")
async def endpoint_delivery_stats(
    endpoint_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Delivery health summary for an endpoint — only if it
    belongs to the current user.

    Example: GET /api/delivery/endpoint/abc123/stats
    Authorization: Bearer <token>
    """
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint or endpoint.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    stats = await get_delivery_stats(endpoint_id)

    return {
        "success": True,
        "endpoint_id": endpoint_id,
        "stats": stats
    }


@router.post("/event/{event_id}/retry-now")
async def retry_event_now(
    event_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Manually force an immediate retry attempt for one event —
    only if it belongs to the current user. Without this check,
    anyone could trigger retries against ANY endpoint URL in the
    system just by guessing or enumerating event IDs.

    Example: POST /api/delivery/event/abc123/retry-now
    Authorization: Bearer <token>
    """
    event, endpoint = await _get_owned_event_or_404(event_id, user)

    await attempt_delivery(
        event_id=event_id,
        endpoint_id=event["endpoint_id"],
        endpoint_url=endpoint["url"],
        payload=event.get("payload", {}),
        retry_count=event.get("retry_count", 0)
    )

    updated_event = await get_webhook_event(event_id)

    return {
        "success": True,
        "message": "Retry attempt completed",
        "event": updated_event
    }