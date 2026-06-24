# services/alerting.py
# ─────────────────────────────────────────────
# Sends alerts to Slack and email when log_alert()
# is called from health_checker.py.
#
# Both channels fire in parallel via asyncio.gather,
# and a failure in one channel never blocks the other —
# each is wrapped in its own try/except.
#
# Every delivery attempt (success or failure) is logged
# to alert_deliveries, separate from alerts_log which
# only records that the alert CONDITION occurred.
# ─────────────────────────────────────────────

import asyncio
import logging
import httpx
import resend

from config import settings
from database import save_alert_delivery

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key

# Map alert_type to a Slack emoji + color, used for formatting
SEVERITY_STYLE = {
    "down": {"emoji": "🔴", "color": "#dc2626"},
    "recovered": {"emoji": "✅", "color": "#16a34a"},
}


async def send_alert(
    endpoint: dict,
    alert_id: str | None,
    alert_type: str,
    message: str
):
    """
    Main entry point — called from log_alert() in health_checker.py
    right after the alert condition is saved to alerts_log.

    Fires Slack and email in parallel. Neither channel blocks
    the other; both are logged to alert_deliveries regardless
    of outcome.
    """
    endpoint_id = endpoint["id"]
    logger.error("DEBUG: send_alert ENTERED")

    logger.error(
        f"DEBUG settings -> "
        f"slack={bool(settings.slack_webhook_url)}, "
        f"resend={bool(settings.resend_api_key)}, "
        f"email_to={bool(settings.alert_email_to)}"
    )

    logger.error(
        f"DEBUG endpoint -> "
        f"slack_enabled={endpoint.get('slack_alerts_enabled', True)}, "
        f"email_enabled={endpoint.get('email_alerts_enabled', True)}"
    )

    tasks = []

    if endpoint.get("slack_alerts_enabled", True) and settings.slack_webhook_url:
        tasks.append(_send_slack(endpoint, alert_id, alert_type, message))

    if endpoint.get("email_alerts_enabled", True) and settings.resend_api_key and settings.alert_email_to:
        tasks.append(_send_email(endpoint, alert_id, alert_type, message))

    if not tasks:
        logger.warning(
            f"No alert channels configured/enabled for endpoint "
            f"'{endpoint.get('name')}' — alert was logged but not delivered anywhere"
        )
        return

    # return_exceptions=True — same pattern as Phase 2's
    # asyncio.gather for health checks. One channel's crash
    # should never take down the other.
    await asyncio.gather(*tasks, return_exceptions=True)


# ════════════════════════════════
# SLACK
# ════════════════════════════════
logger.error("DEBUG: _send_slack ENTERED")
async def _send_slack(
    endpoint: dict,
    alert_id: str | None,
    alert_type: str,
    message: str
):
    style = SEVERITY_STYLE.get(alert_type, {"emoji": "⚠️", "color": "#6b7280"})

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{style['emoji']} Webhook Monitor Alert"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Endpoint:*\n{endpoint.get('name')}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{alert_type.upper()}"},
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            }
        ]
    }

    success = False
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            success = response.status_code == 200
            if not success:
                error_message = f"Slack returned {response.status_code}: {response.text[:200]}"
    except Exception as e:
        error_message = str(e)

    if success:
        logger.info(f"Slack alert sent for endpoint '{endpoint.get('name')}'")
    else:
        logger.error(f"Slack alert FAILED for endpoint '{endpoint.get('name')}': {error_message}")

    try:
        await save_alert_delivery({
            "alert_id": alert_id,
            "endpoint_id": endpoint["id"],
            "channel": "slack",
            "success": success,
            "error_message": error_message,
        })
    except Exception as e:
        logger.error(f"Failed to log Slack delivery attempt: {e}")


# ════════════════════════════════
# EMAIL
# ════════════════════════════════
logger.error("DEBUG: _send_email ENTERED")
async def _send_email(
    endpoint: dict,
    alert_id: str | None,
    alert_type: str,
    message: str
):
    style = SEVERITY_STYLE.get(alert_type, {"emoji": "⚠️", "color": "#6b7280"})
    subject = f"{style['emoji']} Webhook Monitor: {endpoint.get('name')} — {alert_type.upper()}"

    html = f"""
    <div style="font-family: sans-serif; max-width: 500px;">
      <h2 style="color: {style['color']};">{style['emoji']} {alert_type.upper()}</h2>
      <p><strong>Endpoint:</strong> {endpoint.get('name')}</p>
      <p><strong>URL:</strong> {endpoint.get('url')}</p>
      <hr style="border: none; border-top: 1px solid #e5e7eb;" />
      <p>{message}</p>
    </div>
    """

    success = False
    error_message = None

    try:
        # resend's SDK is synchronous, so run it in a thread
        # to avoid blocking the async event loop
        await asyncio.to_thread(
            resend.Emails.send,
            {
                "from": settings.alert_email_from,
                "to": settings.alert_email_to,
                "subject": subject,
                "html": html,
            }
        )
        success = True
    except Exception as e:
        error_message = str(e)

    if success:
        logger.info(f"Email alert sent for endpoint '{endpoint.get('name')}'")
    else:
        logger.error(f"Email alert FAILED for endpoint '{endpoint.get('name')}': {error_message}")

    try:
        await save_alert_delivery({
            "alert_id": alert_id,
            "endpoint_id": endpoint["id"],
            "channel": "email",
            "success": success,
            "error_message": error_message,
        })
    except Exception as e:
        logger.error(f"Failed to log email delivery attempt: {e}")