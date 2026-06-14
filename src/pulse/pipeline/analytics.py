"""Dashboard analytics derived from PulseReport and review ratings."""

from __future__ import annotations

from pulse.pipeline.models import PulseReport, ScrubbedReview, SentimentSummary, ThemeInsight


def compute_sentiment(reviews: list[ScrubbedReview]) -> SentimentSummary:
    """Classify star ratings: positive >=4, negative <=2, neutral otherwise."""
    rated = [r for r in reviews if r.rating is not None]
    if not rated:
        return SentimentSummary(positive_pct=0.0, negative_pct=0.0, neutral_pct=0.0)

    positive = sum(1 for r in rated if r.rating >= 4)
    negative = sum(1 for r in rated if r.rating <= 2)
    neutral = len(rated) - positive - negative
    total = len(rated)
    return SentimentSummary(
        positive_pct=round(positive / total * 100, 1),
        negative_pct=round(negative / total * 100, 1),
        neutral_pct=round(neutral / total * 100, 1),
    )


def compute_avg_rating(reviews: list[ScrubbedReview]) -> float | None:
    rated = [r.rating for r in reviews if r.rating is not None]
    if not rated:
        return None
    return round(sum(rated) / len(rated), 1)


def attach_theme_shares(themes: list[ThemeInsight], total_reviews: int) -> list[ThemeInsight]:
    if total_reviews <= 0:
        return themes
    enriched: list[ThemeInsight] = []
    for theme in themes:
        share = round(theme.review_count / total_reviews * 100, 1) if theme.review_count else 0.0
        enriched.append(theme.model_copy(update={"review_share_pct": share}))
    return enriched


def enrich_report(
    report: PulseReport,
    *,
    scrubbed_reviews: list[ScrubbedReview] | None = None,
) -> PulseReport:
    """Fill analytics fields on a report (for legacy artifacts missing them)."""
    themes = attach_theme_shares(report.themes, report.review_count)
    avg_rating = report.avg_rating
    sentiment = report.sentiment
    if scrubbed_reviews is not None:
        if avg_rating is None:
            avg_rating = compute_avg_rating(scrubbed_reviews)
        if sentiment is None:
            sentiment = compute_sentiment(scrubbed_reviews)
    return report.model_copy(update={"themes": themes, "avg_rating": avg_rating, "sentiment": sentiment})
