"""Unit tests for PII scrubbing."""

from datetime import date, datetime

from pulse.ingest.models import Review
from pulse.pipeline.scrub import scrub_reviews, scrub_text


def _review(body: str, review_id: str = "r1") -> Review:
    return Review(
        review_id=review_id,
        product_id="groww",
        rating=3,
        body=body,
        review_date=date(2026, 5, 1),
        fetched_at=datetime(2026, 6, 8, 10, 0, 0),
    )


def test_scrub_text_redacts_email_and_phone() -> None:
    text = "Contact me at user@gmail.com or call 9876543210 please"
    cleaned = scrub_text(text)
    assert "user@gmail.com" not in cleaned
    assert "9876543210" not in cleaned
    assert "[REDACTED]" in cleaned


def test_scrub_text_collapses_whitespace() -> None:
    assert scrub_text("too   many    spaces") == "too many spaces"


def test_scrub_reviews_dedupes_by_review_id() -> None:
    reviews = [_review("first review body here", "dup"), _review("second body here", "dup")]
    result = scrub_reviews(reviews)
    assert len(result) == 1


def test_scrub_reviews_preserves_review_id() -> None:
    result = scrub_reviews([_review("Valid review body with enough words here")])
    assert result[0].review_id == "r1"
