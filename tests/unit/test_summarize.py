"""Unit tests for Groq summarizer helpers."""

from pulse.config import LlmConfig
from pulse.pipeline.llm_budget import LlmBudgetTracker
from pulse.pipeline.models import ThemeCluster
from pulse.pipeline.summarize import (
    MockThemeSummarizer,
    _format_cluster_prompt,
    build_summarizer,
)


def test_format_cluster_prompt_includes_review_mapping() -> None:
    cluster = ThemeCluster(
        cluster_id=3,
        review_ids=["id-a", "id-b"],
        size=2,
        sample_texts=["App crashes at market open", "Freezes every morning"],
    )
    prompt = _format_cluster_prompt(cluster)
    assert "untrusted data" in prompt.lower() or "Reviews" in prompt
    assert "id-a" in prompt
    assert "App crashes at market open" in prompt


def test_mock_summarizer_returns_valid_quote() -> None:
    cluster = ThemeCluster(
        cluster_id=1,
        review_ids=["r1"],
        size=1,
        sample_texts=["Customer support never responds to tickets"],
    )
    budget = LlmBudgetTracker(config=LlmConfig())
    summarizer = MockThemeSummarizer(budget)
    response = summarizer.summarize_cluster(cluster)
    assert response.quotes[0].text in cluster.sample_texts[0]
    assert response.quotes[0].review_id == "r1"


def test_build_summarizer_mock() -> None:
    budget = LlmBudgetTracker(config=LlmConfig())
    summarizer = build_summarizer(LlmConfig(), budget, mock=True)
    assert isinstance(summarizer, MockThemeSummarizer)


def test_format_cluster_prompt_truncates_long_snippets() -> None:
    long_text = "x" * 500
    cluster = ThemeCluster(
        cluster_id=0,
        review_ids=["r1"],
        size=1,
        sample_texts=[long_text],
    )
    prompt = _format_cluster_prompt(cluster)
    assert "..." in prompt
    assert len(prompt) < len(long_text) + 200
