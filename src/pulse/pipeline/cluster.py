"""UMAP + HDBSCAN clustering and theme ranking."""

from __future__ import annotations

import logging

import hdbscan
import numpy as np
import umap

from pulse.config import ClusteringConfig
from pulse.pipeline.exceptions import ClusteringError
from pulse.pipeline.models import ScrubbedReview, ThemeCluster

logger = logging.getLogger(__name__)

MAX_SAMPLES_PER_CLUSTER = 20


def _mean_rating_extremity(ratings: list[int | None]) -> float:
    values = [r for r in ratings if r is not None]
    if not values:
        return 0.0
    return sum(abs(r - 3) for r in values) / len(values)


def cluster_reviews(
    reviews: list[ScrubbedReview],
    embeddings: np.ndarray,
    config: ClusteringConfig,
) -> tuple[list[ThemeCluster], float]:
    """Cluster embeddings and return ranked theme clusters plus noise ratio."""
    n = len(reviews)
    if n == 0:
        raise ClusteringError("cannot cluster empty review set")
    if n < config.hdbscan_min_cluster_size:
        raise ClusteringError(
            f"review count {n} below hdbscan_min_cluster_size {config.hdbscan_min_cluster_size}"
        )

    n_neighbors = min(config.umap_n_neighbors, max(2, n - 1))
    n_components = min(config.umap_n_components, max(1, n - 2))

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        random_state=config.umap_random_state,
        metric="cosine",
    )
    reduced = reducer.fit_transform(embeddings)

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=config.hdbscan_min_cluster_size,
        min_samples=min(config.hdbscan_min_samples, config.hdbscan_min_cluster_size - 1),
        metric="euclidean",
    )
    labels = clusterer.fit_predict(reduced)

    noise_count = int(np.sum(labels == -1))
    noise_ratio = noise_count / n

    clusters: list[ThemeCluster] = []
    for cluster_id in sorted({int(label) for label in labels if label != -1}):
        indices = [i for i, label in enumerate(labels) if label == cluster_id]
        cluster_reviews_list = [reviews[i] for i in indices]
        samples = cluster_reviews_list[:MAX_SAMPLES_PER_CLUSTER]
        ratings = [r.rating for r in cluster_reviews_list]
        clusters.append(
            ThemeCluster(
                cluster_id=cluster_id,
                review_ids=[r.review_id for r in cluster_reviews_list],
                size=len(cluster_reviews_list),
                sample_texts=[r.body for r in samples],
                mean_rating=_mean_rating_extremity(ratings),
            )
        )

    clusters.sort(key=lambda c: (c.size, c.mean_rating or 0.0), reverse=True)
    top = clusters[: config.top_k_themes]

    if not top and noise_count > 0:
        logger.warning("all reviews labeled noise; using corpus-wide fallback cluster")
        top = [
            ThemeCluster(
                cluster_id=0,
                review_ids=[r.review_id for r in reviews[:MAX_SAMPLES_PER_CLUSTER * 2]],
                size=n,
                sample_texts=[r.body for r in reviews[:MAX_SAMPLES_PER_CLUSTER]],
                mean_rating=_mean_rating_extremity([r.rating for r in reviews]),
            )
        ]

    if not top:
        raise ClusteringError("no clusters produced")

    return top, noise_ratio
