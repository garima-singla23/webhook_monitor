# routers/dashboard.py
# ─────────────────────────────────────────────
# API routes for dashboard data
# Frontend calls these to populate dashboard
# ─────────────────────────────────────────────

from fastapi import APIRouter
from database import (
    get_all_endpoints,
    get_all_recent_events,
    get_event_stats,
    supabase
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"]
)


@router.get("/summary")
async def get_dashboard_summary():
    """
    Get overall dashboard summary.
    Called when dashboard page loads.

    Returns:
    - total endpoints
    - total events today
    - recent events
    - per-endpoint stats
    """
    try:
        endpoints = await get_all_endpoints()
        recent_events = await get_all_recent_events(limit=20)

        # Get stats for each endpoint
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
async def get_recent_events(limit: int = 50):
    """Get recent events across all endpoints"""
    events = await get_all_recent_events(limit)
    return {
        "success": True,
        "count": len(events),
        "events": events
    }