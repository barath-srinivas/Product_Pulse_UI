"""Background pulse run and backfill execution for the operator UI."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from pulse.api.schemas import PipelineStep, PipelineStepStatus
from pulse.config import current_iso_week, iso_week_range, load_config, normalize_iso_week
from pulse.ledger.store import LedgerStore

PIPELINE_STEP_DEFS: list[tuple[str, str]] = [
    ("reviews_retrieved", "Reviews Retrieved"),
    ("reviews_clustered", "Reviews Clustered"),
    ("themes_generated", "Themes Generated"),
    ("quotes_validated", "Quotes Validated"),
    ("report_created", "Report Created"),
    ("email_delivered", "Email Delivered"),
]


@dataclass
class ActiveRunState:
    job_id: str
    product_id: str
    iso_week: str
    ledger_run_id: str | None = None
    status: str = "pending"
    error: str | None = None
    dry_run: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("UTC")))
    completed_at: datetime | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs: object) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)


@dataclass
class ActiveBackfillState:
    job_id: str
    product_id: str
    weeks: list[str]
    force: bool
    force_delivery: bool
    mock_llm: bool
    stop_on_error: bool
    current_week: str | None = None
    completed_weeks: list[str] = field(default_factory=list)
    skipped_weeks: list[str] = field(default_factory=list)
    failed_weeks: dict[str, str] = field(default_factory=dict)
    status: str = "pending"
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("UTC")))
    completed_at: datetime | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs: object) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)


class RunExecutor:
    """Runs pulse jobs in background threads."""

    def __init__(self) -> None:
        self._jobs: dict[str, ActiveRunState] = {}
        self._backfill_jobs: dict[str, ActiveBackfillState] = {}
        self._lock = threading.Lock()

    def start_run(
        self,
        *,
        product_id: str,
        week: str | None,
        force: bool,
        force_delivery: bool,
        mock_llm: bool,
        dry_run: bool,
    ) -> str:
        config = load_config(include_mcp=not dry_run)
        iso_week = normalize_iso_week(week) if week else current_iso_week(config.pulse.timezone)
        job_id = str(uuid.uuid4())
        state = ActiveRunState(
            job_id=job_id,
            product_id=product_id,
            iso_week=iso_week,
            dry_run=dry_run,
        )
        with self._lock:
            self._jobs[job_id] = state

        thread = threading.Thread(
            target=self._execute,
            args=(job_id, product_id, iso_week, force, force_delivery, mock_llm, dry_run),
            daemon=True,
        )
        thread.start()
        return job_id

    def start_backfill(
        self,
        *,
        product_id: str,
        from_week: str,
        to_week: str,
        force: bool,
        force_delivery: bool,
        mock_llm: bool,
        stop_on_error: bool,
    ) -> tuple[str, list[str]]:
        weeks = iso_week_range(normalize_iso_week(from_week), normalize_iso_week(to_week))
        job_id = str(uuid.uuid4())
        state = ActiveBackfillState(
            job_id=job_id,
            product_id=product_id,
            weeks=weeks,
            force=force,
            force_delivery=force_delivery,
            mock_llm=mock_llm,
            stop_on_error=stop_on_error,
        )
        with self._lock:
            self._backfill_jobs[job_id] = state

        thread = threading.Thread(
            target=self._execute_backfill,
            args=(job_id,),
            daemon=True,
        )
        thread.start()
        return job_id, weeks

    def get_job(self, job_id: str) -> ActiveRunState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_backfill_job(self, job_id: str) -> ActiveBackfillState | None:
        with self._lock:
            return self._backfill_jobs.get(job_id)

    def sync_from_ledger(self, state: ActiveRunState) -> None:
        ledger = LedgerStore()
        run = ledger.get_latest_run(state.product_id, state.iso_week)
        if run is None:
            return
        state.update(ledger_run_id=run.run_id, status=run.status, error=run.error)

    def pipeline_steps(self, job_id: str) -> list[PipelineStep]:
        state = self.get_job(job_id)
        if state is None:
            backfill = self.get_backfill_job(job_id)
            if backfill is None or backfill.current_week is None:
                return []
            run_state = ActiveRunState(
                job_id=job_id,
                product_id=backfill.product_id,
                iso_week=backfill.current_week,
            )
            self.sync_from_ledger(run_state)
            return self._pipeline_steps_for_run(run_state)

        self.sync_from_ledger(state)
        return self._pipeline_steps_for_run(state)

    def _pipeline_steps_for_run(self, state: ActiveRunState) -> list[PipelineStep]:
        status = state.status
        error = state.error

        if state.dry_run and status == "completed":
            active_idx = 4
        else:
            active_idx = _status_to_step_index(status)

        steps: list[PipelineStep] = []
        for idx, (step_id, label) in enumerate(PIPELINE_STEP_DEFS):
            if state.dry_run and step_id == "email_delivered":
                step_status: PipelineStepStatus = "pending"
            elif status == "failed" and idx == active_idx:
                step_status = "failed"
            elif idx < active_idx or status == "completed":
                step_status = "completed"
            elif idx == active_idx and status not in {"completed", "failed"}:
                step_status = "active"
            else:
                step_status = "pending"
            steps.append(PipelineStep(id=step_id, label=label, status=step_status))
        if error and status == "failed":
            steps[min(active_idx, len(steps) - 1)].status = "failed"
        return steps

    def _execute(
        self,
        job_id: str,
        product_id: str,
        iso_week: str,
        force: bool,
        force_delivery: bool,
        mock_llm: bool,
        dry_run: bool,
    ) -> None:
        state = self.get_job(job_id)
        if state is None:
            return

        config = load_config(include_mcp=not dry_run)
        from pulse.orchestrator import OrchestratorError, PulseOrchestrator

        orchestrator = PulseOrchestrator(config)
        state.update(status="ingesting")

        try:
            result = orchestrator.run(
                product_id,
                iso_week=iso_week,
                force=force,
                force_delivery=force_delivery,
                mock_llm=mock_llm,
                dry_run=dry_run,
            )
            if result.run:
                state.update(
                    ledger_run_id=result.run.run_id,
                    status=result.run.status,
                    completed_at=datetime.now(ZoneInfo("UTC")),
                )
            else:
                state.update(status="completed", completed_at=datetime.now(ZoneInfo("UTC")))
        except OrchestratorError as exc:
            self.sync_from_ledger(state)
            state.update(
                status="failed",
                error=str(exc),
                completed_at=datetime.now(ZoneInfo("UTC")),
            )
        except Exception as exc:  # noqa: BLE001
            self.sync_from_ledger(state)
            state.update(
                status="failed",
                error=str(exc),
                completed_at=datetime.now(ZoneInfo("UTC")),
            )

    def _execute_backfill(self, job_id: str) -> None:
        state = self.get_backfill_job(job_id)
        if state is None:
            return

        from pulse.orchestrator import OrchestratorError, PulseOrchestrator

        config = load_config(include_mcp=True)
        orchestrator = PulseOrchestrator(config)
        state.update(status="running")

        for week in state.weeks:
            state.update(current_week=week, error=None)
            try:
                result = orchestrator.run(
                    state.product_id,
                    iso_week=week,
                    force=state.force,
                    force_delivery=state.force_delivery,
                    mock_llm=state.mock_llm,
                )
            except OrchestratorError as exc:
                state.failed_weeks[week] = str(exc)
                state.update(
                    status="failed",
                    error=f"{week}: {exc}",
                    completed_at=datetime.now(ZoneInfo("UTC")),
                )
                if state.stop_on_error:
                    return
                continue
            except Exception as exc:  # noqa: BLE001
                state.failed_weeks[week] = str(exc)
                state.update(
                    status="failed",
                    error=f"{week}: {exc}",
                    completed_at=datetime.now(ZoneInfo("UTC")),
                )
                if state.stop_on_error:
                    return
                continue

            if result.skipped:
                state.skipped_weeks.append(week)
            else:
                state.completed_weeks.append(week)

        state.update(
            current_week=None,
            status="completed" if not state.failed_weeks else "failed",
            completed_at=datetime.now(ZoneInfo("UTC")),
        )
        if state.failed_weeks and state.completed_weeks:
            state.update(error=f"{len(state.failed_weeks)} week(s) failed")


def _status_to_step_index(status: str) -> int:
    mapping = {
        "pending": 0,
        "ingesting": 1,
        "reasoning": 3,
        "delivering": 5,
        "completed": 6,
        "failed": 0,
    }
    return mapping.get(status, 0)


_executor = RunExecutor()


def get_run_executor() -> RunExecutor:
    return _executor
