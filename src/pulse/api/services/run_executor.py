"""Background pulse run execution for the operator UI."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field

from pulse.api.schemas import PipelineStep, PipelineStepStatus
from pulse.config import current_iso_week, load_config, normalize_iso_week
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
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, **kwargs: object) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self, key, value)


class RunExecutor:
    """Runs pulse jobs in background threads."""

    def __init__(self) -> None:
        self._jobs: dict[str, ActiveRunState] = {}
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

    def get_job(self, job_id: str) -> ActiveRunState | None:
        with self._lock:
            return self._jobs.get(job_id)

    def sync_from_ledger(self, state: ActiveRunState) -> None:
        ledger = LedgerStore()
        run = ledger.get_latest_run(state.product_id, state.iso_week)
        if run is None:
            return
        state.update(ledger_run_id=run.run_id, status=run.status, error=run.error)

    def pipeline_steps(self, job_id: str) -> list[PipelineStep]:
        state = self.get_job(job_id)
        if state is None:
            return []

        self.sync_from_ledger(state)
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
                )
            else:
                state.update(status="completed")
        except OrchestratorError as exc:
            self.sync_from_ledger(state)
            state.update(status="failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            self.sync_from_ledger(state)
            state.update(status="failed", error=str(exc))


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
