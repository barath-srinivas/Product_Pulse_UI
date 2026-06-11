"""PII scrubbing and text normalization before embed and LLM."""

from __future__ import annotations

import re

from pulse.ingest.models import Review
from pulse.pipeline.models import ScrubbedReview

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+91[\s-]?)?[6-9]\d{9}\b|\b\d{10}\b",
)
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_MAX_BODY_CHARS = 4000
_REDACTION = "[REDACTED]"


def scrub_text(text: str) -> str:
    """Remove PII patterns and normalize whitespace."""
    cleaned = text.strip()
    cleaned = _EMAIL_RE.sub(_REDACTION, cleaned)
    cleaned = _PHONE_RE.sub(_REDACTION, cleaned)
    cleaned = _PAN_RE.sub(_REDACTION, cleaned)
    cleaned = _URL_RE.sub(_REDACTION, cleaned)
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if len(cleaned) > _MAX_BODY_CHARS:
        cleaned = cleaned[: _MAX_BODY_CHARS - 3] + "..."
    return cleaned


def scrub_reviews(reviews: list[Review], *, enabled: bool = True) -> list[ScrubbedReview]:
    """Scrub review bodies; preserve review_id and rating."""
    scrubbed: list[ScrubbedReview] = []
    seen: set[str] = set()
    for review in reviews:
        if review.review_id in seen:
            continue
        seen.add(review.review_id)
        body = scrub_text(review.display_text()) if enabled else review.display_text().strip()
        if not body:
            continue
        scrubbed.append(
            ScrubbedReview(
                review_id=review.review_id,
                product_id=review.product_id,
                rating=review.rating,
                body=body,
                review_date=review.review_date,
            )
        )
    return scrubbed
