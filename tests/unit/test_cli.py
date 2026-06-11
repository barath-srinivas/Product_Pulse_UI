"""Unit tests for pulse CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pulse.cli import main
from pulse.ledger.models import RunRecord
from pulse.ledger.store import LedgerStore
from pulse.orchestrator import OrchestratorResult


def test_run_delegates_to_orchestrator() -> None:
    mock_run = MagicMock(
        return_value=OrchestratorResult(
            run=RunRecord(
                run_id="run-1",
                product_id="groww",
                iso_week="2026-W24",
                status="completed",
                section_anchor="groww-2026-W24",
                review_count=10,
                doc_document_id="doc-1",
                email_mode="draft",
                started_at="2026-06-08T10:00:00+05:30",  # type: ignore[arg-type]
            )
        )
    )
    with patch("pulse.cli.PulseOrchestrator") as orch_cls:
        orch_cls.return_value.run = mock_run
        exit_code = main(["run", "--product", "groww", "--week", "2026-W24", "--mock-llm"])

    assert exit_code == 0
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs.get("dry_run", False) is False


def test_dry_run_writes_report_without_delivery(tmp_path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from pulse.pipeline.models import PulseReport

    report = PulseReport(
        product_id="groww",
        iso_week="2026-W24",
        period_label="Last 10 weeks (Google Play)",
        generated_at=datetime.now(ZoneInfo("Asia/Kolkata")),
        review_count=5,
        themes=[],
        audience_blurb="test",
    )
    mock_run = MagicMock(
        return_value=OrchestratorResult(
            run=None,
            report=report,
            doc_report=None,
            email_payload=None,
        )
    )
    out_path = tmp_path / "report.json"
    with patch("pulse.cli.PulseOrchestrator") as orch_cls:
        orch_cls.return_value.run = mock_run
        exit_code = main(
            ["dry-run", "--product", "groww", "--week", "2026-W24", "--out", str(out_path)]
        )

    assert exit_code == 0
    mock_run.assert_called_once_with(
        "groww",
        iso_week="2026-W24",
        mock_llm=False,
        dry_run=True,
    )
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["product_id"] == "groww"


def test_dry_run_does_not_touch_delivery_client(tmp_path) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from pulse.pipeline.models import PulseReport

    report = PulseReport(
        product_id="groww",
        iso_week="2026-W24",
        period_label="Last 10 weeks (Google Play)",
        generated_at=datetime.now(ZoneInfo("Asia/Kolkata")),
        review_count=5,
        themes=[],
        audience_blurb="test",
    )
    with (
        patch("pulse.cli.PulseOrchestrator") as orch_cls,
        patch("pulse.orchestrator.GoogleMcpClient") as client_cls,
    ):
        orch_cls.return_value.run.return_value = OrchestratorResult(run=None, report=report)
        out_path = tmp_path / "report.json"
        exit_code = main(["dry-run", "--product", "groww", "--out", str(out_path)])

    assert exit_code == 0
    client_cls.from_config.assert_not_called()


def test_status_shows_not_found(tmp_path) -> None:
    ledger = LedgerStore(db_path=tmp_path / "ledger.db")
    with patch("pulse.cli.LedgerStore", return_value=ledger):
        exit_code = main(["status", "--product", "groww", "--week", "2026-W01"])

    assert exit_code == 0


def test_status_shows_record(tmp_path) -> None:
    ledger = LedgerStore(db_path=tmp_path / "ledger.db")
    record = ledger.create_run(
        product_id="groww",
        iso_week="2026-W24",
        section_anchor="groww-2026-W24",
        email_mode="draft",
    )
    record.status = "completed"
    ledger.update_run(record)

    with patch("pulse.cli.LedgerStore", return_value=ledger):
        exit_code = main(["status", "--product", "groww", "--week", "2026-W24"])

    assert exit_code == 0


def test_invalid_product_rejected() -> None:
    with pytest.raises(SystemExit, match="unknown product_id"):
        main(["run", "--product", "kuvera"])


def test_invalid_iso_week_rejected() -> None:
    with pytest.raises(SystemExit, match="invalid ISO week"):
        main(["run", "--product", "groww", "--week", "2026-23"])


def test_backfill_iterates_weeks() -> None:
    mock_run = MagicMock(
        side_effect=[
            OrchestratorResult(run=None, skipped=True),
            OrchestratorResult(run=None, skipped=True),
        ]
    )
    with patch("pulse.cli.PulseOrchestrator") as orch_cls:
        orch_cls.return_value.run = mock_run
        exit_code = main(
            [
                "backfill",
                "--product",
                "groww",
                "--from-week",
                "2026-W22",
                "--to-week",
                "2026-W23",
            ]
        )

    assert exit_code == 0
    assert mock_run.call_count == 2
