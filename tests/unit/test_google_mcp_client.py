"""Unit tests for hosted Google delivery API client (Phases 4–5)."""

from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from pulse.config import GoogleMcpDeliveryConfig, GoogleMcpEndpointsConfig
from pulse.delivery.google_mcp_client import (
    AppendResult,
    DeliveryApiError,
    DeliveryAuthError,
    DraftResult,
    GoogleMcpClient,
    MissingDeliveryApiKeyError,
)

_BASE_URL = "https://web-production-facdf.up.railway.app"
_API_KEY = "test-api-key"
_ENDPOINTS = GoogleMcpEndpointsConfig()


def _client() -> GoogleMcpClient:
    return GoogleMcpClient(base_url=_BASE_URL, api_key=_API_KEY, endpoints=_ENDPOINTS)


def _mock_urlopen(response_body: dict, *, status: int = 200) -> patch:
    payload = json.dumps(response_body).encode("utf-8")

    def _urlopen(request, timeout=None):
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "error",
                hdrs=None,
                fp=io.BytesIO(payload),
            )
        return io.BytesIO(payload)

    return patch("pulse.delivery.google_mcp_client.urllib.request.urlopen", side_effect=_urlopen)


def test_append_to_doc_success() -> None:
    client = _client()
    content = "Groww pulse section\n"
    with _mock_urlopen(
        {
            "status": "success",
            "result": {
                "document_id": "doc-123",
                "appended_chars": len(content),
                "replies": [],
            },
        }
    ):
        result = client.append_to_doc("doc-123", content)

    assert result == AppendResult(document_id="doc-123", appended_chars=len(content))


def test_append_to_doc_sends_api_key_and_payload() -> None:
    client = _client()
    captured: dict = {}

    def _urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return io.BytesIO(
            json.dumps(
                {
                    "status": "success",
                    "result": {"document_id": "doc-1", "appended_chars": 4, "replies": []},
                }
            ).encode("utf-8")
        )

    with patch("pulse.delivery.google_mcp_client.urllib.request.urlopen", side_effect=_urlopen):
        client.append_to_doc("doc-1", "test")

    assert captured["url"] == f"{_BASE_URL}/append_to_doc"
    assert captured["headers"]["X-api-key"] == _API_KEY
    assert captured["body"] == {"doc_id": "doc-1", "content": "test"}


@pytest.mark.parametrize("status", [401, 403])
def test_append_to_doc_auth_errors(status: int) -> None:
    client = _client()
    with _mock_urlopen({"detail": "Invalid or missing X-API-Key."}, status=status):
        with pytest.raises(DeliveryAuthError, match="authentication failed"):
            client.append_to_doc("doc-1", "content")


def test_append_to_doc_http_error() -> None:
    client = _client()
    with _mock_urlopen({"detail": "Google Docs API error"}, status=502):
        with pytest.raises(DeliveryApiError, match="502"):
            client.append_to_doc("doc-1", "content")


def test_append_to_doc_non_success_status() -> None:
    client = _client()
    with _mock_urlopen({"status": "error", "message": "append failed"}):
        with pytest.raises(DeliveryApiError, match="append_to_doc failed"):
            client.append_to_doc("doc-1", "content")


def test_append_to_doc_missing_result_fields() -> None:
    client = _client()
    with _mock_urlopen({"status": "success", "result": {"document_id": "doc-1"}}):
        with pytest.raises(DeliveryApiError, match="document_id and appended_chars"):
            client.append_to_doc("doc-1", "content")


def test_append_to_doc_rejects_empty_inputs() -> None:
    client = _client()
    with pytest.raises(ValueError, match="doc_id"):
        client.append_to_doc("", "content")
    with pytest.raises(ValueError, match="content"):
        client.append_to_doc("doc-1", "")


def test_health_check_ok() -> None:
    client = _client()
    with _mock_urlopen({"status": "ok"}):
        assert client.health_check() is True


def test_health_check_not_ok() -> None:
    client = _client()
    with _mock_urlopen({"status": "degraded"}):
        assert client.health_check() is False


def test_missing_api_key_on_init() -> None:
    with pytest.raises(MissingDeliveryApiKeyError):
        GoogleMcpClient(base_url=_BASE_URL, api_key="")


def test_from_delivery_config_uses_explicit_api_key() -> None:
    delivery = GoogleMcpDeliveryConfig.model_validate(
        {
            "baseUrl": _BASE_URL,
            "apiKeyEnv": "GOOGLE_MCP_API_KEY",
            "endpoints": {
                "health": "/health",
                "appendToDoc": "/append_to_doc",
                "createEmailDraft": "/create_email_draft",
            },
        }
    )
    client = GoogleMcpClient.from_delivery_config(delivery, api_key="explicit-key")
    assert client.api_key == "explicit-key"


def test_from_delivery_config_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    delivery = GoogleMcpDeliveryConfig.model_validate(
        {
            "baseUrl": _BASE_URL,
            "apiKeyEnv": "GOOGLE_MCP_API_KEY",
        }
    )
    monkeypatch.setenv("GOOGLE_MCP_BASE_URL", "https://custom.example.com")
    client = GoogleMcpClient.from_delivery_config(delivery, api_key="key")
    assert client.base_url == "https://custom.example.com"


def test_from_config_missing_api_key(monkeypatch: pytest.MonkeyPatch, config_dir) -> None:
    monkeypatch.delenv("GOOGLE_MCP_API_KEY", raising=False)
    with pytest.raises(MissingDeliveryApiKeyError, match="GOOGLE_MCP_API_KEY"):
        GoogleMcpClient.from_config(config_dir)


def test_create_email_draft_success() -> None:
    client = _client()
    body = "Teaser body with doc link.\n"
    with _mock_urlopen(
        {
            "status": "success",
            "result": {
                "draft_id": "draft-1",
                "message_id": "msg-1",
                "to": "you@example.com",
                "subject": "Groww Weekly Review Pulse — 2026-W24",
            },
        }
    ):
        result = client.create_email_draft(
            "you@example.com",
            "Groww Weekly Review Pulse — 2026-W24",
            body,
        )

    assert result == DraftResult(
        draft_id="draft-1",
        message_id="msg-1",
        to="you@example.com",
        subject="Groww Weekly Review Pulse — 2026-W24",
    )


def test_create_email_draft_sends_api_key_and_payload() -> None:
    client = _client()
    captured: dict = {}

    def _urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return io.BytesIO(
            json.dumps(
                {
                    "status": "success",
                    "result": {
                        "draft_id": "d1",
                        "message_id": "m1",
                        "to": "a@b.com",
                        "subject": "Subject",
                    },
                }
            ).encode("utf-8")
        )

    with patch("pulse.delivery.google_mcp_client.urllib.request.urlopen", side_effect=_urlopen):
        client.create_email_draft("a@b.com", "Subject", "Body text")

    assert captured["url"] == f"{_BASE_URL}/create_email_draft"
    assert captured["headers"]["X-api-key"] == _API_KEY
    assert captured["body"] == {"to": "a@b.com", "subject": "Subject", "body": "Body text"}


@pytest.mark.parametrize("status", [401, 403])
def test_create_email_draft_auth_errors(status: int) -> None:
    client = _client()
    with _mock_urlopen({"detail": "Invalid or missing X-API-Key."}, status=status):
        with pytest.raises(DeliveryAuthError, match="authentication failed"):
            client.create_email_draft("a@b.com", "Subject", "Body")


def test_create_email_draft_http_error() -> None:
    client = _client()
    with _mock_urlopen({"detail": "Gmail API error"}, status=502):
        with pytest.raises(DeliveryApiError, match="502"):
            client.create_email_draft("a@b.com", "Subject", "Body")


def test_create_email_draft_non_success_status() -> None:
    client = _client()
    with _mock_urlopen({"status": "error", "message": "draft failed"}):
        with pytest.raises(DeliveryApiError, match="create_email_draft failed"):
            client.create_email_draft("a@b.com", "Subject", "Body")


def test_create_email_draft_missing_result_fields() -> None:
    client = _client()
    with _mock_urlopen({"status": "success", "result": {"draft_id": "d1"}}):
        with pytest.raises(DeliveryApiError, match="draft_id and message_id"):
            client.create_email_draft("a@b.com", "Subject", "Body")


def test_create_email_draft_rejects_empty_inputs() -> None:
    client = _client()
    with pytest.raises(ValueError, match="to"):
        client.create_email_draft("", "Subject", "Body")
    with pytest.raises(ValueError, match="subject"):
        client.create_email_draft("a@b.com", "", "Body")
    with pytest.raises(ValueError, match="body"):
        client.create_email_draft("a@b.com", "Subject", "")


def test_create_email_drafts_loops_recipients() -> None:
    client = _client()
    calls: list[str] = []

    def _urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        calls.append(body["to"])
        return io.BytesIO(
            json.dumps(
                {
                    "status": "success",
                    "result": {
                        "draft_id": f"draft-{body['to']}",
                        "message_id": f"msg-{body['to']}",
                        "to": body["to"],
                        "subject": body["subject"],
                    },
                }
            ).encode("utf-8")
        )

    with patch("pulse.delivery.google_mcp_client.urllib.request.urlopen", side_effect=_urlopen):
        results = client.create_email_drafts(
            to=["one@example.com", "two@example.com"],
            subject="Pulse",
            body="Teaser",
        )

    assert calls == ["one@example.com", "two@example.com"]
    assert len(results) == 2
    assert results[0].to == "one@example.com"
    assert results[1].to == "two@example.com"


def test_create_email_drafts_requires_recipients() -> None:
    client = _client()
    with pytest.raises(ValueError, match="at least one recipient"):
        client.create_email_drafts(to=[], subject="Pulse", body="Teaser")
