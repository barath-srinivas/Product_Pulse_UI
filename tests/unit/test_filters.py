"""Unit tests for Phase 1 review normalization filters."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from pulse.config import IngestConfig
from pulse.ingest.filters import (
    contains_emoji,
    count_words,
    filter_reviews,
    get_filter_reason,
    is_english,
    passes_review_filters,
)
from pulse.ingest.models import Review

IST = ZoneInfo("Asia/Kolkata")
CONFIG = IngestConfig(min_words=8, english_only=True, reject_emojis=True)


def _review(body: str, review_id: str = "r1") -> Review:
    return Review(
        review_id=review_id,
        product_id="groww",
        body=body,
        review_date=date(2026, 5, 1),
        fetched_at=datetime(2026, 6, 8, 12, 0, tzinfo=IST),
    )


def test_count_words() -> None:
    assert count_words("one two three four five six seven eight") == 8
    assert count_words("one two three four five six seven") == 7


def test_contains_emoji() -> None:
    assert contains_emoji("Great app 😀 with enough words here overall") is True
    assert contains_emoji("Great app with enough words here overall today") is False


def test_is_english() -> None:
    assert is_english("The app freezes when the market opens every morning") is True
    assert (
        is_english(
            "यह ऐप बहुत खराब है और हर दिन क्रैश होता है बार बार"
        )
        is False
    )


def test_get_filter_reason_too_short() -> None:
    reason = get_filter_reason("too short review only", CONFIG)
    assert reason == "too_short"


def test_get_filter_reason_emoji() -> None:
    text = "This app crashes often during market hours every day 😀"
    assert get_filter_reason(text, CONFIG) == "emoji"


def test_get_filter_reason_non_english() -> None:
    text = "यह ऐप बहुत खराब है और हर दिन क्रैश होता है बार बार"
    assert get_filter_reason(text, CONFIG) == "non_english"


def test_passes_review_filters() -> None:
    review = _review("The app freezes exactly when the market opens, very frustrating.")
    assert passes_review_filters(review, CONFIG) is True


def test_filter_reviews_drops_invalid_entries() -> None:
    reviews = [
        _review("The app freezes exactly when the market opens, very frustrating.", "ok"),
        _review("too short review only", "short"),
        _review("This app crashes often during market hours every day 😀", "emoji"),
        _review("यह ऐप बहुत खराब है और हर दिन क्रैश होता है बार बार", "hindi"),
    ]
    kept, dropped = filter_reviews(reviews, CONFIG)
    assert len(kept) == 1
    assert kept[0].review_id == "ok"
    assert dropped == {"too_short": 1, "emoji": 1, "non_english": 1}


def test_filter_reviews_can_disable_rules() -> None:
    config = IngestConfig(min_words=3, english_only=False, reject_emojis=False)
    review = _review("यह ऐप बहुत खराब है 😀", "mixed")
    assert passes_review_filters(review, config) is True
