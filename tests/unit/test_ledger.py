"""Unit tests for SQLite run ledger."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pulse.ledger.models import GmailDraftRecord
from pulse.ledger.store import LedgerStore


@pytest.fixture
def ledger(tmp_path) -> LedgerStore:
    return LedgerStore(db_path=tmp_path / "ledger.db")


def test_create_and_fetch_run(ledger: LedgerStore) -> None:
    record = ledger.create_run(
        product_id="groww",
        iso_week="2026-W24",
        section_anchor="groww-2026-W24",
        email_mode="draft",
    )
    assert record.status == "pending"
    assert record.run_key == "groww:2026-W24"

    latest = ledger.get_latest_run("groww", "2026-W24")
    assert latest is not None
    assert latest.run_id == record.run_id


def test_update_run_persists_delivery_ids(ledger: LedgerStore) -> None:
    record = ledger.create_run(
        product_id="groww",
        iso_week="2026-W24",
        section_anchor="groww-2026-W24",
        email_mode="draft",
    )
    record.status = "delivering"
    record.review_count = 32
    record.doc_document_id = "doc-123"
    record.gmail_drafts = [
        GmailDraftRecord(
            to="a@example.com",
            draft_id="draft-1",
            message_id="msg-1",
        )
    ]
    record.gmail_draft_id = "draft-1"
    record.gmail_message_id = "msg-1"
    ledger.update_run(record)

    loaded = ledger.get_latest_run("groww", "2026-W24")
    assert loaded is not None
    assert loaded.doc_document_id == "doc-123"
    assert loaded.gmail_drafts[0].draft_id == "draft-1"


def test_completed_run_lookup(ledger: LedgerStore) -> None:
    record = ledger.create_run(
        product_id="groww",
        iso_week="2026-W24",
        section_anchor="groww-2026-W24",
        email_mode="draft",
    )
    record.status = "completed"
    record.completed_at = datetime.now(ZoneInfo("Asia/Kolkata"))
    ledger.update_run(record)

    assert ledger.get_completed_run("groww", "2026-W24") is not None
    assert ledger.get_completed_run("groww", "2026-W25") is None


def test_set_status_marks_completed_timestamp(ledger: LedgerStore) -> None:
    record = ledger.create_run(
        product_id="groww",
        iso_week="2026-W24",
        section_anchor="groww-2026-W24",
        email_mode="draft",
    )
    updated = ledger.set_status(record, "completed")
    assert updated.status == "completed"
    assert updated.completed_at is not None
