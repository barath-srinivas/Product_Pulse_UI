"""Unit tests for plain-text Doc section rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulse.pipeline.models import PulseReport
from pulse.render.report import render_doc_report, section_anchor

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE_REPORT_PATH = FIXTURES / "report_groww_sample.json"
SAMPLE_DOC_SECTION_PATH = FIXTURES / "doc_section_groww_sample.json"


@pytest.fixture
def sample_report() -> PulseReport:
    raw = json.loads(SAMPLE_REPORT_PATH.read_text(encoding="utf-8"))
    return PulseReport.model_validate(raw)


def test_section_anchor_from_product_and_week() -> None:
    assert section_anchor("groww", "2026-W24") == "groww-2026-W24"


def test_render_doc_structure(sample_report: PulseReport) -> None:
    doc = render_doc_report(
        sample_report,
        display_name="Groww",
        document_id="test-doc-id",
    )

    assert doc.section_anchor == "groww-2026-W24"
    assert doc.product_id == "groww"
    assert doc.iso_week == "2026-W24"
    assert doc.document_id == "test-doc-id"

    content = doc.content
    assert "Groww — Weekly Review Pulse — 2026-W24" in content
    assert "[anchor:groww-2026-W24]" in content
    assert "Period: Last 10 weeks (Google Play) · Reviews analyzed: 32" in content

    for heading in ("Top themes", "Real user quotes", "Action ideas", "Who this helps"):
        assert heading in content

    assert content.count("• 1. Theme cluster 0") == 1
    assert content.count('• "The app freezes exactly when the market opens') == 1
    assert "• Investigate reported issues and prioritize fixes." in content
    assert "product and support teams" in content.lower()


def test_render_doc_section_spacing(sample_report: PulseReport) -> None:
    doc = render_doc_report(
        sample_report,
        display_name="Groww",
        document_id="test-doc-id",
    )
    assert doc.content.startswith("\n\nGroww — Weekly Review Pulse")
    assert doc.content.endswith("\n\n")


def test_render_doc_matches_fixture(sample_report: PulseReport) -> None:
    doc = render_doc_report(
        sample_report,
        display_name="Groww",
        document_id="<GOOGLE_DOC_ID>",
    )
    expected = json.loads(SAMPLE_DOC_SECTION_PATH.read_text(encoding="utf-8"))
    actual = json.loads(doc.model_dump_json())
    assert actual == expected
