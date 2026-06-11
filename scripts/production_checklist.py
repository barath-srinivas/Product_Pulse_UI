#!/usr/bin/env python3
"""Phase 9 production go-live checklist helper (draft-mode + scheduler)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from pulse.config import (
    ProductConfig,
    current_iso_week,
    load_config,
    load_pulse_config,
    resolve_config_dir,
)
from pulse.ledger.store import LedgerStore

PLACEHOLDER_MARKERS = ("<", "YOUR_", "you@example.com", "example.com")
EXPECTED_CRON = "0 8 * * 1"

CHECKS = [
    ("9.1", "Production config: products.yaml from products.production.example.yaml"),
    ("9.2", "Email mode: delivery.email_mode=draft (hosted API v1)"),
    ("9.3", "Scheduler: Monday 08:00 IST documented and registered"),
    ("9.4", "First production run: pulse run completes with status=completed"),
    ("9.5", "Ledger audit: doc_document_id + gmail drafts recorded"),
    ("9.6", "Stakeholder sign-off: production Doc section + drafts approved"),
]


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in PLACEHOLDER_MARKERS)


def _load_production_products(config_dir: Path) -> dict[str, ProductConfig]:
    path = config_dir / "products.production.example.yaml"
    if not path.exists():
        raise FileNotFoundError(f"missing production template: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    products_raw = raw.get("products", {})
    return {pid: ProductConfig.model_validate(cfg) for pid, cfg in products_raw.items()}


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Print Phase 9 production checklist status (draft-mode)"
    )
    parser.add_argument("--product", default="groww")
    parser.add_argument("--week", help="ISO week to inspect (default: current IST week)")
    args = parser.parse_args()

    config_dir = resolve_config_dir()
    products_path = config_dir / "products.yaml"
    using_production_yaml = products_path.exists()

    warnings: list[str] = []
    errors: list[str] = []

    try:
        config = load_config()
        pulse = load_pulse_config(config_dir)
        product = config.get_product(args.product)
        prod_template = _load_production_products(config_dir).get(args.product)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    iso_week = args.week or current_iso_week(pulse.timezone)
    ledger = LedgerStore()
    record = ledger.get_completed_run(args.product, iso_week)

    print("=== Phase 9 production checklist (draft-mode) ===\n")
    for step, description in CHECKS:
        print(f"[ ] {step} {description}")

    print("\n--- Automated preflight ---")
    if using_production_yaml:
        products_label = "products.yaml"
    else:
        products_label = "products.example.yaml (fallback)"
    print(f"config_products={products_label}")
    print(f"email_mode={pulse.delivery.email_mode}")
    print(f"schedule_cron={pulse.schedule.cron}")
    print(f"timezone={pulse.timezone}")
    print(f"document_id={product.google_doc.document_id}")
    print(f"doc_title={product.google_doc.title}")
    print(f"stakeholders_to={product.stakeholders.to}")
    print(f"stakeholders_cc={product.stakeholders.cc}")
    print(f"iso_week={iso_week}")
    print(f"ledger_completed={'yes' if record else 'no'}")
    if record:
        print(f"run_id={record.run_id}")
        print(f"review_count={record.review_count}")
        print(f"doc_document_id={record.doc_document_id}")
        print(f"gmail_draft_count={len(record.gmail_drafts)}")

    if pulse.delivery.email_mode != "draft":
        warnings.append(
            "email_mode is not 'draft' — hosted API v1 only supports drafts; "
            "revert to draft for production until send endpoint exists"
        )
    if pulse.schedule.cron != EXPECTED_CRON:
        warnings.append(
            f"schedule.cron={pulse.schedule.cron!r} differs from expected {EXPECTED_CRON!r}"
        )
    if _looks_like_placeholder(product.google_doc.document_id):
        errors.append("document_id looks like a placeholder — set production Google Doc id")
    for email in product.stakeholders.to:
        if _looks_like_placeholder(email):
            errors.append(f"stakeholder email looks like a placeholder: {email}")
    if not product.stakeholders.to:
        errors.append("stakeholders.to is empty")
    if "staging" in product.google_doc.title.lower():
        warnings.append("doc title contains 'staging' — confirm production Doc")
    if not using_production_yaml:
        warnings.append(
            "copy config/products.production.example.yaml to config/products.yaml for production"
        )
    if prod_template and product.google_doc.document_id == prod_template.google_doc.document_id:
        print("production_template_doc_id=matches products.production.example.yaml")

    import os

    for env_var in ("GROQ_API_KEY", "GOOGLE_MCP_API_KEY"):
        print(f"{env_var}={'set' if os.getenv(env_var) else 'MISSING'}")

    for message in warnings:
        print(f"\nWARNING: {message}", file=sys.stderr)
    for message in errors:
        print(f"\nERROR: {message}", file=sys.stderr)

    print("\nScheduler: see docs/scheduler.md")
    print("Manual sign-off (9.6): _____________________  Date: __________")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
