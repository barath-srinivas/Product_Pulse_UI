"""Operator run trigger and status endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from pulse.api.schemas import RunDetailResponse, RunListResponse, RunSummary, RunTriggerRequest
from pulse.api.services.run_executor import get_run_executor
from pulse.config import load_config
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
    state = executor.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")

    executor.sync_from_ledger(state)
    ledger_run_id = state.ledger_run_id
    review_count = None
    started_at = None
    completed_at = None
    if ledger_run_id:
        run = LedgerStore().get_run_by_id(ledger_run_id)
        if run:
            review_count = run.review_count
            started_at = run.started_at
            completed_at = run.completed_at

    from datetime import datetime
    from zoneinfo import ZoneInfo

    return RunDetailResponse(
        run_id=ledger_run_id or job_id,
        product_id=state.product_id,
        iso_week=state.iso_week,
        status=state.status,
        review_count=review_count,
        started_at=started_at or datetime.now(ZoneInfo("UTC")),
        completed_at=completed_at,
        error=state.error,
        pipeline_steps=executor.pipeline_steps(job_id),
    )
