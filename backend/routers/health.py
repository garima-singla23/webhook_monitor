# routers/health.py
# ─────────────────────────────────────────────
# API routes for health check data
# Frontend calls these to show health status
#
# Phase 7: every route now requires authentication and
# is scoped to the logged-in user's own endpoints — this
# was a real gap before today: any of these routes could
# previously be called with any endpoint_id, regardless
# of who actually owned it.
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from database import (
    get_endpoint,
    get_health_checks,
    get_latest_health_check,
    get_uptime_percentage,
    get_average_response_time,
    get_consecutive_failure_count,
    get_all_endpoints,
    supabase
)
from services.health_checker import check_single_endpoint
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/health",
    tags=["health"]
)


async def _get_owned_endpoint_or_404(endpoint_id: str, user: AuthUser) -> dict:
    """Same ownership check as routers/endpoints.py — kept
    consistent across every router rather than each file
    rolling its own slightly different version."""
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint or endpoint.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.get("/{endpoint_id}")
async def get_endpoint_health(
    endpoint_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get complete health status for one endpoint — only if
    it belongs to the current user.

    Example:
    GET /api/health/abc123
    Authorization: Bearer <token>
    """
    endpoint = await _get_owned_endpoint_or_404(endpoint_id, user)

    latest = await get_latest_health_check(endpoint_id)
    uptime = await get_uptime_percentage(endpoint_id)
    avg_response = await get_average_response_time(endpoint_id)
    failures = await get_consecutive_failure_count(endpoint_id)
    recent_checks = await get_health_checks(endpoint_id, limit=20)

    cdn_info = None
    if latest and latest.get("cdn_detected"):
        cdn_info = {
            "detected": True,
            "provider": latest.get("cdn_provider")
        }

    return {
        "success": True,
        "endpoint": endpoint,
        "health": {
            "current_status": latest.get("status", "unknown") if latest else "never_checked",
            "uptime_percentage": uptime,
            "avg_response_ms": avg_response,
            "consecutive_failures": failures,
            "last_checked": latest.get("checked_at") if latest else None,
            "last_response_ms": latest.get("response_time_ms") if latest else None,
            "last_status_code": latest.get("status_code") if latest else None,
            "last_error": latest.get("error_message") if latest else None,
        },
        "cdn": cdn_info,
        "recent_checks": recent_checks
    }


@router.post("/{endpoint_id}/check-now")
async def trigger_manual_check(
    endpoint_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Manually trigger a health check right now — only if the
    endpoint belongs to the current user. Don't wait for the
    60s scheduler.

    Example:
    POST /api/health/abc123/check-now
    Authorization: Bearer <token>
    """
    endpoint = await _get_owned_endpoint_or_404(endpoint_id, user)

    logger.info(
        f"Manual health check triggered for: {endpoint['name']} "
        f"(user {user.id})"
    )

    result = await check_single_endpoint(endpoint)

    return {
        "success": True,
        "message": "Health check completed",
        "result": result
    }


@router.get("/")
async def get_all_health_status(user: AuthUser = Depends(get_current_user)):
    """
    Get health status for ALL of the current user's endpoints.
    Used for the dashboard overview.

    Before Phase 7 this queried every active endpoint in the
    ENTIRE system regardless of owner — that was the actual
    security hole this fix closes.

    Example:
    GET /api/health/
    Authorization: Bearer <token>
    """
    try:
        # Scoped by user_id now, not a blanket query across everyone
        endpoints = await get_all_endpoints(user_id=user.id)
        endpoints = [ep for ep in endpoints if ep.get("is_active", True)]

        health_summary = []

        for ep in endpoints:
            latest = await get_latest_health_check(ep["id"])
            uptime = await get_uptime_percentage(ep["id"])

            health_summary.append({
                "endpoint_id": ep["id"],
                "name": ep["name"],
                "provider": ep["provider"],
                "url": ep["url"],
                "status": latest.get("status", "unknown") if latest else "never_checked",
                "uptime_percentage": uptime,
                "last_response_ms": latest.get("response_time_ms") if latest else None,
                "last_checked": latest.get("checked_at") if latest else None,
                "consecutive_failures": ep.get("consecutive_failures", 0),
                "cdn_detected": latest.get("cdn_detected", False) if latest else False,
                "cdn_provider": latest.get("cdn_provider") if latest else None,
            })

        total = len(health_summary)
        up_count = sum(1 for h in health_summary if h["status"] == "up")
        down_count = sum(1 for h in health_summary if h["status"] == "down")

        return {
            "success": True,
            "summary": {
                "total": total,
                "up": up_count,
                "down": down_count,
                "degraded": total - up_count - down_count
            },
            "endpoints": health_summary
        }

    except Exception as e:
        logger.error(f"Error getting health status: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get health status"
        )


@router.get("/{endpoint_id}/alerts")
async def get_endpoint_alerts(
    endpoint_id: str,
    limit: int = 10,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get recent alerts for an endpoint — only if it belongs
    to the current user.

    Example:
    GET /api/health/abc123/alerts
    Authorization: Bearer <token>
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)

    try:
        result = supabase.table("alerts_log")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("sent_at", desc=True)\
            .limit(limit)\
            .execute()

        return {
            "success": True,
            "alerts": result.data
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        return {"success": False, "alerts": []}