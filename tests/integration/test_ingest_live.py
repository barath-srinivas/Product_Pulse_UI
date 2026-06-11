"""Live Google Play ingestion tests (optional, requires network)."""

from __future__ import annotations

import os

import pytest

from pulse.config import current_iso_week, load_config
from pulse.ingest.play_store import ingest_groww_reviews


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_INGEST") != "1",
    reason="Set RUN_LIVE_INGEST=1 to run live Groww Play Store fetch",
)
def test_live_groww_ingest_meets_minimum() -> None:
    config = load_config(include_mcp=False)
    iso_week = current_iso_week(config.pulse.timezone)
    result = ingest_groww_reviews(iso_week=iso_week, config=config)
    assert result.product_id == "groww"
    assert result.package == "com.nextbillion.groww"
    assert result.review_count >= config.pulse.min_reviews_required
