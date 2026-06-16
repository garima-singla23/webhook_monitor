# providers/base.py
# ─────────────────────────────────────────────
# Base class all providers inherit from
# Defines standard interface
# ─────────────────────────────────────────────

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """
    Base class for webhook providers.
    Each provider (Razorpay, Stripe, GitHub)
    inherits this and implements parse().
    """

    @abstractmethod
    def parse(self, payload: dict) -> dict:
        """
        Parse raw webhook payload into standard format.
        Returns dict with these keys:
        - event_type: str
        - readable: str (human readable description)
        - metadata: dict (provider specific data)
        """
        pass

    def safe_parse(self, payload: dict) -> dict:
        """
        Wraps parse() with error handling.
        If parsing fails, returns generic response.
        """
        try:
            return self.parse(payload)
        except Exception as e:
            return {
                "event_type": "unknown",
                "readable": "Could not parse payload",
                "metadata": {},
                "parse_error": str(e)
            }