"""End-to-end pulse run coordinator with ledger-backed idempotency."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pulse.config import AppConfig, current_iso_week, load_config, normalize_iso_week
from pulse.delivery.google_mcp_client import DeliveryError, DraftResult, GoogleMcpClient
from pulse.ingest.models import IngestResult, Review
from pulse.ingest.play_store import ingest_groww_reviews
from pulse.ledger.models import GmailDraftRecord, PipelineStage, RunRecord
from pulse.ledger.store import LedgerStore, report_artifact_path
from pulse.pipeline.models import PulseReport, ReasoningResult
from pulse.pipeline.reasoning import run_reasoning_pipeline
from pulse.render.email import render_email_teaser
from pulse.render.models import DocStructuredReport, EmailPayload
from pulse.render.report import render_doc_report, section_anchor

logger = logging.getLogger(__name__)

STAGE_ORDER: dict[PipelineStage, int] = {
    "ingest": 0,
    "reason": 1,
    "render": 2,
    "delivery": 3,
}


@dataclass
class OrchestratorResult:
    run: RunRecord | None
    skipped: bool = False
    report: PulseReport | None = None
    doc_report: DocStructuredReport | None = None
    email_payload: EmailPayload | None = None


class OrchestratorError(Exception):
    """Raised when a pulse run cannot complete."""


def _log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str))


def _save_report(report: PulseReport) -> Path:
    path = report_artifact_path(report.product_id, report.iso_week)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_report(product_id: str, iso_week: str) -> PulseReport:
    path = report_artifact_path(product_id, iso_week)
    if not path.exists():
        raise OrchestratorError(
            f"report artifact not found: {path}; run full pipeline before --from-stage delivery"
        )
    return PulseReport.model_validate_json(path.read_text(encoding="utf-8"))


def _merge_draft_records(
    existing: list[GmailDraftRecord],
    new_results: list[DraftResult],
) -> list[GmailDraftRecord]:
    by_to = {draft.to: draft for draft in existing}
    for result in new_results:
        by_to[result.to] = GmailDraftRecord(
            to=result.to,
            draft_id=result.draft_id,
            message_id=result.message_id,
        )
    return list(by_to.values())


def _apply_drafts_to_record(record: RunRecord, drafts: list[GmailDraftRecord]) -> None:
    record.gmail_drafts = drafts
    if drafts:
        record.gmail_draft_id = drafts[0].draft_id
        record.gmail_message_id = drafts[0].message_id


class PulseOrchestrator:
    """Coordinate ingest → reason → render → delivery with run ledger guards."""

    def __init__(
        self,
        config: AppConfig,
        *,
        ledger: LedgerStore | None = None,
        delivery_client: GoogleMcpClient | None = None,
        ingest_fn: Callable[..., IngestResult] | None = None,
        reasoning_fn: Callable[..., ReasoningResult] | None = None,
    ) -> None:
        self.config = config
        self.ledger = ledger or LedgerStore()
        self.delivery_client = delivery_client
        self.ingest_fn = ingest_fn or ingest_groww_reviews
        self.reasoning_fn = reasoning_fn or run_reasoning_pipeline

    def run(
        self,
        product_id: str,
        *,
        iso_week: str | None = None,
        force: bool = False,
        force_delivery: bool = False,
        from_stage: PipelineStage = "ingest",
        mock_llm: bool = False,
        dry_run: bool = False,
    ) -> OrchestratorResult:
        resolved_week = (
            normalize_iso_week(iso_week) if iso_week else current_iso_week(self.config.pulse.timezone)
        )
        product = self.config.get_product(product_id)
        anchor = section_anchor(product_id, resolved_week)

        if dry_run:
            return self._run_dry(
                product_id=product_id,
                iso_week=resolved_week,
                mock_llm=mock_llm,
            )

        completed = self.ledger.get_completed_run(product_id, resolved_week)
        if completed and not force and from_stage == "ingest":
            _log_event(
                "run_skipped",
                product_id=product_id,
                iso_week=resolved_week,
                run_id=completed.run_id,
                reason="already_completed",
            )
            return OrchestratorResult(
                run=completed,
                skipped=True,
                report=_load_report_safe(product_id, resolved_week),
            )

        idempotency_source = completed or self.ledger.get_latest_run(product_id, resolved_week)
        run = self._begin_run(
            product_id=product_id,
            iso_week=resolved_week,
            section_anchor=anchor,
            existing=idempotency_source if force else None,
        )

        try:
            report = self._run_pipeline(
                run=run,
                product_id=product_id,
                iso_week=resolved_week,
                force=force,
                from_stage=from_stage,
                mock_llm=mock_llm,
                idempotency_source=idempotency_source,
            )
            doc_report = render_doc_report(
                report,
                display_name=product.display_name,
                document_id=product.google_doc.document_id,
            )
            email_payload = render_email_teaser(
                report,
                display_name=product.display_name,
                to=product.stakeholders.to,
                cc=product.stakeholders.cc,
                document_id=product.google_doc.document_id,
            )

            if STAGE_ORDER[from_stage] <= STAGE_ORDER["delivery"]:
                self._deliver(
                    run=run,
                    doc_report=doc_report,
                    email_payload=email_payload,
                    idempotency_source=idempotency_source,
                    force_delivery=force_delivery,
                )

            run = self.ledger.set_status(run, "completed", timezone=self.config.pulse.timezone)
            _log_event(
                "run_completed",
                run_id=run.run_id,
                product_id=product_id,
                iso_week=resolved_week,
                review_count=run.review_count,
            )
            return OrchestratorResult(
                run=run,
                report=report,
                doc_report=doc_report,
                email_payload=email_payload,
            )
        except Exception as exc:
            error = str(exc)
            run.error = error
            if run.status not in {"completed"}:
                run = self.ledger.set_status(
                    run,
                    "failed" if run.status != "delivering" else "delivering",
                    error=error,
                    timezone=self.config.pulse.timezone,
                )
            _log_event(
                "run_failed",
                run_id=run.run_id,
                product_id=product_id,
                iso_week=resolved_week,
                status=run.status,
                error=error,
            )
            raise OrchestratorError(error) from exc

    def _run_dry(
        self,
        *,
        product_id: str,
        iso_week: str,
        mock_llm: bool,
    ) -> OrchestratorResult:
        """Ingest → reason → render without ledger or delivery HTTP."""
        product = self.config.get_product(product_id)
        _log_event("dry_run_start", product_id=product_id, iso_week=iso_week)

        ingest_result = self.ingest_fn(
            iso_week=iso_week,
            config=self.config,
            force=False,
        )
        _log_event("stage_complete", stage="ingest", review_count=ingest_result.review_count)

        reasoning_result = self.reasoning_fn(
            ingest_result.reviews,
            product_id=product_id,
            iso_week=iso_week,
            config=self.config.pulse,
            mock_llm=mock_llm,
        )
        report = reasoning_result.report
        _log_event("stage_complete", stage="reason", theme_count=len(report.themes))

        doc_report = render_doc_report(
            report,
            display_name=product.display_name,
            document_id=product.google_doc.document_id,
        )
        email_payload = render_email_teaser(
            report,
            display_name=product.display_name,
            to=product.stakeholders.to,
            cc=product.stakeholders.cc,
            document_id=product.google_doc.document_id,
        )
        _log_event("dry_run_complete", product_id=product_id, iso_week=iso_week)

        return OrchestratorResult(
            run=None,
            report=report,
            doc_report=doc_report,
            email_payload=email_payload,
        )

    def _begin_run(
        self,
        *,
        product_id: str,
        iso_week: str,
        section_anchor: str,
        existing: RunRecord | None,
    ) -> RunRecord:
        if existing and existing.status in {"delivering", "failed", "pending"}:
            existing.error = None
            existing.section_anchor = section_anchor
            return self.ledger.update_run(existing)

        return self.ledger.create_run(
            product_id=product_id,
            iso_week=iso_week,
            section_anchor=section_anchor,
            email_mode=self.config.pulse.delivery.email_mode,
            timezone=self.config.pulse.timezone,
        )

    def _run_pipeline(
        self,
        *,
        run: RunRecord,
        product_id: str,
        iso_week: str,
        force: bool,
        from_stage: PipelineStage,
        mock_llm: bool,
        idempotency_source: RunRecord | None,
    ) -> PulseReport:
        if from_stage in {"render", "delivery"}:
            report = _load_report(product_id, iso_week)
            run.review_count = report.review_count
            self.ledger.update_run(run)
            _log_event("stage_skipped", stage="ingest", reason=f"from_stage_{from_stage}")
            _log_event("stage_skipped", stage="reason", reason=f"from_stage_{from_stage}")
            return report

        reviews: list[Review] | None = None
        if STAGE_ORDER[from_stage] <= STAGE_ORDER["ingest"]:
            run = self.ledger.set_status(run, "ingesting", timezone=self.config.pulse.timezone)
            _log_event("stage_start", stage="ingest", run_id=run.run_id)
            ingest_result = self.ingest_fn(
                iso_week=iso_week,
                config=self.config,
                force=force,
            )
            reviews = ingest_result.reviews
            run.review_count = ingest_result.review_count
            self.ledger.update_run(run)
            _log_event(
                "stage_complete",
                stage="ingest",
                run_id=run.run_id,
                review_count=ingest_result.review_count,
            )
        elif force:
            ingest_result = self.ingest_fn(
                iso_week=iso_week,
                config=self.config,
                force=force,
            )
            reviews = ingest_result.reviews
            run.review_count = ingest_result.review_count
            self.ledger.update_run(run)

        if STAGE_ORDER[from_stage] <= STAGE_ORDER["reason"]:
            run = self.ledger.set_status(run, "reasoning", timezone=self.config.pulse.timezone)
            _log_event("stage_start", stage="reason", run_id=run.run_id)
            if reviews is None:
                raise OrchestratorError("ingest stage required before reasoning")
            reasoning_result = self.reasoning_fn(
                reviews,
                product_id=product_id,
                iso_week=iso_week,
                config=self.config.pulse,
                mock_llm=mock_llm,
            )
            report = reasoning_result.report
            _save_report(report)
            run.review_count = report.review_count
            self.ledger.update_run(run)
            _log_event(
                "stage_complete",
                stage="reason",
                run_id=run.run_id,
                theme_count=len(report.themes),
            )
            return report

        return _load_report(product_id, iso_week)

    def _deliver(
        self,
        *,
        run: RunRecord,
        doc_report: DocStructuredReport,
        email_payload: EmailPayload,
        idempotency_source: RunRecord | None,
        force_delivery: bool = False,
    ) -> None:
        run = self.ledger.set_status(run, "delivering", timezone=self.config.pulse.timezone)
        client = self.delivery_client or GoogleMcpClient.from_config()

        _log_event("stage_start", stage="delivery", run_id=run.run_id)
        if not client.health_check():
            raise OrchestratorError("delivery API health check failed")

        delivery_state = idempotency_source or run
        if not force_delivery and delivery_state.doc_delivered():
            _log_event(
                "delivery_skipped",
                step="append_to_doc",
                run_id=run.run_id,
                document_id=delivery_state.doc_document_id,
            )
            run.doc_document_id = delivery_state.doc_document_id
            run.doc_revision_id = delivery_state.doc_revision_id
        else:
            append_result = client.append_to_doc(
                doc_id=doc_report.document_id,
                content=doc_report.content,
            )
            run.doc_document_id = append_result.document_id
            _log_event(
                "delivery_complete",
                step="append_to_doc",
                run_id=run.run_id,
                document_id=append_result.document_id,
                appended_chars=append_result.appended_chars,
            )

        recipients = list(email_payload.to)
        if not recipients:
            raise OrchestratorError("no email recipients configured in stakeholders.to")

        existing_drafts = [] if force_delivery else list(delivery_state.gmail_drafts)
        drafted_to = {draft.to for draft in existing_drafts}
        pending_recipients = [addr for addr in recipients if addr not in drafted_to]

        if (
            not force_delivery
            and not pending_recipients
            and delivery_state.email_delivered(len(recipients))
        ):
            _log_event("delivery_skipped", step="create_email_draft", run_id=run.run_id)
            _apply_drafts_to_record(run, existing_drafts)
        else:
            if self.config.pulse.delivery.email_mode != "draft":
                raise OrchestratorError(
                    "email_mode=send is not supported by the hosted delivery API; use draft"
                )
            new_results: list[DraftResult] = []
            try:
                for recipient in pending_recipients:
                    new_results.append(
                        client.create_email_draft(
                            recipient,
                            email_payload.subject,
                            email_payload.body_text,
                        )
                    )
            except DeliveryError:
                if new_results:
                    merged = _merge_draft_records(existing_drafts, new_results)
                    _apply_drafts_to_record(run, merged)
                    self.ledger.update_run(run)
                raise
            merged = _merge_draft_records(existing_drafts, new_results)
            _apply_drafts_to_record(run, merged)
            _log_event(
                "delivery_complete",
                step="create_email_draft",
                run_id=run.run_id,
                draft_count=len(merged),
            )

        self.ledger.update_run(run)
        _log_event("stage_complete", stage="delivery", run_id=run.run_id)


def _load_report_safe(product_id: str, iso_week: str) -> PulseReport | None:
    path = report_artifact_path(product_id, iso_week)
    if not path.exists():
        return None
    return PulseReport.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Run the Product Review Pulse pipeline")
    parser.add_argument("--product", default="groww", help="Product id (default: groww)")
    parser.add_argument("--week", help="ISO week YYYY-Www (default: current week IST)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute insights; delivery stays idempotent unless --force-delivery",
    )
    parser.add_argument(
        "--force-delivery",
        action="store_true",
        help="Re-append Doc section and create new Gmail drafts even if ledger shows delivered",
    )
    parser.add_argument(
        "--from-stage",
        choices=["ingest", "reason", "render", "delivery"],
        default="ingest",
        help="Start at a pipeline stage (delivery retries email/doc only)",
    )
    parser.add_argument(
        "--mock-llm",
        action="store_true",
        help="Use mock Groq summarizer (dev/tests)",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config()
        orchestrator = PulseOrchestrator(config)
        result = orchestrator.run(
            args.product,
            iso_week=args.week,
            force=args.force,
            force_delivery=args.force_delivery,
            from_stage=args.from_stage,  # type: ignore[arg-type]
            mock_llm=args.mock_llm,
        )
    except OrchestratorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    run = result.run
    if result.skipped:
        print(f"skipped=true run_id={run.run_id if run else 'n/a'}")
        return 0

    assert run is not None
    print(f"status={run.status}")
    print(f"run_id={run.run_id}")
    print(f"section_anchor={run.section_anchor}")
    print(f"review_count={run.review_count}")
    print(f"doc_document_id={run.doc_document_id}")
    print(f"gmail_draft_count={len(run.gmail_drafts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
