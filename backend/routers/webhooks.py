# routers/webhooks.py
# ─────────────────────────────────────────────
# Receives incoming webhook events
# This is the URL developers point their
# Razorpay/Stripe/GitHub webhooks to
# ─────────────────────────────────────────────

from fastapi import APIRouter, Request, HTTPException
from database import (
    get_endpoint,
    save_webhook_event,
    get_events_for_endpoint
)
from providers import get_provider
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/{endpoint_id}")
async def receive_webhook(
    endpoint_id: str,
    request: Request
):
    """
    Receive a webhook from any provider.

    Developers point their webhooks here:
    https://yourapp.com/webhook/{endpoint_id}

    CRITICAL RULES:
    1. Always return 200 immediately
    2. Never make providers wait
    3. Log everything even if processing fails
    """

    received_at = time.time()

    # ── Step 1: Validate endpoint exists ──
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint:
        # Return 404 so provider knows URL is wrong
        raise HTTPException(
            status_code=404,
            detail="Webhook endpoint not registered"
        )

    if not endpoint.get("is_active", True):
        # Endpoint is paused
        return {"status": "paused"}

    # ── Step 2: Get raw payload ──
    try:
        payload = await request.json()
    except Exception:
        # Even if JSON is invalid, save what we got
        payload = {}

    # ── Step 3: Get headers ──
    headers = dict(request.headers)

    # ── Step 4: Parse with correct provider ──
    provider_name = endpoint.get("provider", "generic")
    provider = get_provider(provider_name)
    parsed = provider.safe_parse(payload)

    # ── Step 5: Save to database ──
    try:
        event = await save_webhook_event({
            "endpoint_id": endpoint_id,
            "provider": provider_name,
            "event_type": parsed.get("event_type"),
            "payload": payload,
            "status": "received",
            "received_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(received_at)
            ),
            "readable": parsed.get("readable"),
            "metadata": parsed.get("metadata", {})
        })

        logger.info(
            f"Webhook received: {parsed.get('event_type')} "
            f"for endpoint {endpoint_id}"
        )

    except Exception as e:
        # Log error but STILL return 200
        # Never let database errors cause webhook loss
        logger.error(f"Failed to save webhook: {e}")

    # ── Step 6: ALWAYS return 200 immediately ──
    # This is critical — providers retry if they
    # don't get 200 quickly, causing duplicates
    return {
        "status": "received",
        "event_type": parsed.get("event_type"),
        "message": parsed.get("readable")
    }


@router.get("/webhook/{endpoint_id}/events")
async def get_webhook_events(
    endpoint_id: str,
    limit: int = 20
):
    """
    Get recent events for a webhook endpoint.

    Example:
    GET /webhook/abc123/events?limit=10
    """
    endpoint = await get_endpoint(endpoint_id)
    if not endpoint:
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found"
        )

    events = await get_events_for_endpoint(
        endpoint_id, limit
    )

    return {
        "success": True,
        "endpoint": endpoint,
        "count": len(events),
        "events": events
    }