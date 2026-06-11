#!/usr/bin/env python3
"""Smoke-test Gmail draft creation via hosted Google delivery API (Phase 5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from pulse.config import load_config
from pulse.delivery.google_mcp_client import (
    DeliveryAuthError,
    DeliveryError,
    GoogleMcpClient,
    MissingDeliveryApiKeyError,
)
from pulse.render.models import EmailPayload


def _load_email_payload(path: Path) -> EmailPayload:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EmailPayload.model_validate(raw)


def _resolve_body_text(body_text: str, document_id: str) -> str:
    return body_text.replace("<GOOGLE_DOC_ID>", document_id)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Create Gmail drafts via hosted /create_email_draft API"
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/email_groww_sample.json"),
        help=(
            "EmailPayload JSON fixture "
            "(default: tests/fixtures/email_groww_sample.json)"
        ),
    )
    parser.add_argument(
        "--email",
        type=Path,
        help="EmailPayload JSON from render_report.py (overrides --fixture)",
    )
    parser.add_argument(
        "--to",
        action="append",
        dest="recipients",
        metavar="EMAIL",
        help="Recipient override (repeatable; default: stakeholders.to from config)",
    )
    parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Only run GET /health and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print payload summary without calling the delivery API",
    )
    args = parser.parse_args()

    try:
        client = GoogleMcpClient.from_config()
    except MissingDeliveryApiKeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Set GOOGLE_MCP_API_KEY in .env (must match Railway API_KEY).", file=sys.stderr)
        return 1

    if args.health_only:
        try:
            ok = client.health_check()
        except DeliveryError as exc:
            print(f"ERROR: health check failed: {exc}", file=sys.stderr)
            return 1
        print(f"health_ok={ok}")
        return 0 if ok else 1

    email_path = args.email or args.fixture
    if not email_path.exists():
        print(f"ERROR: email payload file not found: {email_path}", file=sys.stderr)
        return 1

    try:
        email_payload = _load_email_payload(email_path)
        config = load_config()
        product = config.get_product(args.product)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if config.pulse.delivery.email_mode != "draft":
        print(
            "WARNING: delivery.email_mode is not 'draft'; hosted API only supports drafts",
            file=sys.stderr,
        )

    recipients = args.recipients or product.stakeholders.to
    if not recipients:
        print(
            "ERROR: set --to or configure stakeholders.to in config/products.yaml",
            file=sys.stderr,
        )
        return 1

    document_id = product.google_doc.document_id
    if not document_id or document_id.startswith("<"):
        print(
            "ERROR: configure google_doc.document_id in config/products.yaml",
            file=sys.stderr,
        )
        return 1

    body_text = _resolve_body_text(email_payload.body_text, document_id)

    print(f"idempotency_key={email_payload.idempotency_key}")
    print(f"subject={email_payload.subject!r}")
    print(f"recipients={recipients}")
    print(f"body_chars={len(body_text)}")

    if args.dry_run:
        print("dry_run=true (no HTTP call)")
        return 0

    try:
        results = client.create_email_drafts(
            to=recipients,
            subject=email_payload.subject,
            body=body_text,
        )
    except DeliveryAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Check GOOGLE_MCP_API_KEY matches Railway API_KEY.", file=sys.stderr)
        return 1
    except DeliveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(
            f"draft_created to={result.to} draft_id={result.draft_id} "
            f"message_id={result.message_id}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
