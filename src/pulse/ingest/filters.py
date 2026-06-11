"""Phase 1 review normalization filters."""

from __future__ import annotations

import re
from typing import Literal

from langdetect import LangDetectException, detect

from pulse.config import IngestConfig
from pulse.ingest.models import Review

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)

FilterReason = Literal["too_short", "emoji", "non_english"]


def count_words(text: str) -> int:
    """Count whitespace-delimited words in review text."""
    return len([word for word in text.split() if word.strip()])


def contains_emoji(text: str) -> bool:
    """Return True when the text contains emoji characters."""
    return bool(_EMOJI_RE.search(text))


def is_english(text: str) -> bool:
    """Return True when langdetect identifies the text as English."""
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


def review_text(review: Review) -> str:
    """Combined review text used for normalization checks."""
    return review.display_text().strip()


def get_filter_reason(
    text: str,
    config: IngestConfig,
) -> FilterReason | None:
    """Return a rejection reason, or None if the review passes all filters."""
    if count_words(text) < config.min_words:
        return "too_short"
    if config.reject_emojis and contains_emoji(text):
        return "emoji"
    if config.english_only and not is_english(text):
        return "non_english"
    return None


def passes_review_filters(review: Review, config: IngestConfig) -> bool:
    """Return True when the review meets Phase 1 normalization rules."""
    return get_filter_reason(review_text(review), config) is None


def filter_reviews(
    reviews: list[Review],
    config: IngestConfig,
) -> tuple[list[Review], dict[FilterReason, int]]:
    """Keep only reviews that pass normalization filters."""
    kept: list[Review] = []
    dropped: dict[FilterReason, int] = {
        "too_short": 0,
        "emoji": 0,
        "non_english": 0,
    }

    for review in reviews:
        reason = get_filter_reason(review_text(review), config)
        if reason is None:
            kept.append(review)
        else:
            dropped[reason] += 1

    return kept, dropped
