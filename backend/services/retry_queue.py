# services/retry_queue.py
# Redis-backed retry queue for failed webhook
# deliveries to customer endpoints.
#
# Flow:
#   1. attempt_delivery() tries to POST payload to the customer's registered URL
#   2. On success → mark event "delivered"
#   3. On failure → push to Redis queue with a retry_after timestamp (exponential backoff)
#   4. process_retry_queue() runs every 30s v APScheduler, pops items whose time has come, retries them, re-queues or gives up

import json
import time
import logging
from datetime import datetime, timezone, timedelta

import httpx

from redis_client import redis_client
from database import (
    get_endpoint,
    update_event_delivery_status,
    save_delivery_attempt,
)
from services.ai_diagnosis import diagnose_failure
from websocket.manager import broadcast

logger = logging.getLogger(__name__)

# ── Config ──
QUEUE_KEY = "webhook:retry:queue"
MAX_RETRIES = 5

# Retry after: 30s, 1min, 5min, 10min, 30min
RETRY_DELAYS = [30, 60, 300, 600, 1800]

DELIVERY_TIMEOUT_SECONDS = 10.0


def get_retry_delay(retry_count: int) -> int:
    """How many seconds to wait before the next retry"""
    if retry_count < len(RETRY_DELAYS):
        return RETRY_DELAYS[retry_count]
    return RETRY_DELAYS[-1]

# DELIVERY ATTEMPT (the actual HTTP call)
async def deliver_payload(
    url: str,
    payload: dict
) -> dict:
    """
    Attempt to POST the webhook payload to the
    customer's registered endpoint URL.

    Returns:
        {
            "success": bool,
            "status_code": int | None,
            "response_time_ms": int | None,
            "error_message": str | None
        }
    """
    start = time.time()

    try:
        async with httpx.AsyncClient(
            timeout=DELIVERY_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload)

        response_time_ms = int((time.time() - start) * 1000)

        # 2xx = success. Anything else counts as a failed delivery.
        success = 200 <= response.status_code < 300

        return {
            "success": success,
            "status_code": response.status_code,
            "response_time_ms": response_time_ms,
            "error_message": None if success else (
                f"Endpoint returned {response.status_code}"
            )
        }

    except httpx.TimeoutException:
        return {
            "success": False,
            "status_code": None,
            "response_time_ms": int(DELIVERY_TIMEOUT_SECONDS * 1000),
            "error_message": f"Timed out after {DELIVERY_TIMEOUT_SECONDS}s"
        }

    except httpx.ConnectError:
        return {
            "success": False,
            "status_code": None,
            "response_time_ms": int((time.time() - start) * 1000),
            "error_message": "Could not connect to endpoint"
        }

    except Exception as e:
        return {

            "success": False,
            "status_code": None,
            "response_time_ms": int((time.time() - start) * 1000),
            "error_message": str(e)
        }


# ════════════════════════════════
# FIRST ATTEMPT — called right after a webhook is received
# ════════════════════════════════

async def attempt_delivery(
    event_id: str,
    endpoint_id: str,
    endpoint_url: str,
    payload: dict,
    retry_count: int = 0
):
    """
    Try delivering a webhook event to the customer's endpoint.
    Called once immediately on receipt (retry_count=0), and
    again later by process_retry_queue() for retries.
    """

    result = await deliver_payload(endpoint_url, payload)
    attempt_number = retry_count + 1

    # Always log the attempt, success or failure
    try:
        await save_delivery_attempt({
            "event_id": event_id,
            "endpoint_id": endpoint_id,
            "attempt_number": attempt_number,
            "success": result["success"],
            "status_code": result["status_code"],
            "response_time_ms": result["response_time_ms"],
            "error_message": result["error_message"],
        })
    except Exception as e:
        logger.error(f"Failed to log delivery attempt: {e}")

    if result["success"]:
        await _mark_delivered(event_id, endpoint_id, retry_count)
        logger.info(
            f"Delivered event {event_id} "
            f"on attempt #{attempt_number}"
        )
        return

    # Delivery failed — decide: retry or give up
    if retry_count >= MAX_RETRIES:
        await _mark_permanently_failed(
            event_id, endpoint_id, result["error_message"]
        )
        logger.warning(
            f"Event {event_id} permanently failed "
            f"after {attempt_number} attempts"
        )

        # ── Phase 4: get AI diagnosis now that we've given up ──
        try:
            diagnosis = await diagnose_failure(
                endpoint_id=endpoint_id,
                source="delivery",
                source_id=event_id,
                failure_data={
                    "source": "delivery",
                    "provider": "generic",
                    "status_code": result.get("status_code"),
                    "response_time_ms": result.get("response_time_ms"),
                    "error_message": result.get("error_message"),
                    "consecutive_failures": attempt_number,
                }
            )
            logger.info(
                f"AI diagnosis for failed event {event_id}: "
                f"{diagnosis['likely_cause']}"
            )
        except Exception as e:
            logger.error(f"AI diagnosis failed: {e}")

        return

    # Queue for retry with exponential backoff
    await _queue_for_retry(
        event_id, endpoint_id, endpoint_url,
        payload, retry_count, result["error_message"]
    )


# ════════════════════════════════
# QUEUE MANAGEMENT (Redis)
# ════════════════════════════════

async def _queue_for_retry(
    event_id: str,
    endpoint_id: str,
    endpoint_url: str,
    payload: dict,
    retry_count: int,
    error_message: str
):
    """Push a failed delivery into the Redis retry queue"""

    delay_seconds = get_retry_delay(retry_count)
    retry_after_timestamp = time.time() + delay_seconds
    next_retry_dt = datetime.now(timezone.utc) + timedelta(
        seconds=delay_seconds
    )

    item = {
        "event_id": event_id,
        "endpoint_id": endpoint_id,
        "endpoint_url": endpoint_url,
        "payload": payload,
        "retry_count": retry_count + 1,
        "retry_after": retry_after_timestamp,
    }

    # lpush = add to the queue (a Redis list)
    redis_client.lpush(QUEUE_KEY, json.dumps(item))

    # Mirror status in Supabase too, so the dashboard
    # can show "retrying" without reading Redis directly
    try:
        await update_event_delivery_status(event_id, {
            "delivery_status": "retrying",
            "retry_count": retry_count + 1,
            "next_retry_at": next_retry_dt.isoformat(),
            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
            "last_delivery_error": error_message,
        })
    except Exception as e:
        logger.error(f"Failed to update event retry status: {e}")

    logger.info(
        f"Queued event {event_id} for retry #{retry_count + 1} "
        f"in {delay_seconds}s — reason: {error_message}"
    )

    # ── Phase 5: broadcast retry to live dashboard ──
    await broadcast("delivery_retrying", {
        "event_id": event_id,
        "endpoint_id": endpoint_id,
        "retry_count": retry_count + 1,
        "next_retry_in_seconds": delay_seconds,
        "error_message": error_message,
    })


async def _mark_delivered(
    event_id: str,
    endpoint_id: str,
    retry_count: int
):
    """Mark an event as successfully delivered"""
    try:
        await update_event_delivery_status(event_id, {
            "delivery_status": "delivered",
            "retry_count": retry_count,
            "delivered_at": datetime.now(timezone.utc).isoformat(),
            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
            "last_delivery_error": None,
            # also keep the original Phase 1 "status" field in sync
            "status": "delivered",
        })
    except Exception as e:
        logger.error(f"Failed to mark event delivered: {e}")

    # ── Phase 5: broadcast successful delivery ──
    # Useful to show on the dashboard even for the common,
    # happy-path case — not just failures.
    await broadcast("delivery_delivered", {
        "event_id": event_id,
        "endpoint_id": endpoint_id,
        "retry_count": retry_count,
        "delivered_after_retry": retry_count > 0,
    })


async def _mark_permanently_failed(
    event_id: str,
    endpoint_id: str,
    error_message: str
):
    """Mark an event as permanently failed after max retries"""
    try:
        await update_event_delivery_status(event_id, {
            "delivery_status": "failed",
            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
            "last_delivery_error": error_message,
            "status": "failed",
        })
    except Exception as e:
        logger.error(f"Failed to mark event as failed: {e}")

    # ── Phase 5: broadcast permanent failure ──
    # This is the most important delivery event to show live —
    # it means the system has given up and a human may need to
    # intervene (e.g. via the manual retry-now endpoint).
    await broadcast("delivery_failed", {
        "event_id": event_id,
        "endpoint_id": endpoint_id,
        "error_message": error_message,
    })


# ════════════════════════════════
# BACKGROUND WORKER — runs every 30s via scheduler
# ════════════════════════════════

async def process_retry_queue():
    """
    Pop all items from the Redis queue whose retry_after
    time has passed, and attempt delivery again.

    Items not yet ready are pushed back onto the queue.
    Called by APScheduler every 30 seconds.
    """

    queue_length = redis_client.llen(QUEUE_KEY)
    if queue_length == 0:
        return  # nothing to do, skip logging noise

    logger.info(f"Processing retry queue ({queue_length} items)...")

    processed = 0
    requeued = 0

    # We pop the entire current queue length once,
    # so we don't loop forever on items we just re-pushed
    for _ in range(queue_length):
        item_json = redis_client.rpop(QUEUE_KEY)
        if not item_json:
            break

        item = json.loads(item_json)

        # Not ready yet — push back and skip
        if time.time() < item["retry_after"]:
            redis_client.lpush(QUEUE_KEY, item_json)
            requeued += 1
            continue

        # Ready — retry delivery now
        processed += 1
        await attempt_delivery(
            event_id=item["event_id"],
            endpoint_id=item["endpoint_id"],
            endpoint_url=item["endpoint_url"],
            payload=item["payload"],
            retry_count=item["retry_count"],
        )

    if processed > 0:
        logger.info(
            f"Retry queue: {processed} retried, "
            f"{requeued} still waiting"
        )


def get_queue_status() -> dict:
    """Quick stats on the current Redis queue — used in /health"""
    try:
        length = redis_client.llen(QUEUE_KEY)
        return {"connected": True, "queue_length": length}
    except Exception as e:
        return {"connected": False, "error": str(e)}