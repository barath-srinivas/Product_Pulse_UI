"""Unit tests for Google Play ingestion."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pulse.config import load_config
from pulse.ingest.models import Review
from pulse.ingest.play_store import (
    InsufficientReviewsError,
    compute_review_window,
    dedupe_reviews,
    fetch_reviews_for_package,
    ingest_product_reviews,
    normalize_raw_review,
    persist_actual_reviews,
    persist_normalized_reviews,
    stable_review_id,
    to_actual_review_entry,
)

IST = ZoneInfo("Asia/Kolkata")
FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "groww_reviews_sample.json"


@pytest.fixture
def sample_raw_reviews() -> list[dict]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for item in raw:
        item["at"] = datetime.fromisoformat(item["at"]).replace(tzinfo=IST)
    return raw


def test_stable_review_id_deterministic() -> None:
    reviewed_at = datetime(2026, 5, 1, 9, 0, tzinfo=IST)
    first = stable_review_id("com.nextbillion.groww", "user", reviewed_at, "text")
    second = stable_review_id("com.nextbillion.groww", "user", reviewed_at, "text")
    assert first == second
    assert len(first) == 32


def test_normalize_raw_review(sample_raw_reviews: list[dict]) -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    review = normalize_raw_review(
        sample_raw_reviews[0],
        product_id="groww",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        timezone="Asia/Kolkata",
    )
    assert review is not None
    assert review.review_id == "sample-review-001"
    assert review.product_id == "groww"
    assert review.source == "google_play"
    assert review.rating == 2
    assert review.review_date == date(2026, 5, 15)


def test_normalize_skips_empty_body(sample_raw_reviews: list[dict]) -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    empty = normalize_raw_review(
        sample_raw_reviews[-1],
        product_id="groww",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        timezone="Asia/Kolkata",
    )
    assert empty is None


def test_normalize_hash_fallback_when_missing_review_id(sample_raw_reviews: list[dict]) -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    review = normalize_raw_review(
        sample_raw_reviews[3],
        product_id="groww",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        timezone="Asia/Kolkata",
    )
    assert review is not None
    assert review.review_id != ""
    assert len(review.review_id) == 32


def test_review_round_trip_json(sample_raw_reviews: list[dict]) -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    review = normalize_raw_review(
        sample_raw_reviews[0],
        product_id="groww",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        timezone="Asia/Kolkata",
    )
    assert review is not None
    payload = review.model_dump(mode="json")
    restored = Review.model_validate(payload)
    assert restored == review


def test_dedupe_reviews() -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    base = Review(
        review_id="dup",
        product_id="groww",
        body="same",
        review_date=date(2026, 5, 1),
        fetched_at=fetched_at,
    )
    dup = base.model_copy()
    unique = dedupe_reviews([base, dup])
    assert len(unique) == 1


def test_compute_review_window() -> None:
    end = datetime(2026, 6, 8, 8, 0, tzinfo=IST)
    start, end_date = compute_review_window(10, "Asia/Kolkata", end=end)
    assert end_date == date(2026, 6, 8)
    assert start == date(2026, 3, 30)


def test_fetch_reviews_for_package_filters_by_window(sample_raw_reviews: list[dict]) -> None:
    pages = [sample_raw_reviews, []]
    calls = {"count": 0}

    def fake_fetch_page(*_args, **_kwargs):
        idx = calls["count"]
        calls["count"] += 1
        if idx == 0:
            return pages[0], None
        return pages[1], None

    raw = fetch_reviews_for_package(
        "com.nextbillion.groww",
        window_start=date(2026, 4, 1),
        window_end=date(2026, 6, 30),
        timezone="Asia/Kolkata",
        fetch_page=fake_fetch_page,
    )
    # Newest-first pagination stops once a review is older than the window.
    assert len(raw) == 2
    assert raw[0]["reviewId"] == "sample-review-001"
    assert raw[1]["reviewId"] == "sample-review-002"


def test_fetch_stops_on_old_reviews(sample_raw_reviews: list[dict]) -> None:
    newest_first = [
        sample_raw_reviews[0],
        sample_raw_reviews[1],
        sample_raw_reviews[2],
    ]

    def fake_fetch_page(*_args, **_kwargs):
        return newest_first, None

    raw = fetch_reviews_for_package(
        "com.nextbillion.groww",
        window_start=date(2026, 5, 1),
        window_end=date(2026, 6, 30),
        timezone="Asia/Kolkata",
        fetch_page=fake_fetch_page,
    )
    assert len(raw) == 1
    assert raw[0]["reviewId"] == "sample-review-001"


def test_to_actual_review_entry_strips_fields(sample_raw_reviews: list[dict]) -> None:
    entry = to_actual_review_entry(sample_raw_reviews[0], "Asia/Kolkata")
    assert entry is not None
    dumped = entry.model_dump()
    assert set(dumped) == {
        "content",
        "score",
        "thumbsUpCount",
        "appVersion",
        "review_date",
    }
    assert dumped["content"] == sample_raw_reviews[0]["content"]
    assert dumped["review_date"] == date(2026, 5, 15)


def test_persist_actual_and_normalized_reviews(
    tmp_path: Path,
    sample_raw_reviews: list[dict],
) -> None:
    fetched_at = datetime(2026, 6, 8, 12, 0, tzinfo=IST)
    data_dir = tmp_path

    actual_path = persist_actual_reviews(
        product_id="groww",
        iso_week="2026-W23",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        review_window_weeks=10,
        window_start=date(2026, 3, 30),
        window_end=date(2026, 6, 8),
        raw_reviews=sample_raw_reviews[:3],
        timezone="Asia/Kolkata",
        data_dir=data_dir,
    )
    assert actual_path.name == "groww_actual.json"
    actual_payload = json.loads(actual_path.read_text(encoding="utf-8"))
    assert actual_payload["review_count"] == 3
    assert "raw_reviews" not in actual_payload
    first = actual_payload["reviews"][0]
    assert "reviewId" not in first
    assert "userName" not in first
    assert "userImage" not in first
    assert "reviewCreatedVersion" not in first
    assert "at" not in first
    assert "replyContent" not in first
    assert "repliedAt" not in first

    review = normalize_raw_review(
        sample_raw_reviews[0],
        product_id="groww",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        timezone="Asia/Kolkata",
    )
    assert review is not None
    normalized_path = persist_normalized_reviews(
        product_id="groww",
        iso_week="2026-W23",
        package="com.nextbillion.groww",
        fetched_at=fetched_at,
        review_window_weeks=10,
        window_start=date(2026, 3, 30),
        window_end=date(2026, 6, 8),
        reviews=[review],
        filtered_out_count=0,
        data_dir=data_dir,
    )
    assert normalized_path.name == "groww_normalized.json"
    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    stored = normalized_payload["reviews"][0]
    assert "review_id" not in stored
    assert "reviewer_name" not in stored
    assert "fetched_at" not in stored
    assert stored["body"] == review.body


def test_ingest_raises_when_below_minimum(config_dir: Path, sample_raw_reviews: list[dict]) -> None:
    config = load_config(config_dir, include_mcp=False)

    def fake_fetch_page(*_args, **_kwargs):
        return sample_raw_reviews[:2], None

    with pytest.raises(InsufficientReviewsError) as exc:
        ingest_product_reviews(
            "groww",
            iso_week="2026-W23",
            config=config,
            fetch_page=fake_fetch_page,
        )
    assert exc.value.count == 2
    assert exc.value.minimum == config.pulse.min_reviews_required


def test_ingest_force_allows_low_count(
    config_dir: Path,
    sample_raw_reviews: list[dict],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(config_dir, include_mcp=False)
    monkeypatch.setattr(
        "pulse.ingest.play_store.get_data_dir",
        lambda: tmp_path,
    )

    def fake_fetch_page(*_args, **_kwargs):
        return sample_raw_reviews[:2], None

    result = ingest_product_reviews(
        "groww",
        iso_week="2026-W23",
        config=config,
        force=True,
        fetch_page=fake_fetch_page,
    )
    assert result.review_count == 2
    assert result.raw_review_count == 2
    assert result.filtered_out_count == 0
    assert Path(result.actual_reviews_path).exists()
    assert Path(result.normalized_reviews_path).exists()


def test_ingest_applies_normalization_filters(
    config_dir: Path,
    sample_raw_reviews: list[dict],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = load_config(config_dir, include_mcp=False)
    monkeypatch.setattr(
        "pulse.ingest.play_store.get_data_dir",
        lambda: tmp_path,
    )

    short_review = sample_raw_reviews[0].copy()
    short_review["reviewId"] = "short-review"
    short_review["content"] = "too short review only"

    emoji_review = sample_raw_reviews[1].copy()
    emoji_review["reviewId"] = "emoji-review"
    emoji_review["content"] = "This app crashes often during market hours every day 😀"

    def fake_fetch_page(*_args, **_kwargs):
        return [short_review, emoji_review, sample_raw_reviews[0]], None

    result = ingest_product_reviews(
        "groww",
        iso_week="2026-W23",
        config=config,
        force=True,
        fetch_page=fake_fetch_page,
    )
    assert result.raw_review_count == 3
    assert result.review_count == 1
    assert result.filtered_out_count == 2
    assert result.reviews[0].review_id == "sample-review-001"


def test_load_reviews_from_raw_audit(config_dir: Path) -> None:
    from pulse.ingest.play_store import load_reviews_from_raw_audit

    fixture = (
        Path(__file__).parent.parent / "fixtures" / "groww_raw_audit_sample.json"
    )
    config = load_config(config_dir, include_mcp=False)
    reviews = load_reviews_from_raw_audit(fixture, config=config)
    assert len(reviews) == 3
    assert all(r.review_id for r in reviews)
    bodies = {r.body for r in reviews}
    assert "The app freezes exactly when the market opens every morning." in bodies
