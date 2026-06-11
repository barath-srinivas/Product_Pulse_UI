"""Unit tests for Groq LLM budget tracking."""

import pytest

from pulse.config import LlmConfig
from pulse.pipeline.exceptions import LlmBudgetExceededError
from pulse.pipeline.llm_budget import LlmBudgetTracker


def test_preflight_rejects_over_run_cap(tmp_path) -> None:
    config = LlmConfig(max_tokens_per_run=1000)
    tracker = LlmBudgetTracker(config=config, usage_file=tmp_path / "usage.json")
    with pytest.raises(LlmBudgetExceededError, match="max_tokens_per_run"):
        tracker.preflight(1500)


def test_record_accumulates_run_tokens(tmp_path) -> None:
    config = LlmConfig(max_tokens_per_run=5000)
    tracker = LlmBudgetTracker(config=config, usage_file=tmp_path / "usage.json")
    tracker.preflight(500)
    tracker.record(500)
    tracker.preflight(500)
    tracker.record(500)
    assert tracker.run_tokens == 1000
    assert tracker.run_requests == 2


def test_daily_token_persistence(tmp_path) -> None:
    usage_file = tmp_path / "usage.json"
    config = LlmConfig()
    tracker = LlmBudgetTracker(config=config, usage_file=usage_file)
    tracker.record(100)
    tracker2 = LlmBudgetTracker(config=config, usage_file=usage_file)
    assert tracker2._load_daily_tokens() == 100
