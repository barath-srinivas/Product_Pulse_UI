"""Operator run trigger and status endpoints."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from pulse.api.schemas import (
    BackfillRequest,
    BackfillTriggerResponse,
    RunDetailResponse,
    RunListResponse,
    RunSummary,
    RunTriggerRequest,
)
from pulse.api.services.run_executor import get_run_executor
from pulse.config import iso_week_range, load_config, normalize_iso_week
from pulse.ledger.store import LedgerStore

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("")
def trigger_run(body: RunTriggerRequest) -> dict:
    config = load_config(include_mcp=not body.dry_run)
    try:
        config.get_product(body.product)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = get_run_executor().start_run(
        product_id=body.product,
        week=body.week,
        force=body.force,
        force_delivery=body.force_delivery,
        mock_llm=body.mock_llm,
        dry_run=body.dry_run,
    )
    return {"job_id": job_id, "status": "started"}


@router.post("/backfill")
def trigger_backfill(body: BackfillRequest) -> BackfillTriggerResponse:
    config = load_config(include_mcp=True)
    try:
        config.get_product(body.product)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        normalize_iso_week(body.from_week)
        normalize_iso_week(body.to_week)
        weeks = iso_week_range(normalize_iso_week(body.from_week), normalize_iso_week(body.to_week))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id, _ = get_run_executor().start_backfill(
        product_id=body.product,
        from_week=body.from_week,
        to_week=body.to_week,
        force=body.force,
        force_delivery=body.force_delivery,
        mock_llm=body.mock_llm,
        stop_on_error=body.stop_on_error,
    )
    return BackfillTriggerResponse(job_id=job_id, weeks=weeks)


@router.get("")
def list_runs(product: str = Query(default="groww"), limit: int = Query(default=20, ge=1, le=100)):
    ledger = LedgerStore()
    runs = ledger.list_runs(product_id=product, limit=limit)
    return RunListResponse(
        runs=[
            RunSummary(
                run_id=r.run_id,
                product_id=r.product_id,
                iso_week=r.iso_week,
                status=r.status,
                review_count=r.review_count,
                doc_document_id=r.doc_document_id,
                gmail_draft_count=len(r.gmail_drafts),
                started_at=r.started_at,
                completed_at=r.completed_at,
                error=r.error,
            )
            for r in runs
        ]
    )


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> RunDetailResponse:
    executor = get_run_executor()
    backfill = executor.get_backfill_job(job_id)
    if backfill is not None:
        return _backfill_detail(backfill, executor)

    state = executor.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")

    executor.sync_from_ledger(state)
    ledger_run_id = state.ledger_run_id
    review_count = None
    started_at = state.started_at
    completed_at = state.completed_at
    if ledger_run_id:
        run = LedgerStore().get_run_by_id(ledger_run_id)
        if run:
            review_count = run.review_count
            started_at = run.started_at
            completed_at = run.completed_at

    return RunDetailResponse(
        run_id=ledger_run_id or job_id,
        product_id=state.product_id,
        iso_week=state.iso_week,
        status=state.status,
        review_count=review_count,
        started_at=started_at,
        completed_at=completed_at,
        error=state.error,
        job_type="run",
        pipeline_steps=executor.pipeline_steps(job_id),
    )


def _backfill_detail(backfill, executor) -> RunDetailResponse:
    iso_week = backfill.current_week or (
        backfill.weeks[-1] if backfill.weeks else ""
    )
    review_count = None
    if backfill.current_week:
        run = LedgerStore().get_latest_run(backfill.product_id, backfill.current_week)
        if run:
            review_count = run.review_count

    return RunDetailResponse(
        run_id=backfill.job_id,
        product_id=backfill.product_id,
        iso_week=iso_week,
        status=backfill.status,
        review_count=review_count,
        started_at=backfill.started_at,
        completed_at=backfill.completed_at,
        error=backfill.error,
        job_type="backfill",
        pipeline_steps=executor.pipeline_steps(backfill.job_id),
        backfill_weeks=backfill.weeks,
        backfill_current_week=backfill.current_week,
        backfill_completed=list(backfill.completed_weeks),
        backfill_skipped=list(backfill.skipped_weeks),
        backfill_failed=dict(backfill.failed_weeks),
    )
