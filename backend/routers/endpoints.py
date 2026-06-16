# routers/endpoints.py
# ─────────────────────────────────────────────
# API routes for managing webhook endpoints
# CRUD: Create, Read, Update, Delete
# ─────────────────────────────────────────────

from fastapi import APIRouter, HTTPException
from models.endpoint import EndpointCreate, EndpointUpdate
from database import (
    create_endpoint,
    get_endpoint,
    get_all_endpoints,
    update_endpoint,
    delete_endpoint,
    get_event_stats
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/endpoints",
    tags=["endpoints"]
)


@router.post("/")
async def register_endpoint(data: EndpointCreate):
    """
    Register a new webhook endpoint to monitor.

    Example:
    POST /api/endpoints
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
            "is_active": True
        })

        logger.info(f"Endpoint registered: {data.name}")

        return {
            "success": True,
            "message": "Endpoint registered successfully",
            "endpoint": endpoint,
            # Give them their unique webhook URL
            "webhook_url": f"/webhook/{endpoint['id']}"
        }

    except Exception as e:
        logger.error(f"Error registering endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to register endpoint"
        )


@router.get("/")
async def list_endpoints():
    """
    Get all registered endpoints.

    Example:
    GET /api/endpoints
    """
    endpoints = await get_all_endpoints()
    return {
        "success": True,
        "count": len(endpoints),
        "endpoints": endpoints
    }


@router.get("/{endpoint_id}")
async def get_endpoint_detail(endpoint_id: str):
    """
    Get a single endpoint with its stats.

    Example:
    GET /api/endpoints/abc123
    """
    endpoint = await get_endpoint(endpoint_id)

    if not endpoint:
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found"
        )

    # Get stats for this endpoint
    stats = await get_event_stats(endpoint_id)

    return {
        "success": True,
        "endpoint": endpoint,
        "stats": stats
    }


@router.patch("/{endpoint_id}")
async def update_endpoint_settings(
    endpoint_id: str,
    data: EndpointUpdate
):
    """
    Update endpoint settings.

    Example:
    PATCH /api/endpoints/abc123
    {
        "threshold_ms": 3000,
        "is_active": false
    }
    """
    # Check endpoint exists
    existing = await get_endpoint(endpoint_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found"
        )

    # Only update fields that were provided
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
async def remove_endpoint(endpoint_id: str):
    """
    Delete an endpoint.

    Example:
    DELETE /api/endpoints/abc123
    """
    existing = await get_endpoint(endpoint_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Endpoint not found"
        )

    await delete_endpoint(endpoint_id)

    return {
        "success": True,
        "message": "Endpoint deleted"
    }