# services/ai_explainer.py
# Uses Groq to convert a raw webhook payload into
# a short, plain-English summary a non-technical
# person could understand.
#
# Caches by a hash of the payload shape so two
# very similar events don't both cost an API call.
import json
import hashlib
import logging
from groq import Groq

from config import settings
from redis_client import redis_client
from database import update_event_ai_summary

logger = logging.getLogger(__name__)

client = Groq(api_key=settings.groq_api_key)

MODEL = "llama-3.1-8b-instant"
CACHE_TTL_SECONDS = 3600


def _build_cache_key(provider: str, event_type: str, payload: dict) -> str:
    """
    Cache key based on provider + event_type + a hash of the
    payload's top-level keys (not full values, since amounts/IDs
    will differ between events but the explanation pattern won't).
    """
    shape = sorted(payload.keys()) if isinstance(payload, dict) else []
    key_parts = f"{provider}|{event_type}|{shape}"
    hashed = hashlib.sha256(key_parts.encode()).hexdigest()[:16]
    return f"ai_explain:{hashed}"


async def explain_payload(
    event_id: str,
    provider: str,
    event_type: str,
    payload: dict,
    readable: str = ""
) -> str:
    """
    Generate (or retrieve cached) plain-English summary
    of a webhook payload, and save it to the event row.

    readable is the existing Phase 1 provider-parsed text
    (e.g. "✅ Payment of INR 500.00 captured via upi") —
    passed in as extra context since it's already useful
    and free (no AI needed to produce it).
    """
    cache_key = _build_cache_key(provider, event_type, payload)

    cached = redis_client.get(cache_key)
    if cached:
        logger.info(f"AI explainer cache HIT: {cache_key}")
        summary = cached
    else:
        logger.info(f"AI explainer cache MISS — calling Groq: {cache_key}")
        summary = await _call_groq_for_explanation(
            provider, event_type, payload, readable
        )
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, summary)

    # Always save to this specific event row, even on cache hit —
    # the cached text is reused, but every event still gets its
    # own saved summary for display on the dashboard.
    try:
        await update_event_ai_summary(event_id, summary)
    except Exception as e:
        logger.error(f"Failed to save AI summary: {e}")

    return summary


async def _call_groq_for_explanation(
    provider: str,
    event_type: str,
    payload: dict,
    readable: str
) -> str:
    """Build the prompt, call Groq, return plain text"""

    # Truncate payload to keep prompt small and cheap
    payload_str = json.dumps(payload, indent=2)[:600]

    prompt = f"""Summarize this {provider} webhook event in 2-3 simple sentences
that a non-technical person could understand. Focus on what happened and
whether any action is needed.

Event type: {event_type}
Already-parsed description: {readable}

Raw payload (truncated):
{payload_str}

Respond with ONLY the plain English summary text. No JSON, no markdown,
no headers — just the summary sentences."""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Groq API call failed in explainer: {e}")
        # Fall back to the existing Phase 1 readable text —
        # never leave the user with nothing
        return readable or "Could not generate an AI summary for this event."