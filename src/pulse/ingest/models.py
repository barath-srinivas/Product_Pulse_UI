"""Ingestion data models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Review(BaseModel):
    """In-memory review used by the ingest pipeline."""

    review_id: str
    product_id: str
    source: Literal["google_play"] = "google_play"
    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = None
    body: str
    reviewer_name: str | None = None
    review_date: date
    fetched_at: datetime
    language: str | None = None

    def display_text(self) -> str:
        """Combined text used for embedding in later phases."""
        if self.title and self.body:
            return f"{self.title}\n{self.body}"
        return self.body or self.title or ""

    def to_stored_entry(self) -> StoredReviewEntry:
        """Serialize to the normalized reviews file format."""
        return StoredReviewEntry(
            product_id=self.product_id,
            rating=self.rating,
            body=self.body,
            review_date=self.review_date,
            language=self.language,
        )


class ActualReviewEntry(BaseModel):
    """Stored actual review with Play metadata fields removed."""

    content: str
    score: int | None = Field(default=None, ge=1, le=5)
    thumbsUpCount: int | None = None
    appVersion: str | None = None
    review_date: date


class StoredReviewEntry(BaseModel):
    """Stored normalized review without ids or reviewer PII."""

    product_id: str
    source: Literal["google_play"] = "google_play"
    rating: int | None = Field(default=None, ge=1, le=5)
    body: str
    review_date: date
    language: str | None = None


class ActualReviewsFile(BaseModel):
    product_id: str
    iso_week: str
    package: str
    fetched_at: datetime
    review_window_weeks: int
    window_start: date
    window_end: date
    review_count: int
    reviews: list[ActualReviewEntry]


class NormalizedReviewsFile(BaseModel):
    product_id: str
    iso_week: str
    package: str
    fetched_at: datetime
    review_window_weeks: int
    window_start: date
    window_end: date
    review_count: int
    filtered_out_count: int
    reviews: list[StoredReviewEntry]


class IngestResult(BaseModel):
    product_id: str
    iso_week: str
    package: str
    reviews: list[Review]
    actual_reviews_path: str
    normalized_reviews_path: str
    review_count: int
    raw_review_count: int
    filtered_out_count: int
    window_start: date
    window_end: date
    fetched_at: datetime
