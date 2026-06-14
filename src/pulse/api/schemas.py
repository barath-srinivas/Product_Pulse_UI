"""API request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PipelineStepStatus = Literal["pending", "active", "completed", "failed"]


class ThemeItem(BaseModel):
    theme_name: str
    review_share_pct: float
    review_count: int
    rank: int
    icon: str = ""


class OverviewResponse(BaseModel):
    product_id: str
    display_name: str
    iso_week: str
    review_count: int
    theme_count: int
    avg_rating: float | None


class TopThemesResponse(BaseModel):
    product_id: str
    iso_week: str
    themes: list[ThemeItem]


class TrendPoint(BaseModel):
    iso_week: str
    theme_name: str
    review_share_pct: float


class TrendsResponse(BaseModel):
    product_id: str
    weeks: list[str]
    series: list[TrendPoint]


class EmergingIssue(BaseModel):
    theme_name: str
    change_pct: float


class CustomerVoiceResponse(BaseModel):
    product_id: str
    iso_week: str
    review_count: int
    positive_pct: float
    negative_pct: float
    neutral_pct: float
    top_themes: list[ThemeItem]
    emerging_issues: list[EmergingIssue]


class PipelineStep(BaseModel):
    id: str
    label: str
    status: PipelineStepStatus


class RunTriggerRequest(BaseModel):
    product: str = "groww"
    week: str | None = None
    force: bool = False
    force_delivery: bool = False
    mock_llm: bool = False
    dry_run: bool = False


class BackfillRequest(BaseModel):
    product: str = "groww"
    from_week: str
    to_week: str
    force: bool = False
    force_delivery: bool = False
    mock_llm: bool = False
    stop_on_error: bool = False


class BackfillTriggerResponse(BaseModel):
    job_id: str
    status: str = "started"
    weeks: list[str]


class RunSummary(BaseModel):
    run_id: str
    product_id: str
    iso_week: str
    status: str
    review_count: int | None
    doc_document_id: str | None = None
    gmail_draft_count: int = 0
    started_at: datetime
    completed_at: datetime | None
    error: str | None


class RunDetailResponse(RunSummary):
    job_type: Literal["run", "backfill"] = "run"
    pipeline_steps: list[PipelineStep] = Field(default_factory=list)
    backfill_weeks: list[str] | None = None
    backfill_current_week: str | None = None
    backfill_completed: list[str] = Field(default_factory=list)
    backfill_skipped: list[str] = Field(default_factory=list)
    backfill_failed: dict[str, str] = Field(default_factory=dict)


class RunListResponse(BaseModel):
    runs: list[RunSummary]
