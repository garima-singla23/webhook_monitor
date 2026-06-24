# routers/dashboard.py
# ─────────────────────────────────────────────
# API routes for dashboard data
# Frontend calls these to populate dashboard
#
# Phase 7: this was the most serious pre-existing gap —
# get_dashboard_summary() previously called get_all_endpoints()
# with no user filter at all, meaning ANY logged-in user (or
# even an unauthenticated caller, since there was no auth check
# whatsoever) could see every other user's endpoints and events
# on the main dashboard. Fixed by requiring auth and scoping
# every query to the current user.
# ─────────────────────────────────────────────

from fastapi import APIRouter, Depends
from database import (
    get_all_endpoints,
    get_all_recent_events,
    get_event_stats,
)
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)


@router.get("/summary")
async def get_dashboard_summary(user: AuthUser = Depends(get_current_user)):
    """
    Get overall dashboard summary for the CURRENT USER only.
    Called when dashboard page loads.

    Returns:
    - total endpoints (this user's)
    - total events (this user's)
    - recent events (this user's)
    - per-endpoint stats (this user's)

    Example:
    GET /api/dashboard/summary
    Authorization: Bearer <token>
    """
    try:
        endpoints = await get_all_endpoints(user_id=user.id)
        recent_events = await get_all_recent_events(limit=20, user_id=user.id)

        endpoint_stats = []
        for ep in endpoints:
            stats = await get_event_stats(ep["id"])
            endpoint_stats.append({
                **ep,
                "stats": stats,
                "webhook_url": f"/webhook/{ep['id']}"
            })

        return {
            "success": True,
            "summary": {
                "total_endpoints": len(endpoints),
                "active_endpoints": sum(
                    1 for ep in endpoints
                    if ep.get("is_active", True)
                ),
                "total_events": sum(
                    s["stats"]["total"]
                    for s in endpoint_stats
                ),
            },
            "endpoints": endpoint_stats,
            "recent_events": recent_events
        }

    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return {
            "success": False,
            "error": "Could not load dashboard"
        }


@router.get("/events/recent")
async def get_recent_events(
    limit: int = 50,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get recent events across the current user's own endpoints only.

    Example:
    GET /api/dashboard/events/recent
    Authorization: Bearer <token>
    """
    events = await get_all_recent_events(limit=limit, user_id=user.id)
    return {
        "success": True,
        "count": len(events),
        "events": events
    }