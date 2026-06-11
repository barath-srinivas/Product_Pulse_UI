"""Hosted Google delivery API client (Docs append, Gmail drafts)."""

from pulse.delivery.google_mcp_client import (
    AppendResult,
    DeliveryApiError,
    DeliveryAuthError,
    DeliveryError,
    DraftResult,
    GoogleMcpClient,
    MissingDeliveryApiKeyError,
)

__all__ = [
    "AppendResult",
    "DeliveryApiError",
    "DeliveryAuthError",
    "DeliveryError",
    "DraftResult",
    "GoogleMcpClient",
    "MissingDeliveryApiKeyError",
]
