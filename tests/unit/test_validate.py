"""Unit tests for quote validation."""

from datetime import date

from pulse.config import SafetyConfig
from pulse.pipeline.models import LlmQuoteCandidate, LlmThemeResponse, ScrubbedReview
from pulse.pipeline.validate import build_theme_insight, validate_quote


def _corpus() -> dict[str, ScrubbedReview]:
    body = "The app freezes exactly when the market opens."
    return {
        "abc": ScrubbedReview(
            review_id="abc",
            product_id="groww",
            rating=2,
            body=body,
            review_date=date(2026, 5, 1),
        )
    }


def test_validate_quote_exact_match() -> None:
    quote = LlmQuoteCandidate(text="freezes exactly when the market opens", review_id="abc")
    result = validate_quote(quote, _corpus(), max_length=280)
    assert result is not None
    assert result.validation == "exact"


def test_validate_quote_normalized_match() -> None:
    quote = LlmQuoteCandidate(text="Freezes exactly when the market opens.", review_id="abc")
    result = validate_quote(quote, _corpus(), max_length=280)
    assert result is not None
    assert result.validation == "normalized"


def test_validate_quote_rejects_hallucination() -> None:
    quote = LlmQuoteCandidate(text="This quote does not exist in corpus", review_id="abc")
    assert validate_quote(quote, _corpus(), max_length=280) is None


def test_build_theme_insight_requires_valid_quote() -> None:
    response = LlmThemeResponse(
        theme_name="Performance",
        theme_summary="Lag at open",
        quotes=[LlmQuoteCandidate(text="freezes exactly when the market opens", review_id="abc")],
        action_ideas=["Fix crashes"],
    )
    insight = build_theme_insight(
        cluster_id=1,
        rank=1,
        response=response,
        corpus=_corpus(),
        safety=SafetyConfig(),
    )
    assert insight is not None
    assert len(insight.quotes) == 1
