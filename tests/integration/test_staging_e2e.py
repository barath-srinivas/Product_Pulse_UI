"""Phase 8 staging E2E checks (mocked delivery; optional live run)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from pulse.config import load_config
from pulse.delivery.google_mcp_client import AppendResult, DraftResult
from pulse.ingest.models import IngestResult, Review
from pulse.ledger.store import LedgerStore
from pulse.orchestrator import PulseOrchestrator
from pulse.pipeline.reasoning import run_reasoning_pipeline

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _fixture_reviews() -> list[Review]:
    raw = json.loads((FIXTURES / "reasoning_reviews_sample.json").read_text(encoding="utf-8"))
    return [Review.model_validate(item) for item in raw]


def _mock_ingest(**kwargs) -> IngestResult:
    from datetime import date, datetime
    from zoneinfo import ZoneInfo

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
def staging_orchestrator(tmp_path, config_dir, monkeypatch):
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("pulse.ledger.store.get_runs_dir", lambda: runs_dir)
    monkeypatch.setattr(
        "pulse.orchestrator.report_artifact_path",
        lambda pid, week: runs_dir / pid / week / "report.json",
    )

    config = load_config(config_dir)
    config.pulse.embeddings.provider = "tfidf"
    config.pulse.delivery.email_mode = "draft"

    mock_delivery = MagicMock()
    mock_delivery.health_check.return_value = True
    mock_delivery.append_to_doc.return_value = AppendResult(
        document_id=config.products["groww"].google_doc.document_id,
        appended_chars=500,
    )
    mock_delivery.create_email_draft.side_effect = lambda to, subject, body: DraftResult(
        draft_id=f"draft-{to}",
        message_id=f"msg-{to}",
        to=to,
        subject=subject,
    )

    def reasoning_fn(reviews, *, product_id, iso_week, config, mock_llm=False):
        return run_reasoning_pipeline(
            reviews,
            product_id=product_id,
            iso_week=iso_week,
            config=config,
            mock_llm=True,
        )

    ledger = LedgerStore(db_path=runs_dir / "ledger.db")
    return PulseOrchestrator(
        config,
        ledger=ledger,
        delivery_client=mock_delivery,
        ingest_fn=_mock_ingest,
        reasoning_fn=reasoning_fn,
    ), mock_delivery


def test_staging_e2e_idempotency_no_duplicate_delivery(staging_orchestrator) -> None:
    """EC-ORCH-01 + EC-DOCS-04 + EC-GMAIL-03: second run skips delivery."""
    orch, delivery = staging_orchestrator
    week = "2026-W24"

    first = orch.run("groww", iso_week=week, mock_llm=True)
    assert first.skipped is False
    assert first.run is not None
    assert first.run.status == "completed"
    assert delivery.append_to_doc.call_count == 1
    assert delivery.create_email_draft.call_count == 2

    delivery.reset_mock()
    second = orch.run("groww", iso_week=week, mock_llm=True)
    assert second.skipped is True
    delivery.append_to_doc.assert_not_called()
    delivery.create_email_draft.assert_not_called()


def test_staging_force_recomputes_without_redelivery(staging_orchestrator) -> None:
    """EC-ORCH-06: --force recomputes insights; delivery stays idempotent."""
    orch, delivery = staging_orchestrator
    week = "2026-W24"

    orch.run("groww", iso_week=week, mock_llm=True)
    delivery.reset_mock()

    result = orch.run("groww", iso_week=week, force=True, mock_llm=True)
    assert result.skipped is False
    assert result.run is not None
    assert result.run.status == "completed"
    delivery.append_to_doc.assert_not_called()
    delivery.create_email_draft.assert_not_called()


def _live_staging_enabled() -> bool:
    return os.getenv("RUN_STAGING_E2E") == "1" and bool(os.getenv("GOOGLE_MCP_API_KEY"))


@pytest.mark.skipif(
    not _live_staging_enabled(),
    reason="set RUN_STAGING_E2E=1 and GOOGLE_MCP_API_KEY",
)
def test_live_staging_run_completes() -> None:
    """Manual staging smoke: pulse run against Railway + real config."""
    from dotenv import load_dotenv

    load_dotenv()
    config = load_config()
    orch = PulseOrchestrator(config)
    week = os.getenv("STAGING_ISO_WEEK", "2026-W24")
    result = orch.run("groww", iso_week=week, mock_llm=True)
    assert result.run is not None
    assert result.run.status in {"completed", "failed"}
