"""Golden-path reasoning pipeline tests with mock Groq."""

import json
from pathlib import Path

import pytest

from pulse.config import PulseConfig
from pulse.ingest.models import Review
from pulse.pipeline.exceptions import LlmBudgetExceededError
from pulse.pipeline.reasoning import run_reasoning_pipeline


def _fixture_reviews() -> list[Review]:
    path = Path(__file__).parent.parent / "fixtures" / "reasoning_reviews_sample.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Review.model_validate(item) for item in raw]


def test_reasoning_pipeline_mock_groq(pulse_config_fast: PulseConfig) -> None:
    result = run_reasoning_pipeline(
        _fixture_reviews(),
        product_id="groww",
        iso_week="2026-W24",
        config=pulse_config_fast,
        mock_llm=True,
    )
    report = result.report
    assert report.llm_provider == "groq"
    assert report.llm_model == "llama-3.3-70b-versatile"
    assert 1 <= len(report.themes) <= pulse_config_fast.clustering.top_k_themes
    assert report.review_count == 32
    for theme in report.themes:
        assert theme.quotes
        for quote in theme.quotes:
            assert quote.review_id
            assert quote.text
    assert result.llm_requests > 0
    assert result.llm_tokens_used > 0


def test_reasoning_enforces_token_cap(pulse_config_fast: PulseConfig) -> None:
    pulse_config_fast.llm.max_tokens_per_run = 100
    with pytest.raises(LlmBudgetExceededError):
        run_reasoning_pipeline(
            _fixture_reviews(),
            product_id="groww",
            iso_week="2026-W24",
            config=pulse_config_fast,
            mock_llm=True,
        )


def test_reasoning_report_snapshot(pulse_config_fast: PulseConfig) -> None:
    """Golden path: fixture reviews → stable PulseReport shape (mocked Groq)."""
    result = run_reasoning_pipeline(
        _fixture_reviews(),
        product_id="groww",
        iso_week="2026-W24",
        config=pulse_config_fast,
        mock_llm=True,
    )
    snapshot_path = Path(__file__).parent.parent / "fixtures" / "report_groww_sample.json"
    expected = json.loads(snapshot_path.read_text(encoding="utf-8"))

    actual = json.loads(result.report.model_dump_json())
    actual["generated_at"] = expected["generated_at"]

    assert actual["product_id"] == expected["product_id"]
    assert actual["iso_week"] == expected["iso_week"]
    assert actual["review_count"] == expected["review_count"]
    assert actual["llm_provider"] == expected["llm_provider"]
    assert actual["llm_model"] == expected["llm_model"]
    assert len(actual["themes"]) == len(expected["themes"])
    for act_theme, exp_theme in zip(actual["themes"], expected["themes"], strict=True):
        assert act_theme["cluster_id"] == exp_theme["cluster_id"]
        assert act_theme["rank"] == exp_theme["rank"]
        assert act_theme["quotes"][0]["review_id"] == exp_theme["quotes"][0]["review_id"]
        assert act_theme["quotes"][0]["text"] == exp_theme["quotes"][0]["text"]
