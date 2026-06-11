"""Phase 3 render: PulseReport → Doc plain-text section and Gmail teaser."""

from pulse.render.email import doc_url_for_document, idempotency_key, render_email_teaser
from pulse.render.models import DocStructuredReport, EmailPayload
from pulse.render.report import render_doc_report, section_anchor

__all__ = [
    "DocStructuredReport",
    "EmailPayload",
    "doc_url_for_document",
    "idempotency_key",
    "render_doc_report",
    "render_email_teaser",
    "section_anchor",
]
