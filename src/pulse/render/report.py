"""Render PulseReport into plain-text Google Doc section content."""

from __future__ import annotations

from pulse.pipeline.models import PulseReport
from pulse.render.models import DocStructuredReport


def section_anchor(product_id: str, iso_week: str) -> str:
    """Stable section anchor for Doc idempotency and deep links."""
    return f"{product_id}-{iso_week}"


def _anchor_marker(anchor: str) -> str:
    return f"[anchor:{anchor}]"


def _theme_bullet(rank: int, theme_name: str, theme_summary: str) -> str:
    return f"{rank}. {theme_name} — {theme_summary}"


def _quote_bullet(quote_text: str) -> str:
    return f'"{quote_text}"'


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _render_section_content(
    report: PulseReport,
    *,
    display_name: str,
    anchor: str,
) -> str:
    """Build plain-text Doc body (no heading/bullet formatting — append-only MCP)."""
    lines: list[str] = [
        (
            f"{display_name} — Weekly Review Pulse — {report.iso_week} "
            f"{_anchor_marker(anchor)}"
        ),
        "",
        f"Period: {report.period_label} · Reviews analyzed: {report.review_count}",
        "",
        "Top themes",
    ]

    for theme in sorted(report.themes, key=lambda t: t.rank):
        lines.append(f"• {_theme_bullet(theme.rank, theme.theme_name, theme.theme_summary)}")

    lines.extend(["", "Real user quotes"])
    for theme in sorted(report.themes, key=lambda t: t.rank):
        for quote in theme.quotes:
            lines.append(f"• {_quote_bullet(quote.text)}")

    lines.extend(["", "Action ideas"])
    action_ideas = _dedupe_preserve_order(
        idea for theme in sorted(report.themes, key=lambda t: t.rank) for idea in theme.action_ideas
    )
    for idea in action_ideas:
        lines.append(f"• {idea}")

    lines.extend(["", "Who this helps", report.audience_blurb])
    return "\n".join(lines)


def render_doc_report(
    report: PulseReport,
    *,
    display_name: str,
    document_id: str,
) -> DocStructuredReport:
    """Convert a PulseReport into plain-text content for Docs MCP append."""
    anchor = section_anchor(report.product_id, report.iso_week)
    return DocStructuredReport(
        section_anchor=anchor,
        product_id=report.product_id,
        iso_week=report.iso_week,
        document_id=document_id,
        content=_render_section_content(report, display_name=display_name, anchor=anchor),
    )
