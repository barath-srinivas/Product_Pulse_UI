"""Unit tests for clustering."""

import json
from pathlib import Path

from pulse.config import ClusteringConfig
from pulse.ingest.models import Review
from pulse.pipeline.cluster import cluster_reviews
from pulse.pipeline.embed import TfidfEmbedder
from pulse.pipeline.scrub import scrub_reviews


def _load_fixture_reviews() -> list[Review]:
    path = Path(__file__).parent.parent / "fixtures" / "reasoning_reviews_sample.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Review.model_validate(item) for item in raw]


def test_cluster_produces_top_k_themes() -> None:
    reviews = _load_fixture_reviews()
    scrubbed = scrub_reviews(reviews)
    embedder = TfidfEmbedder(n_components=16)
    matrix = embedder.embed(scrubbed)
    config = ClusteringConfig(
        umap_n_components=5,
        umap_n_neighbors=10,
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        top_k_themes=3,
    )
    clusters, noise_ratio = cluster_reviews(scrubbed, matrix, config)
    assert 1 <= len(clusters) <= 3
    assert all(c.size >= 4 for c in clusters)
    assert 0.0 <= noise_ratio <= 1.0


def test_cluster_ranking_prefers_larger_clusters() -> None:
    reviews = _load_fixture_reviews()
    scrubbed = scrub_reviews(reviews)
    matrix = TfidfEmbedder(n_components=16).embed(scrubbed)
    config = ClusteringConfig(
        hdbscan_min_cluster_size=4,
        hdbscan_min_samples=2,
        top_k_themes=5,
    )
    clusters, _ = cluster_reviews(scrubbed, matrix, config)
    sizes = [c.size for c in clusters]
    assert sizes == sorted(sizes, reverse=True)
