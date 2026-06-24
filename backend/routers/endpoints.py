# routers/endpoints.py
# ─────────────────────────────────────────────
# API routes for managing webhook endpoints
# CRUD: Create, Read, Update, Delete
#
# Phase 7: every route now requires authentication
# via Depends(get_current_user), and every operation
# is scoped to the logged-in user's own endpoints.
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Depends
from models.endpoint import EndpointCreate, EndpointUpdate
from database import (
    create_endpoint,
    get_endpoint,
    get_all_endpoints,
    update_endpoint,
    delete_endpoint,
    get_event_stats
)
from auth_deps import get_current_user, AuthUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/endpoints",
    tags=["endpoints"]
)


async def _get_owned_endpoint_or_404(endpoint_id: str, user: AuthUser) -> dict:
    """
    Shared helper: fetch an endpoint and verify the current
    user actually owns it.

    This is intentionally redundant with RLS — even if this
    check were accidentally removed, the database-level policy
    in supabase_phase7.sql would still prevent cross-user access.
    But checking here too means we can return a clean 404
    ("not found") instead of relying on RLS to silently return
    nothing and hoping the calling code handles that gracefully.
    """
    endpoint = await get_endpoint(endpoint_id)

    if not endpoint or endpoint.get("user_id") != user.id:
        # Deliberately the SAME error for "doesn't exist" and
        # "exists but belongs to someone else" — returning a
        # different message for the second case would leak
        # information about which endpoint IDs are real.
        raise HTTPException(status_code=404, detail="Endpoint not found")

    return endpoint


@router.post("/")
async def register_endpoint(
    data: EndpointCreate,
    user: AuthUser = Depends(get_current_user)
):
    """
    Register a new webhook endpoint to monitor, owned by
    the currently authenticated user.

    Example:
    POST /api/endpoints
    Authorization: Bearer <token>
    {
        "name": "My Payment Webhook",
        "url": "https://myapp.com/webhooks/razorpay",
        "provider": "razorpay",
        "threshold_ms": 5000
    }
    """
    try:
        endpoint = await create_endpoint({
            "name": data.name,
            "url": str(data.url),
            "provider": data.provider.value,
            "threshold_ms": data.threshold_ms,
            "is_active": True,
            "user_id": user.id,
        })

        logger.info(f"Endpoint registered: {data.name} (user {user.id})")

        return {
            "success": True,
            "message": "Endpoint registered successfully",
            "endpoint": endpoint,
            "webhook_url": f"/webhook/{endpoint['id']}"
        }

    except Exception as e:
        logger.error(f"Error registering endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to register endpoint"
        )


@router.get("/")
async def list_endpoints(user: AuthUser = Depends(get_current_user)):
    """
    Get all endpoints belonging to the currently authenticated user.
    Other users' endpoints are never included, even though this is
    a "list everything" style route.

    Example:
    GET /api/endpoints
    Authorization: Bearer <token>
    """
    endpoints = await get_all_endpoints(user_id=user.id)
    return {
        "success": True,
        "count": len(endpoints),
        "endpoints": endpoints
    }


@router.get("/{endpoint_id}")
async def get_endpoint_detail(
    endpoint_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Get a single endpoint with its stats — only if it
    belongs to the current user.

    Example:
    GET /api/endpoints/abc123
    Authorization: Bearer <token>
    """
    endpoint = await _get_owned_endpoint_or_404(endpoint_id, user)
    stats = await get_event_stats(endpoint_id)

    return {
        "success": True,
        "endpoint": endpoint,
        "stats": stats
    }


@router.patch("/{endpoint_id}")
async def update_endpoint_settings(
    endpoint_id: str,
    data: EndpointUpdate,
    user: AuthUser = Depends(get_current_user)
):
    """
    Update endpoint settings — only if it belongs to the
    current user.

    Example:
    PATCH /api/endpoints/abc123
    Authorization: Bearer <token>
    {
        "threshold_ms": 3000,
        "is_active": false
    }
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields to update"
        )

    updated = await update_endpoint(endpoint_id, update_data)

    return {
        "success": True,
        "message": "Endpoint updated",
        "endpoint": updated
    }


@router.delete("/{endpoint_id}")
async def remove_endpoint(
    endpoint_id: str,
    user: AuthUser = Depends(get_current_user)
):
    """
    Delete an endpoint — only if it belongs to the current user.

    Example:
    DELETE /api/endpoints/abc123
    Authorization: Bearer <token>
    """
    await _get_owned_endpoint_or_404(endpoint_id, user)
    await delete_endpoint(endpoint_id)

    return {
        "success": True,
        "message": "Endpoint deleted"
    }