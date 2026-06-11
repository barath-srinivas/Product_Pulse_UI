#!/usr/bin/env python3
"""Smoke-test Docs append via hosted Google delivery API (Phase 4)."""

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
from pulse.render.models import DocStructuredReport


def _load_doc_section(path: Path) -> DocStructuredReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return DocStructuredReport.model_validate(raw)


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Append Doc section content via hosted /append_to_doc API"
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("tests/fixtures/doc_section_groww_sample.json"),
        help=(
            "DocStructuredReport JSON fixture "
            "(default: tests/fixtures/doc_section_groww_sample.json)"
        ),
    )
    parser.add_argument(
        "--doc-section",
        type=Path,
        help="DocStructuredReport JSON from render_report.py (overrides --fixture)",
    )
    parser.add_argument(
        "--doc-id",
        help="Google Doc id override (default: from fixture or config/products.yaml)",
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

    section_path = args.doc_section or args.fixture
    if not section_path.exists():
        print(f"ERROR: doc section file not found: {section_path}", file=sys.stderr)
        return 1

    try:
        doc_section = _load_doc_section(section_path)
        config = load_config()
        product = config.get_product(args.product)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    doc_id = args.doc_id or product.google_doc.document_id
    if not doc_id or doc_id.startswith("<"):
        print(
            "ERROR: set --doc-id or configure google_doc.document_id in config/products.yaml",
            file=sys.stderr,
        )
        return 1

    print(f"section_anchor={doc_section.section_anchor}")
    print(f"content_chars={len(doc_section.content)}")
    print(f"doc_id={doc_id}")

    if args.dry_run:
        print("dry_run=true (no HTTP call)")
        return 0

    try:
        result = client.append_to_doc(doc_id=doc_id, content=doc_section.content)
    except DeliveryAuthError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Check GOOGLE_MCP_API_KEY matches Railway API_KEY.", file=sys.stderr)
        return 1
    except DeliveryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"document_id={result.document_id}")
    print(f"appended_chars={result.appended_chars}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
