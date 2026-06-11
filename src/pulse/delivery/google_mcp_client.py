"""HTTP client for the hosted Google delivery API on Railway."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from pulse.config import (
    GoogleMcpDeliveryConfig,
    GoogleMcpEndpointsConfig,
    load_mcp_delivery,
    resolve_config_dir,
)


class DeliveryError(Exception):
    """Base class for delivery client errors."""


class MissingDeliveryApiKeyError(DeliveryError):
    """Raised when the configured API key environment variable is unset."""


class DeliveryAuthError(DeliveryError):
    """Raised when the delivery API rejects the API key (401/403)."""


class DeliveryApiError(DeliveryError):
    """Raised for other delivery API or transport failures."""


@dataclass(frozen=True)
class AppendResult:
    document_id: str
    appended_chars: int


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    message_id: str
    to: str
    subject: str


def _parse_json_response(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeliveryApiError("delivery API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DeliveryApiError("delivery API response must be a JSON object")
    return payload


class GoogleMcpClient:
    """HTTPS client for Docs append and Gmail draft endpoints.

    Idempotency for weekly runs is enforced by the run ledger (Phase 6), not by
    the hosted API — callers must check the ledger before append or draft calls.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        endpoints: GoogleMcpEndpointsConfig | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise MissingDeliveryApiKeyError("delivery API key must be a non-empty string")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.endpoints = endpoints or GoogleMcpEndpointsConfig()
        self.timeout = timeout

    @classmethod
    def from_config(cls, config_dir: str | os.PathLike[str] | None = None) -> GoogleMcpClient:
        """Build a client from ``config/mcp-servers.json`` and environment variables."""
        from pathlib import Path

        resolved = resolve_config_dir(None if config_dir is None else Path(config_dir))
        mcp_config = load_mcp_delivery(resolved)
        delivery = mcp_config.google_mcp_delivery
        base_url = os.getenv("GOOGLE_MCP_BASE_URL", delivery.base_url).rstrip("/")
        api_key = os.getenv(delivery.api_key_env)
        if not api_key:
            raise MissingDeliveryApiKeyError(
                f"{delivery.api_key_env} is not set; required for delivery API calls"
            )
        return cls(
            base_url=base_url,
            api_key=api_key,
            endpoints=delivery.endpoints,
        )

    @classmethod
    def from_delivery_config(
        cls,
        delivery: GoogleMcpDeliveryConfig,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> GoogleMcpClient:
        """Build a client from an explicit delivery config (useful in tests)."""
        resolved_key = api_key if api_key is not None else os.getenv(delivery.api_key_env)
        if not resolved_key:
            raise MissingDeliveryApiKeyError(
                f"{delivery.api_key_env} is not set; required for delivery API calls"
            )
        resolved_base = (base_url or os.getenv("GOOGLE_MCP_BASE_URL") or delivery.base_url).rstrip(
            "/"
        )
        return cls(
            base_url=resolved_base,
            api_key=resolved_key,
            endpoints=delivery.endpoints,
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        require_api_key: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        body: bytes | None = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if require_api_key:
            headers["X-API-Key"] = self.api_key

        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return _parse_json_response(response.read())
        except urllib.error.HTTPError as exc:
            detail = self._http_error_detail(exc)
            if exc.code in {401, 403}:
                raise DeliveryAuthError(
                    f"delivery API authentication failed ({exc.code}): {detail}"
                ) from exc
            raise DeliveryApiError(f"delivery API request failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise DeliveryApiError(f"delivery API transport error: {exc.reason}") from exc

    @staticmethod
    def _http_error_detail(exc: urllib.error.HTTPError) -> str:
        try:
            payload = _parse_json_response(exc.read())
        except DeliveryApiError:
            return exc.reason or "unknown error"
        message = payload.get("detail") or payload.get("message") or payload.get("error")
        if message:
            return str(message)
        return exc.reason or "unknown error"

    def health_check(self) -> bool:
        """Return True when ``GET /health`` reports ``status: ok``."""
        payload = self._request("GET", self.endpoints.health)
        return payload.get("status") == "ok"

    def append_to_doc(self, doc_id: str, content: str) -> AppendResult:
        """Append plain-text content to a Google Doc via ``POST /append_to_doc``."""
        if not doc_id or not doc_id.strip():
            raise ValueError("doc_id must be a non-empty string")
        if not content:
            raise ValueError("content must be non-empty")

        payload = self._request(
            "POST",
            self.endpoints.append_to_doc,
            payload={"doc_id": doc_id, "content": content},
            require_api_key=True,
        )
        if payload.get("status") != "success":
            detail = payload.get("detail") or payload.get("message") or payload
            raise DeliveryApiError(f"append_to_doc failed: {detail}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise DeliveryApiError("append_to_doc response missing result object")

        document_id = result.get("document_id")
        appended_chars = result.get("appended_chars")
        if not document_id or appended_chars is None:
            raise DeliveryApiError(
                "append_to_doc result must include document_id and appended_chars"
            )

        return AppendResult(document_id=str(document_id), appended_chars=int(appended_chars))

    def create_email_draft(self, to: str, subject: str, body: str) -> DraftResult:
        """Create a Gmail draft via ``POST /create_email_draft`` (plain-text body)."""
        if not to or not to.strip():
            raise ValueError("to must be a non-empty email address")
        if not subject or not subject.strip():
            raise ValueError("subject must be a non-empty string")
        if not body:
            raise ValueError("body must be non-empty")

        payload = self._request(
            "POST",
            self.endpoints.create_email_draft,
            payload={"to": to, "subject": subject, "body": body},
            require_api_key=True,
        )
        if payload.get("status") != "success":
            detail = payload.get("detail") or payload.get("message") or payload
            raise DeliveryApiError(f"create_email_draft failed: {detail}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise DeliveryApiError("create_email_draft response missing result object")

        draft_id = result.get("draft_id")
        message_id = result.get("message_id")
        if not draft_id or not message_id:
            raise DeliveryApiError("create_email_draft result must include draft_id and message_id")

        return DraftResult(
            draft_id=str(draft_id),
            message_id=str(message_id),
            to=str(result.get("to", to)),
            subject=str(result.get("subject", subject)),
        )

    def create_email_drafts(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
    ) -> list[DraftResult]:
        """Create one draft per recipient (hosted API accepts a single ``to`` per request)."""
        if not to:
            raise ValueError("to must contain at least one recipient email")
        return [self.create_email_draft(recipient, subject, body) for recipient in to]
