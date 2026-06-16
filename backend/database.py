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


async def get_all_endpoints() -> list:
    """Get all registered endpoints"""
    try:
        result = supabase.table("endpoints")\
            .select("*")\
            .order("created_at", desc=True)\
            .execute()
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


async def get_all_recent_events(limit: int = 50) -> list:
    """Get recent events across all endpoints"""
    try:
        result = supabase.table("webhook_events")\
            .select("*, endpoints(name, provider)")\
            .order("received_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data
    except Exception as e:
        logger.error(f"Error getting recent events: {e}")
        return []


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