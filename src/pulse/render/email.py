"""Render PulseReport into a Gmail teaser payload."""

from __future__ import annotations

import html

from pulse.pipeline.models import PulseReport, ThemeInsight
from pulse.render.models import EmailPayload


def idempotency_key(product_id: str, iso_week: str) -> str:
    """Stable Gmail idempotency key for weekly delivery."""
    return f"pulse/{product_id}/{iso_week}"


def doc_url_for_document(document_id: str, *, heading_id: str | None = None) -> str:
    """Build a Google Doc URL, optionally with a heading deep link."""
    base = f"https://docs.google.com/document/d/{document_id}/edit"
    if heading_id:
        return f"{base}#heading={heading_id}"
    return base


def _intro_sentences(display_name: str, iso_week: str, review_count: int) -> str:
    return (
        f"This week's {display_name} Review Pulse ({iso_week}) summarizes "
        f"{review_count} Google Play reviews. "
        f"Below are the top themes; the full report with quotes and action ideas "
        f"is in the shared Google Doc."
    )


def _is_generic_theme_name(name: str) -> bool:
    return name.strip().lower().startswith("theme cluster")


def _normalize_theme_summary(summary: str) -> str:
    """Strip mock-LLM filler so teaser bullets read as headlines."""
    text = summary.strip()
    prefix = "Users mention: "
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip()
    return text


def _truncate_teaser(line: str, max_length: int) -> str:
    if len(line) <= max_length:
        return line
    return line[: max_length - 3].rstrip() + "..."


def theme_teaser_line(theme: ThemeInsight) -> str:
    """One email bullet: theme headline plus a short summary (teaser, not full quotes)."""
    name = theme.theme_name.strip()
    summary = _normalize_theme_summary(theme.theme_summary)

    if _is_generic_theme_name(name):
        # Mock/dev runs use generic names — show a short summary snippet only.
        return _truncate_teaser(summary or name, max_length=60)
    if summary:
        return _truncate_teaser(f"{name} — {summary}", max_length=120)
    return name


def _top_theme_lines(report: PulseReport, *, max_bullets: int) -> list[str]:
    themes = sorted(report.themes, key=lambda t: t.rank)
    return [theme_teaser_line(theme) for theme in themes[:max_bullets]]


def render_email_teaser(
    report: PulseReport,
    *,
    display_name: str,
    to: list[str],
    cc: list[str],
    document_id: str,
    doc_url: str | None = None,
    max_theme_bullets: int = 3,
) -> EmailPayload:
    """Build a teaser-only email payload (no full quotes or action lists)."""
    resolved_doc_url = doc_url or doc_url_for_document(document_id)
    intro = _intro_sentences(display_name, report.iso_week, report.review_count)
    theme_lines = _top_theme_lines(report, max_bullets=max_theme_bullets)

    bullet_text = "\n".join(f"• {line}" for line in theme_lines)
    body_text = (
        f"{intro}\n\n"
        f"Top themes:\n{bullet_text}\n\n"
        f"Read full report: {resolved_doc_url}"
    )

    theme_items_html = "".join(f"<li>{html.escape(line)}</li>" for line in theme_lines)
    body_html = (
        f"<p>{html.escape(intro)}</p>"
        f"<p><strong>Top themes:</strong></p>"
        f"<ul>{theme_items_html}</ul>"
        f'<p><a href="{html.escape(resolved_doc_url, quote=True)}">Read full report</a></p>'
    )

    subject = f"{display_name} Weekly Review Pulse — {report.iso_week}"

    return EmailPayload(
        idempotency_key=idempotency_key(report.product_id, report.iso_week),
        to=list(to),
        cc=list(cc),
        subject=subject,
        body_html=body_html,
        body_text=body_text,
        doc_url=resolved_doc_url,
    )
