#!/usr/bin/env python3
"""Render PulseReport JSON into Doc section text and Gmail teaser payloads (Phase 3)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pulse.config import load_config
from pulse.pipeline.models import PulseReport
from pulse.render.email import render_email_teaser
from pulse.render.report import render_doc_report


def _load_report(path: Path) -> PulseReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PulseReport.model_validate(raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render PulseReport to Doc section text + email JSON"
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("report.json"),
        help="Input PulseReport JSON (default: report.json)",
    )
    parser.add_argument(
        "--doc-out",
        type=Path,
        default=Path("doc_section.json"),
        help="Output DocStructuredReport JSON (default: doc_section.json)",
    )
    parser.add_argument(
        "--email-out",
        type=Path,
        default=Path("email.json"),
        help="Output EmailPayload JSON (default: email.json)",
    )
    parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    args = parser.parse_args()

    if not args.report.exists():
        print(f"ERROR: report file not found: {args.report}", file=sys.stderr)
        return 1

    try:
        report = _load_report(args.report)
        config = load_config(include_mcp=False)
        product = config.get_product(args.product)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    doc_report = render_doc_report(
        report,
        display_name=product.display_name,
        document_id=product.google_doc.document_id,
    )
    email_payload = render_email_teaser(
        report,
        display_name=product.display_name,
        to=product.stakeholders.to,
        cc=product.stakeholders.cc,
        document_id=product.google_doc.document_id,
    )

    args.doc_out.write_text(doc_report.model_dump_json(indent=2), encoding="utf-8")
    args.email_out.write_text(email_payload.model_dump_json(indent=2), encoding="utf-8")

    print(f"section_anchor={doc_report.section_anchor}")
    print(f"content_chars={len(doc_report.content)}")
    print(f"email_subject={email_payload.subject!r}")
    print(f"doc_out={args.doc_out.resolve()}")
    print(f"email_out={args.email_out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
