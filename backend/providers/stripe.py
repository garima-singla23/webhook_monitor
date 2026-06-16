# providers/stripe.py
# ─────────────────────────────────────────────
# Parses Stripe webhook payloads
# ─────────────────────────────────────────────

from .base import BaseProvider


class StripeProvider(BaseProvider):

    def parse(self, payload: dict) -> dict:
        event_type = payload.get("type", "unknown")
        data_object = payload.get("data", {})\
                             .get("object", {})

        return {
            "event_type": event_type,
            "readable": self._get_readable(
                event_type, data_object
            ),
            "metadata": {
                "amount": data_object.get("amount", 0) / 100,
                "currency": data_object.get(
                    "currency", "usd"
                ).upper(),
                "payment_id": data_object.get("id"),
                "status": data_object.get("status"),
                "customer": data_object.get("customer"),
                "email": data_object.get(
                    "billing_details", {}
                ).get("email"),
            }
        }

    def _get_readable(
        self,
        event_type: str,
        obj: dict
    ) -> str:
        amount = obj.get("amount", 0) / 100
        currency = obj.get("currency", "usd").upper()

        messages = {
            "payment_intent.succeeded":
                f" Payment of {currency} {amount:.2f} succeeded",

            "payment_intent.payment_failed":
                f" Payment of {currency} {amount:.2f} failed",

            "charge.succeeded":
                f" Charge of {currency} {amount:.2f} succeeded",

            "charge.refunded":
                f" Charge of {currency} {amount:.2f} refunded",

            "customer.subscription.created":
                f" New subscription created",

            "customer.subscription.deleted":
                f" Subscription cancelled",

            "invoice.paid":
                f" Invoice of {currency} {amount:.2f} paid",

            "invoice.payment_failed":
                f" Invoice payment of {currency} {amount:.2f} failed",
        }

        return messages.get(
            event_type, f" Stripe event: {event_type}"
        )