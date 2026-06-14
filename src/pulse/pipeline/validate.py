"""Quote validation against scrubbed review corpus."""

from __future__ import annotations

import re
import string

from pulse.config import SafetyConfig
from pulse.pipeline.models import (
    LlmQuoteCandidate,
    LlmThemeResponse,
    ScrubbedReview,
    ThemeInsight,
    ValidatedQuote,
)

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _normalize(text: str) -> str:
    lowered = text.lower().translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", lowered).strip()


def validate_quote(
    quote: LlmQuoteCandidate,
    corpus: dict[str, ScrubbedReview],
    *,
    max_length: int,
) -> ValidatedQuote | None:
    review = corpus.get(quote.review_id)
    if review is None:
        return None
    text = quote.text.strip()
    if not text or len(text) > max_length:
        return None
    body = review.body
    if text in body:
        return ValidatedQuote(text=text, review_id=quote.review_id, validation="exact")
    if _normalize(text) in _normalize(body):
        return ValidatedQuote(text=text, review_id=quote.review_id, validation="normalized")
    return None


def validate_theme(
    response: LlmThemeResponse,
    corpus: dict[str, ScrubbedReview],
    safety: SafetyConfig,
) -> list[ValidatedQuote]:
    validated: list[ValidatedQuote] = []
    seen: set[str] = set()
    for quote in response.quotes:
        result = validate_quote(quote, corpus, max_length=safety.max_quote_length)
        if result is None:
            continue
        key = f"{result.review_id}:{result.text}"
        if key in seen:
            continue
        seen.add(key)
        validated.append(result)
    return validated


def build_theme_insight(
    *,
    cluster_id: int,
    rank: int,
    response: LlmThemeResponse,
    corpus: dict[str, ScrubbedReview],
    safety: SafetyConfig,
    review_count: int = 0,
    review_share_pct: float = 0.0,
) -> ThemeInsight | None:
    quotes = validate_theme(response, corpus, safety)
    if not quotes:
        return None
    return ThemeInsight(
        cluster_id=cluster_id,
        theme_name=response.theme_name.strip(),
        theme_summary=response.theme_summary.strip(),
        quotes=quotes,
        action_ideas=[a.strip() for a in response.action_ideas if a.strip()][:3],
        rank=rank,
        review_count=review_count,
        review_share_pct=review_share_pct,
    )
