"""Reasoning pipeline data models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScrubbedReview(BaseModel):
    review_id: str
    product_id: str
    rating: int | None = Field(default=None, ge=1, le=5)
    body: str
    review_date: date


class ThemeCluster(BaseModel):
    cluster_id: int
    review_ids: list[str]
    size: int
    sample_texts: list[str]
    mean_rating: float | None = None


class ValidatedQuote(BaseModel):
    text: str
    review_id: str
    validation: Literal["exact", "normalized"]


class ThemeInsight(BaseModel):
    cluster_id: int
    theme_name: str
    theme_summary: str
    quotes: list[ValidatedQuote]
    action_ideas: list[str]
    rank: int


class PulseReport(BaseModel):
    product_id: str
    iso_week: str
    period_label: str
    generated_at: datetime
    review_count: int
    themes: list[ThemeInsight]
    audience_blurb: str
    llm_provider: str = "groq"
    llm_model: str = ""


class LlmQuoteCandidate(BaseModel):
    text: str
    review_id: str


class LlmThemeResponse(BaseModel):
    theme_name: str
    theme_summary: str
    quotes: list[LlmQuoteCandidate] = Field(default_factory=list)
    action_ideas: list[str] = Field(default_factory=list)


class ReasoningResult(BaseModel):
    report: PulseReport
    cluster_count: int
    noise_ratio: float
    llm_requests: int
    llm_tokens_used: int
