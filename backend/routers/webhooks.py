# routers/webhooks.py
# ─────────────────────────────────────────────
# Receives incoming webhook events
# This is the URL developers point their
# Razorpay/Stripe/GitHub webhooks to
# ─────────────────────────────────────────────

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from database import (
    get_endpoint,
    save_webhook_event,
    get_events_for_endpoint
)
from providers import get_provider
from services.retry_queue import attempt_delivery
from services.ai_explainer import explain_payload
from websocket.manager import broadcast
import time
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])


@router.post("/webhook/{endpoint_id}")
async def receive_webhook(
    endpoint_id: str,
    request: Request,
    background_tasks: BackgroundTasks
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
    event = None
    try:
        event = await save_webhook_event({
            "endpoint_id": endpoint_id,
            "provider": provider_name,
            "event_type": parsed.get("event_type"),
            "payload": payload,
            "status": "received",
            "delivery_status": "pending",
            "retry_count": 0,
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

    # ── Step 5b: Broadcast to live dashboard (Phase 5) ──
    # Fires the instant the event is saved — before delivery
    # attempts or AI processing even start, so the dashboard
    # shows "received" immediately and updates again later
    # when delivery/AI results come in via their own broadcasts.
    if event:
        await broadcast("webhook_received", {
            "event_id": event["id"],
            "endpoint_id": endpoint_id,
            "endpoint_name": endpoint.get("name"),
            "provider": provider_name,
            "event_type": parsed.get("event_type"),
            "readable": parsed.get("readable"),
            "received_at": event.get("received_at"),
        })

    # ── Step 6: Schedule delivery attempt (Phase 3) ──
    # This runs AFTER the response is sent to the provider,
    # so it never slows down the 200 response.
    # If endpoint.url is the customer's actual receiving server,
    # we forward this event there and retry on failure.
    if event and endpoint.get("url"):
        background_tasks.add_task(
            attempt_delivery,
            event_id=event["id"],
            endpoint_id=endpoint_id,
            endpoint_url=endpoint["url"],
            payload=payload,
            retry_count=0
        )

    # ── Step 6b: Schedule AI explainer (Phase 4) ──
    # Also runs after the response is sent. Generates a
    # plain-English summary of this payload, separate from
    # the rule-based "readable" text from the provider parser.
    if event:
        background_tasks.add_task(
            explain_payload,
            event_id=event["id"],
            provider=provider_name,
            event_type=parsed.get("event_type", "unknown"),
            payload=payload,
            readable=parsed.get("readable", "")
        )

    # ── Step 7: ALWAYS return 200 immediately ──
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