"""Optional live Groq integration smoke test."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pulse.config import load_pulse_config
from pulse.pipeline.llm_budget import LlmBudgetTracker
from pulse.pipeline.models import ThemeCluster
from pulse.pipeline.summarize import GroqThemeSummarizer

pytestmark = pytest.mark.integration


def _live_groq_enabled() -> bool:
    return os.getenv("RUN_LIVE_GROQ") == "1" and bool(os.getenv("GROQ_API_KEY"))


@pytest.mark.skipif(not _live_groq_enabled(), reason="set RUN_LIVE_GROQ=1 and GROQ_API_KEY")
def test_groq_summarize_single_cluster(config_dir: Path) -> None:
    pulse = load_pulse_config(config_dir)
    cluster = ThemeCluster(
        cluster_id=0,
        review_ids=["live-1"],
        size=1,
        sample_texts=[
            "The app freezes exactly when the market opens and I cannot place orders."
        ],
    )
    budget = LlmBudgetTracker(config=pulse.llm)
    summarizer = GroqThemeSummarizer(pulse.llm, budget)
    response = summarizer.summarize_cluster(cluster)
    assert response.theme_name
    assert response.theme_summary
    assert budget.run_requests == 1
    assert budget.run_tokens > 0
