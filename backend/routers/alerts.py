# routers/alerts.py
# ─────────────────────────────────────────────
# API routes for alert history (Phase 2's alerts_log)
# and delivery tracking (Phase 6's alert_deliveries).
#
# Phase 7: scoped by ownership. update_alert_preferences()
# in particular was the most concerning gap here — without
# this fix, anyone could silently disable another user's
# Slack/email alerts on any endpoint they didn't even own,
# which is actively harmful (someone could go down without
# ever being notified), not just a data leak.
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from database import get_endpoint, get_alert_deliveries, supabase
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


async def _get_owned_endpoint_or_404(endpoint_id: str, user: AuthUser) -> dict:
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint or endpoint.get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.get("/endpoint/{endpoint_id}")
async def get_endpoint_alerts(
    endpoint_id: str,
    limit: int = 20,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get recent alert conditions (down/recovered) for an
    endpoint — only if it belongs to the current user.

    Example: GET /api/alerts/endpoint/abc123
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
        alerts = result.data
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        alerts = []

    return {
        "success": True,
        "endpoint_id": endpoint_id,
        "count": len(alerts),
        "alerts": alerts
    }


@router.get("/endpoint/{endpoint_id}/deliveries")
async def get_endpoint_alert_deliveries(
    endpoint_id: str,
    limit: int = 20,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get the delivery audit trail — did the Slack/email
    notification for each alert actually go through?

    Example: GET /api/alerts/endpoint/abc123/deliveries
    Authorization: Bearer <token>
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)

    deliveries = await get_alert_deliveries(endpoint_id, limit)

    slack_sent = sum(1 for d in deliveries if d["channel"] == "slack" and d["success"])
    slack_failed = sum(1 for d in deliveries if d["channel"] == "slack" and not d["success"])
    email_sent = sum(1 for d in deliveries if d["channel"] == "email" and d["success"])
    email_failed = sum(1 for d in deliveries if d["channel"] == "email" and not d["success"])

    return {
        "success": True,
        "endpoint_id": endpoint_id,
        "count": len(deliveries),
        "deliveries": deliveries,
        "summary": {
            "slack_sent": slack_sent,
            "slack_failed": slack_failed,
            "email_sent": email_sent,
            "email_failed": email_failed,
        }
    }


@router.patch("/endpoint/{endpoint_id}/preferences")
async def update_alert_preferences(
    endpoint_id: str,
    slack_alerts_enabled: bool | None = None,
    email_alerts_enabled: bool | None = None,
    user: AuthUser = Depends(get_current_user)
):
    """
    Toggle Slack/email alerts on or off for a specific endpoint —
    only if it belongs to the current user. This was the most
    important route to lock down in this entire router: without
    ownership enforcement, anyone could silently turn off another
    user's alerts on any endpoint.

    Example: PATCH /api/alerts/endpoint/abc123/preferences?slack_alerts_enabled=false
    Authorization: Bearer <token>
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)

    update_data = {}
    if slack_alerts_enabled is not None:
        update_data["slack_alerts_enabled"] = slack_alerts_enabled
    if email_alerts_enabled is not None:
        update_data["email_alerts_enabled"] = email_alerts_enabled

    if not update_data:
        raise HTTPException(status_code=400, detail="No preferences provided")

    try:
        result = supabase.table("endpoints")\
            .update(update_data)\
            .eq("id", endpoint_id)\
            .execute()
        updated = result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error updating alert preferences: {e}")
        raise HTTPException(status_code=500, detail="Failed to update preferences")

    return {
        "success": True,
        "endpoint": updated
    }