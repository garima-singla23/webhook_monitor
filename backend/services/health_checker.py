# services/health_checker.py
# ─────────────────────────────────────────────
# Pings every registered endpoint every 60s
# Records UP / DOWN / DEGRADED status
# Detects consecutive failures
# Triggers alerts on failure
# ─────────────────────────────────────────────

import httpx
import asyncio
import time
import logging
from datetime import datetime, timezone

from database import (
    get_all_endpoints,
    save_health_check,
    update_endpoint,
    get_consecutive_failure_count,
    save_alert_log,
    supabase
)
from services.ai_diagnosis import diagnose_failure
from services.alerting import send_alert
from websocket.manager import broadcast

logger = logging.getLogger(__name__)


# ════════════════════════════════
# CDN DETECTION
# ════════════════════════════════

# Headers that indicate CDN presence
CDN_SIGNATURES = {
    "cf-ray":           "Cloudflare",
    "cf-cache-status":  "Cloudflare",
    "x-amz-cf-id":      "AWS CloudFront",
    "x-served-by":      "Fastly",
    "x-cache":          "Generic CDN",
    "x-azure-ref":      "Azure CDN",
    "x-cdn":            "Generic CDN",
}


def detect_cdn(headers: dict) -> dict:
    """
    Check response headers for CDN signatures.

    Returns:
        detected: bool
        provider: str or None
    """
    headers_lower = {k.lower(): v for k, v in headers.items()}

    for header, provider in CDN_SIGNATURES.items():
        if header in headers_lower:
            return {
                "detected": True,
                "provider": provider,
                "header_value": headers_lower[header]
            }

    return {"detected": False, "provider": None}


# ════════════════════════════════
# SINGLE ENDPOINT CHECK
# ════════════════════════════════

async def check_single_endpoint(endpoint: dict) -> dict:
    """
    Ping one endpoint and record the result.

    Status values:
    - up        → responded within threshold
    - degraded  → responded but slower than threshold
    - down      → did not respond at all

    Returns the health check result dict.
    """

    endpoint_id = endpoint["id"]
    url = endpoint["url"]
    threshold_ms = endpoint.get("threshold_ms", 5000)

    result = {
        "endpoint_id": endpoint_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "status": "down",
        "response_time_ms": None,
        "status_code": None,
        "error_message": None,
        "cdn_detected": False,
        "cdn_provider": None
    }

    start = time.time()

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=10.0
        ) as client:
            response = await client.get(url)

        response_time = int((time.time() - start) * 1000)

        # Detect CDN from response headers
        cdn_info = detect_cdn(dict(response.headers))

        result["response_time_ms"] = response_time
        result["status_code"] = response.status_code
        result["cdn_detected"] = cdn_info["detected"]
        result["cdn_provider"] = cdn_info["provider"]

        # Determine status
        if response_time > threshold_ms:
            result["status"] = "degraded"
            result["error_message"] = (
                f"Slow response: {response_time}ms "
                f"(threshold: {threshold_ms}ms)"
            )
        elif response.status_code >= 500:
            result["status"] = "down"
            result["error_message"] = (
                f"Server error: HTTP {response.status_code}"
            )
        else:
            result["status"] = "up"

    except httpx.TimeoutException:
        result["status"] = "down"
        result["error_message"] = "Request timed out after 10 seconds"
        result["response_time_ms"] = 10000

    except httpx.ConnectError:
        result["status"] = "down"
        result["error_message"] = "Could not connect to server"

    except httpx.TooManyRedirects:
        result["status"] = "down"
        result["error_message"] = "Too many redirects"

    except Exception as e:
        result["status"] = "down"
        result["error_message"] = f"Unexpected error: {str(e)[:100]}"

    # Save to database
    try:
        await save_health_check(result)
    except Exception as e:
        logger.error(
            f"Failed to save health check for {endpoint_id}: {e}"
        )

    # Update endpoint's last_status and last_checked_at
    try:
        await update_endpoint(endpoint_id, {
            "last_status": result["status"],
            "last_checked_at": result["checked_at"]
        })
    except Exception as e:
        logger.error(f"Failed to update endpoint status: {e}")

    # Handle consecutive failure tracking
    await handle_failure_tracking(endpoint, result)

    return result


# ════════════════════════════════
# FAILURE TRACKING
# ════════════════════════════════

async def handle_failure_tracking(
    endpoint: dict,
    result: dict
):
    """
    Track consecutive failures.
    Alert when 3 consecutive failures detected.
    Alert when endpoint recovers.
    """

    endpoint_id = endpoint["id"]
    current_status = result["status"]
    previous_status = endpoint.get("last_status", "unknown")

    # ── Phase 5: broadcast only on a REAL status change ──
    # Without this guard, a stably-"up" endpoint would push
    # a message every single 60-second cycle forever, which
    # would flood the dashboard with noise for no reason.
    if current_status != previous_status:
        await broadcast("health_status_changed", {
            "endpoint_id": endpoint_id,
            "endpoint_name": endpoint.get("name"),
            "previous_status": previous_status,
            "current_status": current_status,
            "response_time_ms": result.get("response_time_ms"),
            "error_message": result.get("error_message"),
            "checked_at": result.get("checked_at"),
        })

    if current_status in ("down", "degraded"):
        # Increment failure counter
        new_count = (
            endpoint.get("consecutive_failures", 0) + 1
        )

        await update_endpoint(endpoint_id, {
            "consecutive_failures": new_count
        })

        logger.warning(
            f"Endpoint '{endpoint['name']}' is {current_status} "
            f"(failure #{new_count}): {result['error_message']}"
        )

        # Alert after 3 consecutive failures
        if new_count == 3:
            logger.error(
                f"ALERT: '{endpoint['name']}' has failed "
                f"3 times in a row!"
            )
            await log_alert(endpoint, "down", (
                f"Endpoint '{endpoint['name']}' is DOWN. "
                f"3 consecutive failures. "
                f"Error: {result['error_message']}"
            ))

            # ── Phase 4: get AI diagnosis for this failure ──
            try:
                diagnosis = await diagnose_failure(
                    endpoint_id=endpoint_id,
                    source="health_check",
                    source_id=result.get("id"),
                    failure_data={
                        "source": "health_check",
                        "provider": endpoint.get("provider", "generic"),
                        "status_code": result.get("status_code"),
                        "response_time_ms": result.get("response_time_ms"),
                        "error_message": result.get("error_message"),
                        "consecutive_failures": new_count,
                    }
                )
                logger.info(
                    f"AI diagnosis for '{endpoint['name']}': "
                    f"{diagnosis['likely_cause']}"
                )
            except Exception as e:
                logger.error(f"AI diagnosis failed: {e}")

    else:
        # Endpoint is UP
        previous_failures = endpoint.get(
            "consecutive_failures", 0
        )

        # Reset failure counter
        if previous_failures > 0:
            await update_endpoint(endpoint_id, {
                "consecutive_failures": 0
            })

            # Recovery alert
            if previous_failures >= 3:
                logger.info(
                    f"RECOVERED: '{endpoint['name']}' "
                    f"is back UP after {previous_failures} failures"
                )
                await log_alert(endpoint, "recovered", (
                    f"Endpoint '{endpoint['name']}' has RECOVERED. "
                    f"Was down for {previous_failures} checks."
                ))


async def log_alert(
    endpoint: dict,
    alert_type: str,
    message: str
):
    """
    Save the alert condition to alerts_log (Phase 2 behavior,
    unchanged), then deliver it to Slack/email (Phase 6).

    Takes the full endpoint dict (not just endpoint_id) because
    send_alert() needs the endpoint's name, url, and per-endpoint
    channel preferences to build and route the notification.
    """
    alert_row = await save_alert_log(endpoint["id"], alert_type, message)
    alert_id = alert_row["id"] if alert_row else None

    # ── Phase 6: actually deliver the alert ──
    # Wrapped so a Slack/email failure never breaks health checking.
    try:
        await send_alert(endpoint, alert_id, alert_type, message)
    except Exception as e:
        logger.error(f"send_alert failed entirely: {e}")


# ════════════════════════════════
# CHECK ALL ENDPOINTS
# ════════════════════════════════

async def check_all_endpoints():
    """
    Run health checks on ALL active endpoints.

    Called by APScheduler every 60 seconds.
    Uses asyncio.gather to check all in parallel.
    """

    logger.info("Running health checks...")

    # Get all active endpoints
    endpoints = await get_all_endpoints()
    active = [
        ep for ep in endpoints
        if ep.get("is_active", True)
    ]

    if not active:
        logger.info("No active endpoints to check")
        return

    logger.info(f"Checking {len(active)} endpoints...")

    # Run all checks in parallel
    # asyncio.gather = run multiple async functions together
    results = await asyncio.gather(
        *[check_single_endpoint(ep) for ep in active],
        return_exceptions=True  # don't stop if one fails
    )

    # Log summary
    up_count = sum(
        1 for r in results
        if isinstance(r, dict) and r.get("status") == "up"
    )
    down_count = sum(
        1 for r in results
        if isinstance(r, dict) and r.get("status") == "down"
    )
    degraded_count = sum(
        1 for r in results
        if isinstance(r, dict) and r.get("status") == "degraded"
    )

    logger.info(
        f"Health check complete: "
        f"{up_count} UP | "
        f"{degraded_count} DEGRADED | "
        f"{down_count} DOWN"
    )

    return results