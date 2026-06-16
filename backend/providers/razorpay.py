# providers/razorpay.py
# ─────────────────────────────────────────────
# Parses Razorpay webhook payloads
# Converts raw JSON to human readable format
# ─────────────────────────────────────────────

from .base import BaseProvider


class RazorpayProvider(BaseProvider):

    def parse(self, payload: dict) -> dict:
        event = payload.get("event", "unknown")
        entity = self._get_entity(payload)

        return {
            "event_type": event,
            "readable": self._get_readable(event, entity),
            "metadata": {
                "amount": entity.get("amount", 0) / 100,
                "currency": entity.get("currency", "INR"),
                "payment_id": entity.get("id"),
                "order_id": entity.get("order_id"),
                "method": entity.get("method"),
                "status": entity.get("status"),
                "email": entity.get("email"),
                "contact": entity.get("contact"),
                "vpa": entity.get("vpa"),  # UPI ID
            }
        }

    def _get_entity(self, payload: dict) -> dict:
        """Extract the main entity from payload"""
        payload_data = payload.get("payload", {})

        # Try payment entity first
        if "payment" in payload_data:
            return payload_data["payment"].get("entity", {})

        # Try order entity
        if "order" in payload_data:
            return payload_data["order"].get("entity", {})

        # Try refund entity
        if "refund" in payload_data:
            return payload_data["refund"].get("entity", {})

        return {}

    def _get_readable(self, event: str, entity: dict) -> str:
        """Convert event to human readable description"""
        amount = entity.get("amount", 0) / 100
        currency = entity.get("currency", "INR")
        method = entity.get("method", "")

        messages = {
            "payment.captured":
                f" Payment of {currency} {amount:.2f} captured via {method}",

            "payment.failed":
                f" Payment of {currency} {amount:.2f} failed",

            "payment.authorized":
                f" Payment of {currency} {amount:.2f} authorized",

            "refund.created":
                f" Refund of {currency} {amount:.2f} initiated",

            "refund.processed":
                f" Refund of {currency} {amount:.2f} processed",

            "order.paid":
                f" Order paid: {currency} {amount:.2f}",

            "subscription.activated":
                f" Subscription activated",

            "subscription.cancelled":
                f" Subscription cancelled",
        }

        return messages.get(event, f"📌 Event: {event}")