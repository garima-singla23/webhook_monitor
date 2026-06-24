# database.py
# ─────────────────────────────────────────────
# All database operations in one place
# Uses Supabase (free PostgreSQL)
# ─────────────────────────────────────────────

from supabase import create_client, Client
from config import settings
import logging

logger = logging.getLogger(__name__)

# ── Create Supabase client ──
# This is created once when app starts
print("SUPABASE_URL ENV:", repr(os.getenv("SUPABASE_URL")))
print("SUPABASE_KEY ENV:", repr(os.getenv("SUPABASE_KEY")))
print("SETTINGS URL:", repr(settings.supabase_url))
print("SETTINGS KEY:", repr(settings.supabase_key))

supabase: Client = create_client(
    settings.supabase_url,
    settings.supabase_key
)


# ════════════════════════════════
# ENDPOINT OPERATIONS
# ════════════════════════════════

async def create_endpoint(data: dict) -> dict:
    """
    Register a new webhook endpoint to monitor.
    
    data = {
        "name": "My Razorpay Webhook",
        "url": "https://myapp.com/webhooks",
        "provider": "razorpay",
        "threshold_ms": 5000
    }
    """
    try:
        result = supabase.table("endpoints")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error creating endpoint: {e}")
        raise


async def get_endpoint(endpoint_id: str) -> dict | None:
    """Get a single endpoint by ID"""
    try:
        result = supabase.table("endpoints")\
            .select("*")\
            .eq("id", endpoint_id)\
            .single()\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting endpoint {endpoint_id}: {e}")
        return None


async def get_all_endpoints(user_id: str | None = None) -> list:
    """
    Get registered endpoints.

    user_id=None  → ALL endpoints, regardless of owner.
                    Used ONLY by system/background callers that
                    have no concept of "a user" — the scheduler's
                    check_all_endpoints() needs to check everyone's
                    endpoints, not just one person's.

    user_id=<uuid> → only that user's endpoints.
                     Used by every user-facing API route, so one
                     person never sees another person's data even
                     if this application-level filter were somehow
                     bypassed — RLS is still the real enforcement
                     layer, this is defense in depth on top of it.
    """
    try:
        query = supabase.table("endpoints").select("*")

        if user_id is not None:
            query = query.eq("user_id", user_id)

        result = query.order("created_at", desc=True).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting all endpoints: {e}")
        return []


async def update_endpoint(
    endpoint_id: str,
    data: dict
) -> dict | None:
    """Update endpoint settings"""
    try:
        result = supabase.table("endpoints")\
            .update(data)\
            .eq("id", endpoint_id)\
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error updating endpoint: {e}")
        raise


async def delete_endpoint(endpoint_id: str) -> bool:
    """Delete an endpoint"""
    try:
        supabase.table("endpoints")\
            .delete()\
            .eq("id", endpoint_id)\
            .execute()
        return True
    except Exception as e:
        logger.error(f"Error deleting endpoint: {e}")
        return False


# ════════════════════════════════
# WEBHOOK EVENT OPERATIONS
# ════════════════════════════════

async def save_webhook_event(data: dict) -> dict:
    """
    Save a received webhook event to database.
    
    data = {
        "endpoint_id": "uuid",
        "provider": "razorpay",
        "event_type": "payment.captured",
        "payload": {...},
        "status": "received",
        "response_time_ms": 45
    }
    """
    try:
        result = supabase.table("webhook_events")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error saving webhook event: {e}")
        raise


async def get_events_for_endpoint(
    endpoint_id: str,
    limit: int = 20
) -> list:
    """Get recent webhook events for an endpoint"""
    try:
        result = supabase.table("webhook_events")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("received_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting events: {e}")
        return []


async def get_all_recent_events(
    limit: int = 50,
    user_id: str | None = None
) -> list:
    """
    Get recent events across endpoints.

    user_id=None  → events from ALL endpoints, regardless of
                    owner. Used only by system/background work.

    user_id=<uuid> → only events belonging to that user's own
                     endpoints. Used by every user-facing route.
                     Filters via a Supabase foreign-table filter
                     on the joined endpoints relation, since
                     webhook_events has no user_id column of its
                     own — same join-through-ownership pattern as
                     the RLS policies in supabase_phase7.sql.
    """
    try:
        query = supabase.table("webhook_events")\
            .select("*, endpoints!inner(name, provider, user_id)")

        if user_id is not None:
            query = query.eq("endpoints.user_id", user_id)

        result = query.order("received_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting recent events: {e}")
        return []


# ════════════════════════════════
# HEALTH CHECK OPERATIONS (Phase 2)
# ════════════════════════════════

async def save_health_check(data: dict) -> dict:
    """
    Save a health check result.

    data = {
        "endpoint_id": "uuid",
        "status": "up/down/degraded",
        "response_time_ms": 145,
        "status_code": 200,
        "error_message": None
    }
    """
    try:
        result = supabase.table("health_checks")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error saving health check: {e}")
        raise


async def get_health_checks(
    endpoint_id: str,
    limit: int = 50
) -> list:
    """Get recent health checks for an endpoint"""
    try:
        result = supabase.table("health_checks")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("checked_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting health checks: {e}")
        return []


async def get_latest_health_check(
    endpoint_id: str
) -> dict | None:
    """Get most recent health check for an endpoint"""
    try:
        result = supabase.table("health_checks")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("checked_at", desc=True)\
            .limit(1)\
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error getting latest health check: {e}")
        return None


async def get_uptime_percentage(
    endpoint_id: str,
    last_n_checks: int = 100
) -> float:
    """
    Calculate uptime % from last N health checks.

    Formula: (UP checks / total checks) * 100
    """
    try:
        result = supabase.table("health_checks")\
            .select("status")\
            .eq("endpoint_id", endpoint_id)\
            .order("checked_at", desc=True)\
            .limit(last_n_checks)\
            .execute()

        checks = result.data
        if not checks:
            return 100.0

        up_count = sum(
            1 for c in checks
            if c.get("status") == "up"
        )

        return round((up_count / len(checks)) * 100, 2)

    except Exception as e:
        logger.error(f"Error calculating uptime: {e}")
        return 0.0


async def get_average_response_time(
    endpoint_id: str,
    last_n_checks: int = 20
) -> float | None:
    """Get average response time from recent checks"""
    try:
        result = supabase.table("health_checks")\
            .select("response_time_ms")\
            .eq("endpoint_id", endpoint_id)\
            .eq("status", "up")\
            .order("checked_at", desc=True)\
            .limit(last_n_checks)\
            .execute()

        checks = result.data
        if not checks:
            return None

        times = [
            c["response_time_ms"]
            for c in checks
            if c.get("response_time_ms")
        ]

        return round(sum(times) / len(times), 2) if times else None

    except Exception as e:
        logger.error(f"Error getting avg response time: {e}")
        return None


async def get_consecutive_failure_count(
    endpoint_id: str
) -> int:
    """
    Count how many consecutive failures an endpoint has.
    Stops counting when it hits a success.
    Used to decide when to send alerts.
    """
    try:
        result = supabase.table("health_checks")\
            .select("status")\
            .eq("endpoint_id", endpoint_id)\
            .order("checked_at", desc=True)\
            .limit(20)\
            .execute()

        checks = result.data
        count = 0

        for check in checks:
            if check.get("status") in ("down", "degraded"):
                count += 1
            else:
                break  # stop at first success

        return count

    except Exception as e:
        logger.error(f"Error counting failures: {e}")
        return 0


# ════════════════════════════════
# DELIVERY TRACKING OPERATIONS (Phase 3)
# ════════════════════════════════

async def get_webhook_event(event_id: str) -> dict | None:
    """Get a single webhook event by ID"""
    try:
        result = supabase.table("webhook_events")\
            .select("*")\
            .eq("id", event_id)\
            .single()\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting event {event_id}: {e}")
        return None


async def update_event_delivery_status(
    event_id: str,
    data: dict
) -> dict | None:
    """
    Update delivery tracking fields on a webhook event.

    data can include:
        delivery_status, retry_count, next_retry_at,
        last_attempt_at, last_delivery_error, delivered_at
    """
    try:
        result = supabase.table("webhook_events")\
            .update(data)\
            .eq("id", event_id)\
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error updating delivery status: {e}")
        raise


async def save_delivery_attempt(data: dict) -> dict:
    """
    Log a single delivery attempt (success or failure).

    data = {
        "event_id": "uuid",
        "endpoint_id": "uuid",
        "attempt_number": 1,
        "success": False,
        "status_code": 500,
        "response_time_ms": 230,
        "error_message": "Server error"
    }
    """
    try:
        result = supabase.table("delivery_attempts")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error saving delivery attempt: {e}")
        raise


async def get_delivery_attempts(
    event_id: str
) -> list:
    """Get full attempt history for one webhook event"""
    try:
        result = supabase.table("delivery_attempts")\
            .select("*")\
            .eq("event_id", event_id)\
            .order("attempted_at", desc=False)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting delivery attempts: {e}")
        return []


async def get_pending_retries(limit: int = 100) -> list:
    """
    Get events that are queued for retry and whose
    next_retry_at has already passed (i.e. ready now).
    Used as a fallback/reconciliation check —
    primary queue lives in Redis, this is the safety net.
    """
    try:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        result = supabase.table("webhook_events")\
            .select("*")\
            .eq("delivery_status", "retrying")\
            .lte("next_retry_at", now)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting pending retries: {e}")
        return []


async def get_delivery_stats(endpoint_id: str) -> dict:
    """
    Get delivery health stats for an endpoint:
    - how many delivered on first try vs needed retries
    - how many permanently failed
    """
    try:
        result = supabase.table("webhook_events")\
            .select("delivery_status, retry_count")\
            .eq("endpoint_id", endpoint_id)\
            .execute()

        events = result.data
        total = len(events)

        delivered = sum(
            1 for e in events
            if e.get("delivery_status") == "delivered"
        )
        delivered_first_try = sum(
            1 for e in events
            if e.get("delivery_status") == "delivered"
            and (e.get("retry_count") or 0) == 0
        )
        retrying = sum(
            1 for e in events
            if e.get("delivery_status") == "retrying"
        )
        failed = sum(
            1 for e in events
            if e.get("delivery_status") == "failed"
        )

        return {
            "total": total,
            "delivered": delivered,
            "delivered_first_try": delivered_first_try,
            "needed_retry": delivered - delivered_first_try,
            "currently_retrying": retrying,
            "permanently_failed": failed
        }

    except Exception as e:
        logger.error(f"Error getting delivery stats: {e}")
        return {
            "total": 0, "delivered": 0,
            "delivered_first_try": 0, "needed_retry": 0,
            "currently_retrying": 0, "permanently_failed": 0
        }


async def get_event_stats(endpoint_id: str) -> dict:
    """
    Get stats for an endpoint:
    - total events
    - events by status
    - events by provider
    """
    try:
        result = supabase.table("webhook_events")\
            .select("status, provider")\
            .eq("endpoint_id", endpoint_id)\
            .execute()

        events = result.data
        total = len(events)

        # Count by status
        status_counts = {}
        for event in events:
            s = event.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total": total,
            "by_status": status_counts,
            "received": status_counts.get("received", 0),
            "delivered": status_counts.get("delivered", 0),
            "failed": status_counts.get("failed", 0),
        }

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"total": 0, "by_status": {}}


# ════════════════════════════════
# AI FEATURES (Phase 4)
# ════════════════════════════════

async def save_ai_diagnosis(data: dict) -> dict:
    """
    Save an AI failure diagnosis.

    data = {
        "endpoint_id": "uuid",
        "source": "health_check" | "delivery",
        "source_id": "uuid",
        "likely_cause": "...",
        "severity": "low/medium/high/critical",
        "suggested_fix": "...",
        "code_hint": "..." or None,
        "cache_key": "..."
    }
    """
    try:
        result = supabase.table("ai_diagnoses")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error saving AI diagnosis: {e}")
        raise


async def get_diagnoses_for_endpoint(
    endpoint_id: str,
    limit: int = 20
) -> list:
    """Get recent AI diagnoses for an endpoint"""
    try:
        result = supabase.table("ai_diagnoses")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting diagnoses: {e}")
        return []


async def update_event_ai_summary(
    event_id: str,
    summary: str
) -> dict | None:
    """Save the AI-generated plain-English summary on an event"""
    try:
        result = supabase.table("webhook_events")\
            .update({"ai_summary": summary})\
            .eq("id", event_id)\
            .execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Error saving AI summary: {e}")
        raise


# ════════════════════════════════
# ALERT DELIVERY TRACKING (Phase 6)
# ════════════════════════════════

async def save_alert_log(
    endpoint_id: str,
    alert_type: str,
    message: str
) -> dict | None:
    """
    Save the alert condition itself (Phase 2 behavior, unchanged).
    Returns the inserted row so Phase 6 can use its id when
    logging delivery attempts against it.
    """
    try:
        result = supabase.table("alerts_log").insert({
            "endpoint_id": endpoint_id,
            "alert_type": alert_type,
            "message": message
        }).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to log alert: {e}")
        return None


async def save_alert_delivery(data: dict) -> dict:
    """
    Log whether an alert was successfully delivered to a
    specific channel (Slack or email).

    data = {
        "alert_id": "uuid" or None,
        "endpoint_id": "uuid",
        "channel": "slack" | "email",
        "success": bool,
        "error_message": str | None
    }
    """
    try:
        result = supabase.table("alert_deliveries")\
            .insert(data)\
            .execute()
        return result.data[0]
    except Exception as e:
        logger.error(f"Error saving alert delivery: {e}")
        raise


async def get_alert_deliveries(
    endpoint_id: str,
    limit: int = 20
) -> list:
    """Get recent alert delivery attempts for an endpoint"""
    try:
        result = supabase.table("alert_deliveries")\
            .select("*")\
            .eq("endpoint_id", endpoint_id)\
            .order("sent_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting alert deliveries: {e}")
        return []