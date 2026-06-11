#!/usr/bin/env python3
"""Phase 8 staging sign-off checklist helper."""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from pulse.config import current_iso_week, load_config, load_pulse_config, resolve_config_dir
from pulse.ledger.store import LedgerStore

CHECKS = [
    ("8.1", "Staging config: products.yaml uses staging Doc id and dev recipients"),
    ("8.2", "E2E run: pulse run --product groww completes with status=completed"),
    ("8.3", "Idempotency: second pulse run same week prints skipped=true"),
    ("8.4", "Safety audit: pytest tests/unit/test_safety_audit.py passes"),
    ("8.5", "Runbook: docs/runbook.md reviewed by operator"),
    ("8.6", "Stakeholder sign-off: staging Doc section + draft email approved"),
]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Print Phase 8 staging checklist status")
    parser.add_argument("--product", default="groww")
    parser.add_argument("--week", help="ISO week to inspect (default: current IST week)")
    args = parser.parse_args()

    config_dir = resolve_config_dir()
    products_path = config_dir / "products.yaml"
    using_example = not products_path.exists()

    try:
        config = load_config()
        pulse = load_pulse_config(config_dir)
        product = config.get_product(args.product)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    iso_week = args.week or current_iso_week(pulse.timezone)
    ledger = LedgerStore()
    record = ledger.get_completed_run(args.product, iso_week)

    print("=== Phase 8 staging checklist ===\n")
    for step, description in CHECKS:
        print(f"[ ] {step} {description}")

    print("\n--- Automated preflight ---")
    print(f"config_products={'products.example.yaml' if using_example else 'products.yaml'}")
    print(f"email_mode={pulse.delivery.email_mode}")
    print(f"document_id={product.google_doc.document_id}")
    print(f"stakeholders_to={product.stakeholders.to}")
    print(f"iso_week={iso_week}")
    print(f"ledger_completed={'yes' if record else 'no'}")
    if record:
        print(f"run_id={record.run_id}")
        print(f"review_count={record.review_count}")
        print(f"gmail_draft_count={len(record.gmail_drafts)}")

    if pulse.delivery.email_mode != "draft":
        print(
            "\nWARNING: email_mode is not 'draft' — staging should stay draft-only",
            file=sys.stderr,
        )
    if using_example:
        print(
            "\nNOTE: copy config/products.staging.example.yaml to config/products.yaml "
            "for staging sign-off",
            file=sys.stderr,
        )

    print("\nManual sign-off (8.6): _____________________  Date: __________")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
