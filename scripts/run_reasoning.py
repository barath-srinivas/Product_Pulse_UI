#!/usr/bin/env python3
"""Run Phase 2 reasoning pipeline: scrub → BGE embed → cluster → Groq LLM → report.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from pulse.config import current_iso_week, load_config, parse_iso_week
from pulse.ingest.models import Review
from pulse.ingest.play_store import (
    ingest_groww_reviews,
    load_reviews_from_raw_audit,
    raw_audit_path,
)
from pulse.pipeline.exceptions import MissingGroqApiKeyError, PipelineError
from pulse.pipeline.reasoning import run_reasoning_pipeline

_RAW_AUDIT_DEFAULT = "__default__"


def _load_reviews_from_ingest(iso_week: str, force: bool) -> list[Review]:
    config = load_config(include_mcp=False)
    result = ingest_groww_reviews(iso_week=iso_week, config=config, force=force)
    return result.reviews


def _load_reviews_from_json(path: Path) -> list[Review]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "reviews" in raw:
        raw = raw["reviews"]
    return [Review.model_validate(item) for item in raw]


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Run Groq reasoning pipeline (Phase 2)")
    parser.add_argument(
        "--week",
        help="ISO week YYYY-Www (default: current week in Asia/Kolkata)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="JSON file with Review objects (must include review_id)",
    )
    parser.add_argument(
        "--from-raw",
        nargs="?",
        const=_RAW_AUDIT_DEFAULT,
        default=None,
        metavar="PATH",
        help="Load from raw audit JSON (default path: data/raw/{week}/groww.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("report.json"),
        help="Output PulseReport JSON path (default: report.json)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock Groq summarizer (no GROQ_API_KEY, no quota use)",
    )
    parser.add_argument(
        "--tfidf",
        action="store_true",
        help="Use TF-IDF embeddings instead of BGE (faster dev runs)",
    )
    parser.add_argument(
        "--force-ingest",
        action="store_true",
        help="Pass --force to live ingest when review count is below minimum",
    )
    parser.add_argument("--product", default="groww")
    args = parser.parse_args()

    config = load_config(include_mcp=False)
    iso_week = args.week or current_iso_week(config.pulse.timezone)
    parse_iso_week(iso_week)

    if args.tfidf:
        config.pulse.embeddings.provider = "tfidf"

    try:
        if args.from_raw is not None:
            raw_path = (
                raw_audit_path(args.product, iso_week)
                if args.from_raw == _RAW_AUDIT_DEFAULT
                else Path(args.from_raw)
            )
            reviews = load_reviews_from_raw_audit(raw_path, config=config)
        elif args.input:
            reviews = _load_reviews_from_json(args.input)
        else:
            reviews = _load_reviews_from_ingest(iso_week, force=args.force_ingest)
    except Exception as exc:
        print(f"ERROR: failed to load reviews: {exc}", file=sys.stderr)
        return 1

    if not reviews:
        print("ERROR: no reviews to process", file=sys.stderr)
        return 1

    try:
        result = run_reasoning_pipeline(
            reviews,
            product_id=args.product,
            iso_week=iso_week,
            config=config.pulse,
            mock_llm=args.mock_llm,
        )
    except MissingGroqApiKeyError as exc:
        print(f"ERROR: {exc} (use --mock-llm for local dev)", file=sys.stderr)
        return 1
    except PipelineError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    args.output.write_text(
        result.report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(f"product_id={result.report.product_id}")
    print(f"iso_week={result.report.iso_week}")
    print(f"review_count={result.report.review_count}")
    print(f"themes={len(result.report.themes)}")
    print(f"embeddings={config.pulse.embeddings.provider}")
    print(f"llm_provider={result.report.llm_provider}")
    print(f"llm_model={result.report.llm_model}")
    print(f"llm_requests={result.llm_requests}")
    print(f"llm_tokens_used={result.llm_tokens_used}")
    print(f"noise_ratio={result.noise_ratio:.3f}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
