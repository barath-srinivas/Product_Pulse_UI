#!/usr/bin/env python3
"""Fetch Groww Google Play reviews and write raw audit JSON (Phase 1)."""

from __future__ import annotations

import argparse
import sys

from pulse.config import current_iso_week, load_config, parse_iso_week
from pulse.ingest.play_store import (
    InsufficientReviewsError,
    PlayStoreFetchError,
    ingest_groww_reviews,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Groww Google Play reviews")
    parser.add_argument(
        "--week",
        help="ISO week label YYYY-Www (default: current week in Asia/Kolkata)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run even if review count is below min_reviews_required",
    )
    parser.add_argument(
        "--product",
        default="groww",
        help="Product id (default: groww)",
    )
    args = parser.parse_args()

    config = load_config(include_mcp=False)
    iso_week = args.week or current_iso_week(config.pulse.timezone)
    parse_iso_week(iso_week)

    try:
        if args.product != "groww":
            from pulse.ingest.play_store import ingest_product_reviews

            result = ingest_product_reviews(
                args.product,
                iso_week=iso_week,
                config=config,
                force=args.force,
            )
        else:
            result = ingest_groww_reviews(
                iso_week=iso_week,
                config=config,
                force=args.force,
            )
    except InsufficientReviewsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except PlayStoreFetchError as exc:
        print(f"ERROR: play store fetch failed: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"product_id={result.product_id}")
    print(f"iso_week={result.iso_week}")
    print(f"review_count={result.review_count}")
    print(f"raw_review_count={result.raw_review_count}")
    print(f"filtered_out_count={result.filtered_out_count}")
    print(f"window={result.window_start}..{result.window_end}")
    print(f"actual_reviews_path={result.actual_reviews_path}")
    print(f"normalized_reviews_path={result.normalized_reviews_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
