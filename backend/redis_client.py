# redis_client.py
# Single shared Redis connection (Upstash)
# Used by the retry queue service

import redis
import logging
from config import settings

logger = logging.getLogger(__name__)

# ── Create Redis client once at import time ──
# decode_responses=True means r.get() returns a str, not bytes
# This saves you from writing .decode() everywhere
redis_client = redis.from_url(
    settings.upstash_redis_url,
    decode_responses=True
)


def check_redis_connection() -> bool:
    """
    Quick health check — used at startup and in /health endpoint.
    Returns True if Redis is reachable, False otherwise.
    """
    try:
        redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False