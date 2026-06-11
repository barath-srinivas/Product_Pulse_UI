"""Run ledger data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal["pending", "ingesting", "reasoning", "delivering", "completed", "failed"]
EmailMode = Literal["draft", "send"]
PipelineStage = Literal["ingest", "reason", "render", "delivery"]


class GmailDraftRecord(BaseModel):
    to: str
    draft_id: str
    message_id: str


class RunRecord(BaseModel):
    run_id: str
    product_id: str
    iso_week: str
    status: RunStatus
    review_count: int | None = None
    section_anchor: str
    doc_document_id: str | None = None
    doc_revision_id: str | None = None
    gmail_message_id: str | None = None
    gmail_draft_id: str | None = None
    gmail_drafts: list[GmailDraftRecord] = Field(default_factory=list)
    email_mode: EmailMode
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None

    @property
    def run_key(self) -> str:
        return f"{self.product_id}:{self.iso_week}"

    def doc_delivered(self) -> bool:
        return bool(self.doc_document_id)

    def email_delivered(self, recipient_count: int) -> bool:
        return len(self.gmail_drafts) >= recipient_count and recipient_count > 0
