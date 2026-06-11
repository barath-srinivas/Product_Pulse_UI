"""Google Play review ingestion for Groww."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from google_play_scraper import Sort
from google_play_scraper.features.reviews import reviews as fetch_reviews_page
from pydantic import BaseModel

from pulse.config import GROWW_PRODUCT_ID, AppConfig, get_project_root, load_config
from pulse.ingest.filters import filter_reviews
from pulse.ingest.models import (
    ActualReviewEntry,
    ActualReviewsFile,
    IngestResult,
    NormalizedReviewsFile,
    Review,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 200
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_LANG = "en"
DEFAULT_COUNTRY = "in"


class InsufficientReviewsError(Exception):
    """Raised when fetched reviews are below the configured minimum."""

    def __init__(self, count: int, minimum: int, product_id: str) -> None:
        self.count = count
        self.minimum = minimum
        self.product_id = product_id
        super().__init__(
            f"insufficient reviews for {product_id}: fetched {count}, minimum {minimum}"
        )


class PlayStoreFetchError(Exception):
    """Raised when Google Play review fetch fails after retries."""


ReviewPageResult = tuple[list[dict[str, Any]], Any]


def get_data_dir() -> Path:
    root = get_project_root() / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_reviews_dir() -> Path:
    path = get_data_dir() / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def actual_reviews_path(product_id: str, data_dir: Path | None = None) -> Path:
    base = data_dir or get_data_dir()
    reviews_dir = base / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    return reviews_dir / f"{product_id}_actual.json"


def normalized_reviews_path(product_id: str, data_dir: Path | None = None) -> Path:
    base = data_dir or get_data_dir()
    reviews_dir = base / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    return reviews_dir / f"{product_id}_normalized.json"


def to_actual_review_entry(
    raw: dict[str, Any],
    timezone: str,
) -> ActualReviewEntry | None:
    """Map a Play review to the stored actual-review format."""
    content = (raw.get("content") or "").strip()
    if not content:
        return None

    reviewed_at = _review_datetime(raw, timezone)
    score = raw.get("score")
    return ActualReviewEntry(
        content=content,
        score=int(score) if score is not None else None,
        thumbsUpCount=raw.get("thumbsUpCount"),
        appVersion=raw.get("appVersion"),
        review_date=reviewed_at.date(),
    )


def compute_review_window(
    review_window_weeks: int,
    timezone: str,
    *,
    end: datetime | None = None,
) -> tuple[date, date]:
    """Return inclusive [start, end] dates for the rolling review window."""
    if end is None:
        end = datetime.now(ZoneInfo(timezone))
    elif end.tzinfo is None:
        end = end.replace(tzinfo=ZoneInfo(timezone))
    else:
        end = end.astimezone(ZoneInfo(timezone))

    end_date = end.date()
    start_date = end_date - timedelta(weeks=review_window_weeks)
    return start_date, end_date


def stable_review_id(
    package: str,
    user_name: str,
    reviewed_at: datetime,
    content: str,
) -> str:
    """Fallback id when Play does not return reviewId."""
    key = f"{package}|{user_name}|{reviewed_at.isoformat()}|{content}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _review_datetime(raw: dict[str, Any], timezone: str) -> datetime:
    reviewed_at = raw.get("at")
    if isinstance(reviewed_at, str):
        reviewed_at = datetime.fromisoformat(reviewed_at)
    if isinstance(reviewed_at, datetime):
        if reviewed_at.tzinfo is None:
            return reviewed_at.replace(tzinfo=ZoneInfo(timezone))
        return reviewed_at.astimezone(ZoneInfo(timezone))
    raise ValueError("review payload missing datetime field 'at'")


def normalize_raw_review(
    raw: dict[str, Any],
    *,
    product_id: str,
    package: str,
    fetched_at: datetime,
    timezone: str,
) -> Review | None:
    """Map a google-play-scraper review dict to Review."""
    content = (raw.get("content") or "").strip()
    title = None
    if not content:
        return None

    reviewed_at = _review_datetime(raw, timezone)
    review_id = raw.get("reviewId") or stable_review_id(
        package,
        str(raw.get("userName") or ""),
        reviewed_at,
        content,
    )

    score = raw.get("score")
    rating = int(score) if score is not None else None

    return Review(
        review_id=str(review_id),
        product_id=product_id,
        rating=rating,
        title=title,
        body=content,
        reviewer_name=raw.get("userName"),
        review_date=reviewed_at.date(),
        fetched_at=fetched_at,
        language=raw.get("lang"),
    )


def dedupe_reviews(reviews: list[Review]) -> list[Review]:
    """Drop duplicate review_id entries, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[Review] = []
    for review in reviews:
        if review.review_id in seen:
            continue
        seen.add(review.review_id)
        unique.append(review)
    return unique


def _fetch_page_with_retry(
    fetch_page: Callable[..., ReviewPageResult],
    *args: Any,
    **kwargs: Any,
) -> ReviewPageResult:
    delay = INITIAL_BACKOFF_SECONDS
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fetch_page(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "play store fetch attempt %s/%s failed: %s",
                attempt,
                MAX_RETRIES,
                exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(delay)
                delay *= 2
    raise PlayStoreFetchError(f"failed after {MAX_RETRIES} retries") from last_error


def fetch_reviews_for_package(
    package: str,
    *,
    window_start: date,
    window_end: date,
    timezone: str,
    lang: str = DEFAULT_LANG,
    country: str = DEFAULT_COUNTRY,
    fetch_page: Callable[..., ReviewPageResult] = fetch_reviews_page,
) -> list[dict[str, Any]]:
    """Paginate Google Play reviews (newest first) within the date window."""
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    continuation_token = None

    while True:
        page, continuation_token = _fetch_page_with_retry(
            fetch_page,
            package,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=PAGE_SIZE,
            continuation_token=continuation_token,
        )

        if not page:
            break

        page_ids = {str(item.get("reviewId") or "") for item in page}
        if page_ids and page_ids.issubset(seen_ids):
            logger.info("duplicate pagination page detected; stopping ingest")
            break

        stop_for_window = False
        for raw in page:
            review_id = str(raw.get("reviewId") or "")
            if review_id:
                seen_ids.add(review_id)

            try:
                reviewed_at = _review_datetime(raw, timezone).date()
            except ValueError:
                continue

            if reviewed_at > window_end:
                continue
            if reviewed_at < window_start:
                stop_for_window = True
                break

            collected.append(raw)

        if stop_for_window:
            break
        if continuation_token is None or continuation_token.token is None:
            break

    return collected


def _write_json(path: Path, payload: BaseModel) -> Path:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), indent=2, default=str),
        encoding="utf-8",
    )
    return path


def persist_actual_reviews(
    *,
    product_id: str,
    iso_week: str,
    package: str,
    fetched_at: datetime,
    review_window_weeks: int,
    window_start: date,
    window_end: date,
    raw_reviews: list[dict[str, Any]],
    timezone: str,
    data_dir: Path | None = None,
) -> Path:
    """Write all fetched reviews to data/reviews/{product_id}_actual.json."""
    actual_entries: list[ActualReviewEntry] = []
    for raw in raw_reviews:
        entry = to_actual_review_entry(raw, timezone)
        if entry is not None:
            actual_entries.append(entry)

    out_path = actual_reviews_path(product_id, data_dir)
    record = ActualReviewsFile(
        product_id=product_id,
        iso_week=iso_week,
        package=package,
        fetched_at=fetched_at,
        review_window_weeks=review_window_weeks,
        window_start=window_start,
        window_end=window_end,
        review_count=len(actual_entries),
        reviews=actual_entries,
    )
    return _write_json(out_path, record)


def persist_normalized_reviews(
    *,
    product_id: str,
    iso_week: str,
    package: str,
    fetched_at: datetime,
    review_window_weeks: int,
    window_start: date,
    window_end: date,
    reviews: list[Review],
    filtered_out_count: int,
    data_dir: Path | None = None,
) -> Path:
    """Write filtered normalized reviews to data/reviews/{product_id}_normalized.json."""
    out_path = normalized_reviews_path(product_id, data_dir)
    stored = [review.to_stored_entry() for review in reviews]
    record = NormalizedReviewsFile(
        product_id=product_id,
        iso_week=iso_week,
        package=package,
        fetched_at=fetched_at,
        review_window_weeks=review_window_weeks,
        window_start=window_start,
        window_end=window_end,
        review_count=len(stored),
        filtered_out_count=filtered_out_count,
        reviews=stored,
    )
    return _write_json(out_path, record)


def ingest_product_reviews(
    product_id: str,
    *,
    iso_week: str,
    config: AppConfig | None = None,
    force: bool = False,
    fetch_page: Callable[..., ReviewPageResult] | None = None,
    lang: str = DEFAULT_LANG,
    country: str = DEFAULT_COUNTRY,
) -> IngestResult:
    """Fetch, normalize, dedupe, and persist reviews for a configured product."""
    app_config = config or load_config(include_mcp=False)
    product = app_config.get_product(product_id)
    pulse = app_config.pulse
    timezone = pulse.timezone

    fetched_at = datetime.now(ZoneInfo(timezone))
    window_start, window_end = compute_review_window(
        pulse.review_window_weeks,
        timezone,
        end=fetched_at,
    )

    page_fetcher = fetch_page or fetch_reviews_page
    raw_reviews = fetch_reviews_for_package(
        product.google_play_package,
        window_start=window_start,
        window_end=window_end,
        timezone=timezone,
        lang=lang,
        country=country,
        fetch_page=page_fetcher,
    )

    normalized: list[Review] = []
    for raw in raw_reviews:
        review = normalize_raw_review(
            raw,
            product_id=product_id,
            package=product.google_play_package,
            fetched_at=fetched_at,
            timezone=timezone,
        )
        if review is not None:
            normalized.append(review)

    deduped = dedupe_reviews(normalized)
    reviews, dropped = filter_reviews(deduped, pulse.ingest)
    if any(dropped.values()):
        logger.info(
            "review normalization dropped counts: too_short=%s emoji=%s non_english=%s",
            dropped["too_short"],
            dropped["emoji"],
            dropped["non_english"],
        )

    if not force and len(reviews) < pulse.min_reviews_required:
        raise InsufficientReviewsError(
            len(reviews),
            pulse.min_reviews_required,
            product_id,
        )

    actual_path = persist_actual_reviews(
        product_id=product_id,
        iso_week=iso_week,
        package=product.google_play_package,
        fetched_at=fetched_at,
        review_window_weeks=pulse.review_window_weeks,
        window_start=window_start,
        window_end=window_end,
        raw_reviews=raw_reviews,
        timezone=timezone,
    )
    normalized_path = persist_normalized_reviews(
        product_id=product_id,
        iso_week=iso_week,
        package=product.google_play_package,
        fetched_at=fetched_at,
        review_window_weeks=pulse.review_window_weeks,
        window_start=window_start,
        window_end=window_end,
        reviews=reviews,
        filtered_out_count=len(deduped) - len(reviews),
    )

    return IngestResult(
        product_id=product_id,
        iso_week=iso_week,
        package=product.google_play_package,
        reviews=reviews,
        actual_reviews_path=str(actual_path),
        normalized_reviews_path=str(normalized_path),
        review_count=len(reviews),
        raw_review_count=len(deduped),
        filtered_out_count=len(deduped) - len(reviews),
        window_start=window_start,
        window_end=window_end,
        fetched_at=fetched_at,
    )


def raw_audit_path(
    product_id: str,
    iso_week: str,
    data_dir: Path | None = None,
) -> Path:
    """Path to `data/raw/{iso_week}/{product_id}.json`."""
    base = data_dir or get_data_dir()
    return base / "raw" / iso_week / f"{product_id}.json"


def load_reviews_from_raw_audit(
    path: Path,
    *,
    config: AppConfig | None = None,
) -> list[Review]:
    """Rebuild filtered Review list (with review_id) from a raw audit JSON file."""
    app_config = config or load_config(include_mcp=False)
    pulse = app_config.pulse
    payload = json.loads(path.read_text(encoding="utf-8"))
    product_id = str(payload["product_id"])
    package = str(payload["package"])
    timezone = pulse.timezone

    fetched_at = datetime.fromisoformat(str(payload["fetched_at"]))
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=ZoneInfo(timezone))

    normalized: list[Review] = []
    for raw in payload.get("raw_reviews", []):
        review = normalize_raw_review(
            raw,
            product_id=product_id,
            package=package,
            fetched_at=fetched_at,
            timezone=timezone,
        )
        if review is not None:
            normalized.append(review)

    deduped = dedupe_reviews(normalized)
    reviews, dropped = filter_reviews(deduped, pulse.ingest)
    if any(dropped.values()):
        logger.info(
            "raw audit load dropped: too_short=%s emoji=%s non_english=%s",
            dropped["too_short"],
            dropped["emoji"],
            dropped["non_english"],
        )
    return reviews


def ingest_groww_reviews(
    *,
    iso_week: str,
    config: AppConfig | None = None,
    force: bool = False,
    fetch_page: Callable[..., ReviewPageResult] | None = None,
) -> IngestResult:
    """Convenience wrapper for the sole v1 product."""
    return ingest_product_reviews(
        GROWW_PRODUCT_ID,
        iso_week=iso_week,
        config=config,
        force=force,
        fetch_page=fetch_page,
    )
