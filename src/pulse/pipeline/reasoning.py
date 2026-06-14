"""End-to-end Phase 2 reasoning pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from pulse.config import PulseConfig
from pulse.ingest.models import Review
from pulse.pipeline.cluster import cluster_reviews
from pulse.pipeline.embed import embed_reviews
from pulse.pipeline.exceptions import ClusteringError, EmptyCorpusError, PipelineError
from pulse.pipeline.llm_budget import LlmBudgetTracker
from pulse.pipeline.analytics import (
    attach_theme_shares,
    compute_avg_rating,
    compute_sentiment,
)
from pulse.pipeline.models import PulseReport, ReasoningResult, ThemeInsight
from pulse.pipeline.scrub import scrub_reviews
from pulse.pipeline.summarize import build_summarizer
from pulse.pipeline.validate import build_theme_insight

logger = logging.getLogger(__name__)

MAX_REPROMPTS_PER_THEME = 1


def run_reasoning_pipeline(
    reviews: list[Review],
    *,
    product_id: str,
    iso_week: str,
    config: PulseConfig,
    mock_llm: bool = False,
) -> ReasoningResult:
    """Scrub → embed → cluster → Groq LLM → validate → PulseReport."""
    scrubbed = scrub_reviews(reviews, enabled=config.safety.pii_scrub)
    if not scrubbed:
        raise EmptyCorpusError("no reviews remain after scrubbing")

    embeddings = embed_reviews(
        scrubbed,
        config.embeddings,
        iso_week=iso_week,
        product_id=product_id,
    )

    try:
        clusters, noise_ratio = cluster_reviews(scrubbed, embeddings, config.clustering)
    except ClusteringError as exc:
        raise PipelineError(str(exc)) from exc

    corpus = {r.review_id: r for r in scrubbed}
    budget = LlmBudgetTracker(config=config.llm)
    daily_used = budget._load_daily_tokens()
    daily_cap = config.llm.rate_limits.tokens_per_day
    if daily_used >= daily_cap * 0.85:
        logger.warning(
            "Groq daily token usage high (%s / %s); rate limits likely until quota resets",
            daily_used,
            daily_cap,
        )
    summarizer = build_summarizer(config.llm, budget, mock=mock_llm)

    total_reviews = len(scrubbed)
    themes: list[ThemeInsight] = []
    for rank, cluster in enumerate(clusters, start=1):
        share_pct = round(cluster.size / total_reviews * 100, 1) if total_reviews else 0.0
        insight = _summarize_cluster_with_retry(
            summarizer=summarizer,
            cluster=cluster,
            rank=rank,
            corpus=corpus,
            config=config,
            review_count=cluster.size,
            review_share_pct=share_pct,
        )
        if insight is not None:
            themes.append(insight)

    if not themes:
        raise PipelineError("no valid themes after Groq summarization and quote validation")

    themes = attach_theme_shares(themes, total_reviews)
    theme_names = [t.theme_name for t in themes]
    audience_blurb = summarizer.summarize_audience(theme_names)

    timezone = ZoneInfo(config.timezone)
    report = PulseReport(
        product_id=product_id,
        iso_week=iso_week,
        period_label=f"Last {config.review_window_weeks} weeks (Google Play)",
        generated_at=datetime.now(timezone),
        review_count=total_reviews,
        themes=themes,
        audience_blurb=audience_blurb,
        llm_provider=config.llm.provider,
        llm_model=config.llm.model,
        avg_rating=compute_avg_rating(scrubbed),
        sentiment=compute_sentiment(scrubbed),
    )

    return ReasoningResult(
        report=report,
        cluster_count=len(clusters),
        noise_ratio=noise_ratio,
        llm_requests=budget.run_requests,
        llm_tokens_used=budget.run_tokens,
    )


def _summarize_cluster_with_retry(
    *,
    summarizer,
    cluster,
    rank: int,
    corpus: dict,
    config: PulseConfig,
    review_count: int,
    review_share_pct: float,
) -> ThemeInsight | None:
    response = summarizer.summarize_cluster(cluster)
    insight = build_theme_insight(
        cluster_id=cluster.cluster_id,
        rank=rank,
        response=response,
        corpus=corpus,
        safety=config.safety,
        review_count=review_count,
        review_share_pct=review_share_pct,
    )
    if insight is not None:
        return insight

    for _ in range(MAX_REPROMPTS_PER_THEME):
        logger.info(
            "re-prompting Groq for cluster %s after quote validation failure",
            cluster.cluster_id,
        )
        response = summarizer.summarize_cluster(cluster)
        insight = build_theme_insight(
            cluster_id=cluster.cluster_id,
            rank=rank,
            response=response,
            corpus=corpus,
            safety=config.safety,
            review_count=review_count,
            review_share_pct=review_share_pct,
        )
        if insight is not None:
            return insight
    return None
