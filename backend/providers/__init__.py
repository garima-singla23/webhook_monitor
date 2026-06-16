# providers/__init__.py
# ─────────────────────────────────────────────
# Provider registry
# Maps provider name to provider class
# ─────────────────────────────────────────────

from .razorpay import RazorpayProvider
from .stripe import StripeProvider
from .github import GitHubProvider, GenericProvider

# Registry: provider name → provider instance
PROVIDERS = {
    "razorpay": RazorpayProvider(),
    "stripe": StripeProvider(),
    "github": GitHubProvider(),
    "generic": GenericProvider(),
}


def get_provider(provider_name: str):
    """Get provider by name, fallback to generic"""
    return PROVIDERS.get(provider_name, GenericProvider())