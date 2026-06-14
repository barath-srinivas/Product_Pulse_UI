"""API tests for backfill endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pulse.api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_backfill_rejects_invalid_week(client: TestClient) -> None:
    response = client.post(
        "/api/runs/backfill",
        json={
            "product": "groww",
            "from_week": "2026-W24",
            "to_week": "2026-W20",
        },
    )
    assert response.status_code == 400


def test_backfill_starts_job(client: TestClient) -> None:
    with patch("pulse.api.routes.runs.get_run_executor") as get_executor:
        executor = MagicMock()
        executor.start_backfill.return_value = ("job-123", ["2026-W20", "2026-W21"])
        get_executor.return_value = executor

        response = client.post(
            "/api/runs/backfill",
            json={
                "product": "groww",
                "from_week": "2026-W20",
                "to_week": "2026-W21",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-123"
    assert payload["weeks"] == ["2026-W20", "2026-W21"]
    executor.start_backfill.assert_called_once()
