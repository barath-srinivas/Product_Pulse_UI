"""Operator-facing CLI for Product Review Pulse."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from pulse.config import current_iso_week, iso_week_range, load_config, normalize_iso_week, parse_iso_week
from pulse.ledger.store import LedgerStore
from pulse.orchestrator import OrchestratorError, PulseOrchestrator

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def _load_app_config(*, require_mcp: bool = True):
    try:
        return load_config(include_mcp=require_mcp)
    except KeyError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except Exception as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


def _validate_product(config, product_id: str) -> None:
    try:
        config.get_product(product_id)
    except KeyError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


def _print_run_summary(result) -> int:
    run = result.run
    if result.skipped:
        print(f"skipped=true run_id={run.run_id if run else 'n/a'}")
        return 0

    if run is None:
        return 0

    print(f"status={run.status}")
    print(f"run_id={run.run_id}")
    print(f"section_anchor={run.section_anchor}")
    print(f"review_count={run.review_count}")
    print(f"doc_document_id={run.doc_document_id}")
    print(f"gmail_draft_count={len(run.gmail_drafts)}")
    return 0


def _validate_iso_week(iso_week: str | None) -> str | None:
    if iso_week is None:
        return None
    try:
        return normalize_iso_week(iso_week)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


def cmd_run(args: argparse.Namespace) -> int:
    config = _load_app_config(require_mcp=True)
    _validate_product(config, args.product)
    _validate_iso_week(args.week)

    orchestrator = PulseOrchestrator(config)
    try:
        result = orchestrator.run(
            args.product,
            iso_week=args.week,
            force=args.force,
            force_delivery=args.force_delivery,
            from_stage=args.from_stage,  # type: ignore[arg-type]
            mock_llm=args.mock_llm,
        )
    except OrchestratorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return _print_run_summary(result)


def cmd_dry_run(args: argparse.Namespace) -> int:
    config = _load_app_config(require_mcp=False)
    _validate_product(config, args.product)
    _validate_iso_week(args.week)

    orchestrator = PulseOrchestrator(config)
    try:
        result = orchestrator.run(
            args.product,
            iso_week=args.week,
            mock_llm=args.mock_llm,
            dry_run=True,
        )
    except OrchestratorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    assert result.report is not None
    report_path = args.out.expanduser().resolve()
    report_path.write_text(result.report.model_dump_json(indent=2), encoding="utf-8")

    print("dry_run=true")
    print(f"report_out={report_path}")
    print(f"review_count={result.report.review_count}")
    print(f"theme_count={len(result.report.themes)}")
    if result.doc_report is not None:
        print(f"section_anchor={result.doc_report.section_anchor}")
        print(f"content_chars={len(result.doc_report.content)}")
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    config = _load_app_config(require_mcp=True)
    _validate_product(config, args.product)

    _validate_iso_week(args.from_week)
    _validate_iso_week(args.to_week)

    try:
        weeks = iso_week_range(args.from_week, args.to_week)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    orchestrator = PulseOrchestrator(config)
    failures = 0

    for week in weeks:
        print(f"backfill_week={week}")
        try:
            result = orchestrator.run(
                args.product,
                iso_week=week,
                force=args.force,
                force_delivery=args.force_delivery,
                mock_llm=args.mock_llm,
            )
        except OrchestratorError as exc:
            print(f"ERROR: week={week} {exc}", file=sys.stderr)
            failures += 1
            if args.stop_on_error:
                return 1
            continue

        if result.skipped:
            print(f"skipped=true week={week}")
        elif result.run is not None:
            print(f"completed week={week} run_id={result.run.run_id}")

    return 1 if failures else 0


def cmd_status(args: argparse.Namespace) -> int:
    config = _load_app_config(require_mcp=False)
    _validate_product(config, args.product)

    iso_week = args.week or current_iso_week(config.pulse.timezone)
    try:
        parse_iso_week(iso_week)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ledger = LedgerStore()
    record = ledger.get_latest_run(args.product, iso_week)
    if record is None:
        print(f"product_id={args.product}")
        print(f"iso_week={iso_week}")
        print("status=not_found")
        return 0

    print(f"run_id={record.run_id}")
    print(f"product_id={record.product_id}")
    print(f"iso_week={record.iso_week}")
    print(f"status={record.status}")
    print(f"section_anchor={record.section_anchor}")
    print(f"review_count={record.review_count}")
    print(f"doc_document_id={record.doc_document_id}")
    print(f"gmail_draft_count={len(record.gmail_drafts)}")
    print(f"email_mode={record.email_mode}")
    print(f"started_at={record.started_at.isoformat()}")
    print(f"completed_at={record.completed_at.isoformat() if record.completed_at else ''}")
    if record.error:
        print(f"error={record.error}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pulse",
        description="Weekly Product Review Pulse for Groww",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Full pipeline with delivery")
    run_parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    run_parser.add_argument("--week", help="ISO week YYYY-Www (default: current week IST)")
    run_parser.add_argument("--force", action="store_true", help="Recompute insights")
    run_parser.add_argument(
        "--force-delivery",
        action="store_true",
        help="Re-append Doc and create new drafts even if already delivered",
    )
    run_parser.add_argument(
        "--from-stage",
        choices=["ingest", "reason", "render", "delivery"],
        default="ingest",
        help="Start at a pipeline stage",
    )
    run_parser.add_argument("--mock-llm", action="store_true", help="Use mock Groq summarizer")
    run_parser.set_defaults(handler=cmd_run)

    dry_parser = subparsers.add_parser(
        "dry-run",
        help="Ingest + reason + render; no delivery HTTP",
    )
    dry_parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    dry_parser.add_argument("--week", help="ISO week YYYY-Www (default: current week IST)")
    dry_parser.add_argument(
        "--out",
        type=Path,
        default=Path("report.json"),
        help="Output PulseReport JSON (default: report.json)",
    )
    dry_parser.add_argument("--mock-llm", action="store_true", help="Use mock Groq summarizer")
    dry_parser.set_defaults(handler=cmd_dry_run)

    backfill_parser = subparsers.add_parser("backfill", help="Run pipeline over a week range")
    backfill_parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    backfill_parser.add_argument(
        "--from-week",
        required=True,
        help="Start ISO week YYYY-Www (inclusive)",
    )
    backfill_parser.add_argument(
        "--to-week",
        required=True,
        help="End ISO week YYYY-Www (inclusive)",
    )
    backfill_parser.add_argument("--force", action="store_true", help="Recompute insights")
    backfill_parser.add_argument(
        "--force-delivery",
        action="store_true",
        help="Re-append Doc and create new drafts even if already delivered",
    )
    backfill_parser.add_argument("--mock-llm", action="store_true", help="Use mock Groq summarizer")
    backfill_parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop backfill on first failed week",
    )
    backfill_parser.set_defaults(handler=cmd_backfill)

    status_parser = subparsers.add_parser("status", help="Show ledger summary for a run")
    status_parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    status_parser.add_argument("--week", help="ISO week YYYY-Www (default: current week IST)")
    status_parser.set_defaults(handler=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
