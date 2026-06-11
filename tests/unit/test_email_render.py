"""Unit tests for Gmail teaser email rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pulse.pipeline.models import PulseReport
from pulse.render.email import idempotency_key, render_email_teaser

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
SAMPLE_REPORT_PATH = FIXTURES / "report_groww_sample.json"
SAMPLE_EMAIL_PATH = FIXTURES / "email_groww_sample.json"


@pytest.fixture
def sample_report() -> PulseReport:
    raw = json.loads(SAMPLE_REPORT_PATH.read_text(encoding="utf-8"))
    return PulseReport.model_validate(raw)


def test_idempotency_key_format() -> None:
    assert idempotency_key("groww", "2026-W24") == "pulse/groww/2026-W24"


def test_email_teaser_has_no_full_quotes(sample_report: PulseReport) -> None:
    email = render_email_teaser(
        sample_report,
        display_name="Groww",
        to=["product@groww.example"],
        cc=[],
        document_id="test-doc-id",
    )

    for theme in sample_report.themes:
        for quote in theme.quotes:
            assert quote.text not in email.body_text
            assert quote.text not in email.body_html

    for theme in sample_report.themes:
        for idea in theme.action_ideas:
            assert idea not in email.body_text
            assert idea not in email.body_html


def test_email_teaser_top_three_themes_only(sample_report: PulseReport) -> None:
    email = render_email_teaser(
        sample_report,
        display_name="Groww",
        to=["product@groww.example"],
        cc=[],
        document_id="test-doc-id",
    )

    assert email.subject == "Groww Weekly Review Pulse — 2026-W24"
    assert email.idempotency_key == "pulse/groww/2026-W24"
    assert "app freezes" in email.body_text.lower()
    assert "easy to use" in email.body_text.lower()
    assert "brokerage charges" in email.body_text.lower()
    assert "..." in email.body_text

    assert "Theme cluster" not in email.body_text

    assert "Read full report" in email.body_html
    assert "https://docs.google.com/document/d/test-doc-id/edit" in email.doc_url


def test_email_teaser_matches_fixture(sample_report: PulseReport) -> None:
    email = render_email_teaser(
        sample_report,
        display_name="Groww",
        to=["product@groww.example", "support@groww.example"],
        cc=[],
        document_id="<GOOGLE_DOC_ID>",
    )
    expected = json.loads(SAMPLE_EMAIL_PATH.read_text(encoding="utf-8"))
    actual = json.loads(email.model_dump_json())
    assert actual == expected
