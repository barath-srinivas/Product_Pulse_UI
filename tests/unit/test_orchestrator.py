"""Unit tests for pulse orchestrator."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from pulse.config import load_config
from pulse.delivery.google_mcp_client import AppendResult, DraftResult
from pulse.ingest.models import IngestResult, Review
from pulse.ledger.store import LedgerStore
from pulse.orchestrator import OrchestratorError, PulseOrchestrator
from pulse.pipeline.models import PulseReport
from pulse.pipeline.reasoning import run_reasoning_pipeline


def _save_report_to(runs_dir: Path, report: PulseReport) -> Path:
    path = runs_dir / report.product_id / report.iso_week / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_report_from(runs_dir: Path, product_id: str, iso_week: str) -> PulseReport:
    path = runs_dir / product_id / iso_week / "report.json"
    return PulseReport.model_validate_json(path.read_text(encoding="utf-8"))


def _fixture_reviews() -> list[Review]:
    path = Path(__file__).parent.parent / "fixtures" / "reasoning_reviews_sample.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Review.model_validate(item) for item in raw]


def _mock_ingest(**kwargs) -> IngestResult:
    reviews = _fixture_reviews()
    iso_week = kwargs.get("iso_week", "2026-W24")
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return IngestResult(
        product_id="groww",
        iso_week=iso_week,
        package="com.nextbillion.groww",
        reviews=reviews,
        actual_reviews_path="data/reviews/groww_actual.json",
        normalized_reviews_path="data/reviews/groww_normalized.json",
        review_count=len(reviews),
        raw_review_count=len(reviews),
        filtered_out_count=0,
        window_start=date(2026, 3, 1),
        window_end=date(2026, 6, 8),
        fetched_at=now,
    )


@pytest.fixture
def config(config_dir):
    return load_config(config_dir)


@pytest.fixture
def ledger(tmp_path) -> LedgerStore:
    return LedgerStore(db_path=tmp_path / "ledger.db")


@pytest.fixture
def mock_delivery() -> MagicMock:
    client = MagicMock()
    client.health_check.return_value = True
    client.append_to_doc.return_value = AppendResult(document_id="doc-123", appended_chars=100)
    client.create_email_draft.side_effect = lambda to, subject, body: DraftResult(
        draft_id=f"draft-{to}",
        message_id=f"msg-{to}",
        to=to,
        subject=subject,
    )
    return client


def _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch) -> PulseOrchestrator:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("pulse.ledger.store.get_runs_dir", lambda: runs_dir)

    def artifact_path(pid: str, week: str) -> Path:
        return runs_dir / pid / week / "report.json"

    monkeypatch.setattr("pulse.orchestrator.report_artifact_path", artifact_path)
    monkeypatch.setattr(
        "pulse.orchestrator._save_report",
        lambda report: _save_report_to(runs_dir, report),
    )
    monkeypatch.setattr(
        "pulse.orchestrator._load_report",
        lambda pid, week: _load_report_from(runs_dir, pid, week),
    )

    def reasoning_fn(reviews, *, product_id, iso_week, config, mock_llm=False):
        return run_reasoning_pipeline(
            reviews,
            product_id=product_id,
            iso_week=iso_week,
            config=config,
            mock_llm=True,
        )

    config.pulse.embeddings.provider = "tfidf"
    return PulseOrchestrator(
        config,
        ledger=ledger,
        delivery_client=mock_delivery,
        ingest_fn=_mock_ingest,
        reasoning_fn=reasoning_fn,
    )


def test_full_run_records_completed(config, ledger, mock_delivery, tmp_path, monkeypatch) -> None:
    orch = _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch)
    result = orch.run("groww", iso_week="2026-W24", mock_llm=True)

    assert result.skipped is False
    assert result.run is not None
    assert result.run.status == "completed"
    assert result.run.doc_document_id == "doc-123"
    assert len(result.run.gmail_drafts) == 2
    mock_delivery.append_to_doc.assert_called_once()
    assert mock_delivery.create_email_draft.call_count == 2
    assert (tmp_path / "runs" / "groww" / "2026-W24" / "report.json").exists()


def test_rerun_completed_week_is_skipped(
    config, ledger, mock_delivery, tmp_path, monkeypatch
) -> None:
    orch = _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch)
    orch.run("groww", iso_week="2026-W24", mock_llm=True)

    mock_delivery.reset_mock()
    second = orch.run("groww", iso_week="2026-W24", mock_llm=True)

    assert second.skipped is True
    mock_delivery.append_to_doc.assert_not_called()
    mock_delivery.create_email_draft.assert_not_called()


def test_force_recomputes_without_duplicate_delivery(
    config, ledger, mock_delivery, tmp_path, monkeypatch
) -> None:
    orch = _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch)
    first = orch.run("groww", iso_week="2026-W24", mock_llm=True)

    mock_delivery.reset_mock()
    second = orch.run("groww", iso_week="2026-W24", force=True, mock_llm=True)

    assert second.skipped is False
    assert second.run is not None
    assert second.run.status == "completed"
    mock_delivery.append_to_doc.assert_not_called()
    mock_delivery.create_email_draft.assert_not_called()
    assert first.run is not None
    assert second.run.run_id != first.run.run_id


def test_from_stage_delivery_retries_email_only(
    config, ledger, mock_delivery, tmp_path, monkeypatch
) -> None:
    orch = _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch)
    orch.run("groww", iso_week="2026-W24", mock_llm=True)

    run = ledger.get_latest_run("groww", "2026-W24")
    assert run is not None
    run.status = "delivering"
    run.gmail_drafts = []
    run.gmail_draft_id = None
    run.gmail_message_id = None
    ledger.update_run(run)

    mock_delivery.reset_mock()
    result = orch.run("groww", iso_week="2026-W24", from_stage="delivery")

    assert result.run is not None
    assert result.run.status == "completed"
    mock_delivery.append_to_doc.assert_not_called()
    assert mock_delivery.create_email_draft.call_count == 2


def test_partial_email_failure_preserves_drafts(
    config, ledger, mock_delivery, tmp_path, monkeypatch
) -> None:
    orch = _orchestrator(config, ledger, mock_delivery, tmp_path, monkeypatch)
    orch.run("groww", iso_week="2026-W24", mock_llm=True)

    run = ledger.get_latest_run("groww", "2026-W24")
    assert run is not None
    run.status = "delivering"
    run.gmail_drafts = []
    ledger.update_run(run)

    calls = {"count": 0}

    def flaky_draft(to, subject, body):
        calls["count"] += 1
        if calls["count"] == 2:
            from pulse.delivery.google_mcp_client import DeliveryApiError

            raise DeliveryApiError("simulated failure")
        return DraftResult(draft_id=f"draft-{to}", message_id=f"msg-{to}", to=to, subject=subject)

    mock_delivery.create_email_draft.side_effect = flaky_draft
    mock_delivery.reset_mock()
    mock_delivery.health_check.return_value = True

    with pytest.raises(OrchestratorError):
        orch.run("groww", iso_week="2026-W24", from_stage="delivery")

    resumed = ledger.get_latest_run("groww", "2026-W24")
    assert resumed is not None
    assert len(resumed.gmail_drafts) == 1

    mock_delivery.create_email_draft.side_effect = lambda to, subject, body: DraftResult(
        draft_id=f"draft-{to}",
        message_id=f"msg-{to}",
        to=to,
        subject=subject,
    )
    result = orch.run("groww", iso_week="2026-W24", from_stage="delivery")
    assert result.run is not None
    assert len(result.run.gmail_drafts) == 2
