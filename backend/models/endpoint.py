# models/endpoint.py
# ─────────────────────────────────────────────
# Pydantic models define the shape of data
# FastAPI uses these to validate input/output
# ─────────────────────────────────────────────

from pydantic import BaseModel, HttpUrl, validator, field_validator
from typing import Optional
from datetime import datetime
from enum import Enum


class Provider(str, Enum):
    """Supported webhook providers"""
    razorpay = "razorpay"
    stripe = "stripe"
    github = "github"
    generic = "generic"


class EndpointCreate(BaseModel):
    """
    Schema for creating a new endpoint.
    FastAPI validates incoming request against this.
    
    Example request body:
    {
        "name": "My Payment Webhook",
        "url": "https://myapp.com/webhooks",
        "provider": "razorpay",
        "threshold_ms": 5000
    }
    """
    name: str
    url: str
    provider: Provider = Provider.generic
    threshold_ms: int = 5000

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        if len(v) > 100:
            raise ValueError('Name must be under 100 characters')
        return v

    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if not v.startswith('http://') and \
           not v.startswith('https://'):
            raise ValueError('URL must start with http:// or https://')
        if 'localhost' in v or '127.0.0.1' in v:
            raise ValueError('Cannot monitor localhost URLs')
        return v

    @field_validator('threshold_ms')
    @classmethod
    def validate_threshold(cls, v):
        if v < 100:
            raise ValueError('Threshold must be at least 100ms')
        if v > 30000:
            raise ValueError('Threshold must be under 30 seconds')
        return v


class EndpointUpdate(BaseModel):
    """Schema for updating an endpoint (all fields optional)"""
    name: Optional[str] = None
    threshold_ms: Optional[int] = None
    is_active: Optional[bool] = None


class EndpointResponse(BaseModel):
    """Schema for endpoint in API response"""
    id: str
    name: str
    url: str
    provider: str
    threshold_ms: int
    is_active: bool
    created_at: str


class WebhookEventStatus(str, Enum):
    received = "received"
    delivered = "delivered"
    failed = "failed"
    retrying = "retrying"