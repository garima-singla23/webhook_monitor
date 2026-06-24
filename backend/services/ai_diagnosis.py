# services/ai_diagnosis.py
# ─────────────────────────────────────────────
# Uses Groq's free LLM API to diagnose WHY a
# health check or webhook delivery failed, and
# suggest a specific fix.
#
# Caches identical failures in Redis for 1 hour
# so the same error doesn't trigger a new API
# call every single time it repeats.
# ─────────────────────────────────────────────

import json
import hashlib
import logging
from groq import Groq

from config import settings
from redis_client import redis_client
from database import save_ai_diagnosis
from websocket.manager import broadcast

logger = logging.getLogger(__name__)

# ── Groq client (created once) ──
client = Groq(api_key=settings.groq_api_key)

MODEL = "llama-3.1-8b-instant"
CACHE_TTL_SECONDS = 3600  # 1 hour


# ════════════════════════════════
# CACHE KEY — same error shape = same diagnosis
# ════════════════════════════════

def _build_cache_key(failure_data: dict) -> str:
    """
    Build a stable cache key from the parts of a failure
    that actually matter for diagnosis. Two failures with
    the same status_code + error pattern should hit the
    same cached diagnosis instead of calling Groq twice.
    """
    key_parts = (
        f"{failure_data.get('source')}|"
        f"{failure_data.get('status_code')}|"
        f"{failure_data.get('error_message')}"
    )
    hashed = hashlib.sha256(key_parts.encode()).hexdigest()[:16]
    return f"ai_diagnosis:{hashed}"


# ════════════════════════════════
# MAIN ENTRY POINT
# ════════════════════════════════

async def diagnose_failure(
    endpoint_id: str,
    source: str,
    source_id: str,
    failure_data: dict
) -> dict:
    """
    Diagnose a failure using AI, with caching.

    failure_data should include:
        source, provider, status_code, response_time_ms,
        error_message, consecutive_failures (optional)

    Returns:
        {
            "likely_cause": str,
            "severity": "low/medium/high/critical",
            "fix": str,
            "code_hint": str | None,
            "from_cache": bool
        }
    """
    cache_key = _build_cache_key(failure_data)

    # ── Check Redis cache first ──
    cached = redis_client.get(cache_key)
    if cached:
        logger.info(f"AI diagnosis cache HIT: {cache_key}")
        diagnosis = json.loads(cached)
        diagnosis["from_cache"] = True

        await broadcast("ai_diagnosis_ready", {
            "endpoint_id": endpoint_id,
            "source": source,
            "source_id": source_id,
            "likely_cause": diagnosis["likely_cause"],
            "severity": diagnosis["severity"],
            "fix": diagnosis["fix"],
            "from_cache": True,
        })

        return diagnosis

    logger.info(f"AI diagnosis cache MISS — calling Groq: {cache_key}")

    # ── Cache miss — call Groq ──
    diagnosis = await _call_groq_for_diagnosis(failure_data)
    diagnosis["from_cache"] = False

    # Cache the result (without from_cache flag, that's per-call)
    cache_value = {k: v for k, v in diagnosis.items() if k != "from_cache"}
    redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(cache_value))

    # Save permanently to Supabase too — cache expires, this doesn't
    try:
        await save_ai_diagnosis({
            "endpoint_id": endpoint_id,
            "source": source,
            "source_id": source_id,
            "likely_cause": diagnosis["likely_cause"],
            "severity": diagnosis["severity"],
            "suggested_fix": diagnosis["fix"],
            "code_hint": diagnosis.get("code_hint"),
            "cache_key": cache_key,
        })
    except Exception as e:
        logger.error(f"Failed to save AI diagnosis to database: {e}")

    # ── Phase 5: broadcast the fresh diagnosis ──
    await broadcast("ai_diagnosis_ready", {
        "endpoint_id": endpoint_id,
        "source": source,
        "source_id": source_id,
        "likely_cause": diagnosis["likely_cause"],
        "severity": diagnosis["severity"],
        "fix": diagnosis["fix"],
        "from_cache": False,
    })

    return diagnosis


# ════════════════════════════════
# GROQ API CALL
# ════════════════════════════════

async def _call_groq_for_diagnosis(failure_data: dict) -> dict:
    """Build the prompt, call Groq, parse the JSON response"""

    prompt = f"""You are a webhook reliability expert helping a developer debug a failure.

Failure details:
- Source: {failure_data.get('source', 'unknown')}
- Provider: {failure_data.get('provider', 'unknown')}
- Status Code: {failure_data.get('status_code', 'No response received')}
- Response Time: {failure_data.get('response_time_ms', 'N/A')}ms
- Error Message: {failure_data.get('error_message', 'Unknown error')}
- Consecutive Failures: {failure_data.get('consecutive_failures', 1)}

Respond with ONLY a JSON object, no other text, no markdown formatting, in exactly this shape:
{{
    "likely_cause": "one or two sentences explaining the most probable cause",
    "severity": "low" or "medium" or "high" or "critical",
    "fix": "one or two sentences with a specific, actionable fix",
    "code_hint": "a short code snippet if relevant, or null if not applicable"
}}"""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )

        raw_text = response.choices[0].message.content
        return _parse_ai_json(raw_text)

    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        return {
            "likely_cause": "Could not generate AI diagnosis right now.",
            "severity": "medium",
            "fix": "Check the raw error message and server logs manually.",
            "code_hint": None,
        }


def _parse_ai_json(text: str) -> dict:
    """
    Parse Groq's JSON response safely. LLMs sometimes wrap
    JSON in markdown code fences or add stray text — handle
    both the clean case and the messy case.
    """
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        parsed = json.loads(text)
        # Ensure all expected keys exist, even if model omitted one
        return {
            "likely_cause": parsed.get("likely_cause", "Unknown cause"),
            "severity": parsed.get("severity", "medium"),
            "fix": parsed.get("fix", "No specific fix suggested"),
            "code_hint": parsed.get("code_hint"),
        }
    except json.JSONDecodeError:
        logger.warning(f"Could not parse AI response as JSON: {text[:200]}")
        return {
            "likely_cause": "AI response could not be parsed.",
            "severity": "medium",
            "fix": "Check the raw error message manually.",
            "code_hint": None,
        }