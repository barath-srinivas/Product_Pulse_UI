"""Render output models for Google Docs plain-text sections and Gmail teasers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocStructuredReport(BaseModel):
    section_anchor: str
    product_id: str
    iso_week: str
    document_id: str
    content: str


class EmailPayload(BaseModel):
    idempotency_key: str
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    subject: str
    body_html: str
    body_text: str
    doc_url: str | None = None
