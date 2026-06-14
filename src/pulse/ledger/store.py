"""SQLite-backed run ledger for idempotency and audit."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pulse.config import DEFAULT_TIMEZONE, get_project_root
from pulse.ledger.models import GmailDraftRecord, RunRecord, RunStatus

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    iso_week TEXT NOT NULL,
    status TEXT NOT NULL,
    review_count INTEGER,
    section_anchor TEXT NOT NULL,
    doc_document_id TEXT,
    doc_revision_id TEXT,
    gmail_message_id TEXT,
    gmail_draft_id TEXT,
    gmail_drafts_json TEXT,
    email_mode TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_product_week ON runs(product_id, iso_week);
"""


def get_runs_dir() -> Path:
    path = get_project_root() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_ledger_path() -> Path:
    return get_runs_dir() / "ledger.db"


def run_artifact_dir(product_id: str, iso_week: str) -> Path:
    path = get_runs_dir() / product_id / iso_week
    path.mkdir(parents=True, exist_ok=True)
    return path


def report_artifact_path(product_id: str, iso_week: str) -> Path:
    return run_artifact_dir(product_id, iso_week) / "report.json"


class LedgerStore:
    """Persistent store for pulse run state."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_ledger_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def get_latest_run(self, product_id: str, iso_week: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE product_id = ? AND iso_week = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (product_id, iso_week),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_completed_run(self, product_id: str, iso_week: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE product_id = ? AND iso_week = ? AND status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """,
                (product_id, iso_week),
            ).fetchone()
        return _row_to_record(row) if row else None

    def get_run_by_id(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return _row_to_record(row) if row else None

    def list_runs(
        self,
        *,
        product_id: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        with self._connect() as conn:
            if product_id:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE product_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (product_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    ORDER BY started_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_record(row) for row in rows]

    def list_completed_weeks(self, product_id: str, *, limit: int = 52) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT iso_week FROM runs
                WHERE product_id = ? AND status = 'completed'
                ORDER BY iso_week DESC
                LIMIT ?
                """,
                (product_id, limit),
            ).fetchall()
        return [row["iso_week"] for row in rows]

    def create_run(
        self,
        *,
        product_id: str,
        iso_week: str,
        section_anchor: str,
        email_mode: str,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> RunRecord:
        now = datetime.now(ZoneInfo(timezone))
        record = RunRecord(
            run_id=str(uuid.uuid4()),
            product_id=product_id,
            iso_week=iso_week,
            status="pending",
            section_anchor=section_anchor,
            email_mode=email_mode,  # type: ignore[arg-type]
            started_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, product_id, iso_week, status, review_count,
                    section_anchor, doc_document_id, doc_revision_id,
                    gmail_message_id, gmail_draft_id, gmail_drafts_json,
                    email_mode, started_at, completed_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _record_to_row(record),
            )
        return record

    def update_run(self, record: RunRecord) -> RunRecord:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    review_count = ?,
                    section_anchor = ?,
                    doc_document_id = ?,
                    doc_revision_id = ?,
                    gmail_message_id = ?,
                    gmail_draft_id = ?,
                    gmail_drafts_json = ?,
                    email_mode = ?,
                    started_at = ?,
                    completed_at = ?,
                    error = ?
                WHERE run_id = ?
                """,
                (
                    record.status,
                    record.review_count,
                    record.section_anchor,
                    record.doc_document_id,
                    record.doc_revision_id,
                    record.gmail_message_id,
                    record.gmail_draft_id,
                    _drafts_to_json(record.gmail_drafts),
                    record.email_mode,
                    _dt_to_str(record.started_at),
                    _dt_to_str(record.completed_at),
                    record.error,
                    record.run_id,
                ),
            )
        return record

    def set_status(
        self,
        record: RunRecord,
        status: RunStatus,
        *,
        error: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> RunRecord:
        record.status = status
        record.error = error
        if status == "completed":
            record.completed_at = datetime.now(ZoneInfo(timezone))
        return self.update_run(record)


def _drafts_to_json(drafts: list[GmailDraftRecord]) -> str | None:
    if not drafts:
        return None
    return json.dumps([draft.model_dump() for draft in drafts])


def _drafts_from_json(raw: str | None) -> list[GmailDraftRecord]:
    if not raw:
        return []
    data = json.loads(raw)
    return [GmailDraftRecord.model_validate(item) for item in data]


def _dt_to_str(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt_from_str(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    drafts = _drafts_from_json(row["gmail_drafts_json"])
    return RunRecord(
        run_id=row["run_id"],
        product_id=row["product_id"],
        iso_week=row["iso_week"],
        status=row["status"],  # type: ignore[arg-type]
        review_count=row["review_count"],
        section_anchor=row["section_anchor"],
        doc_document_id=row["doc_document_id"],
        doc_revision_id=row["doc_revision_id"],
        gmail_message_id=row["gmail_message_id"],
        gmail_draft_id=row["gmail_draft_id"],
        gmail_drafts=drafts,
        email_mode=row["email_mode"],  # type: ignore[arg-type]
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=_dt_from_str(row["completed_at"]),
        error=row["error"],
    )


def _record_to_row(record: RunRecord) -> tuple:
    return (
        record.run_id,
        record.product_id,
        record.iso_week,
        record.status,
        record.review_count,
        record.section_anchor,
        record.doc_document_id,
        record.doc_revision_id,
        record.gmail_message_id,
        record.gmail_draft_id,
        _drafts_to_json(record.gmail_drafts),
        record.email_mode,
        _dt_to_str(record.started_at),
        _dt_to_str(record.completed_at),
        record.error,
    )
