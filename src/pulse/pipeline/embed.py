"""Review embeddings — local BGE-small (default) or TF-IDF for fast tests."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from pulse.config import EmbeddingsConfig, get_project_root
from pulse.pipeline.models import ScrubbedReview


class Embedder(ABC):
    @abstractmethod
    def embed(self, reviews: list[ScrubbedReview]) -> np.ndarray:
        """Return embedding matrix of shape (n_reviews, n_dims)."""


class TfidfEmbedder(Embedder):
    """Lightweight embedder for unit tests and quick local runs."""

    def __init__(self, n_components: int = 64) -> None:
        self._n_components = n_components

    def embed(self, reviews: list[ScrubbedReview]) -> np.ndarray:
        texts = [r.body for r in reviews]
        if not texts:
            return np.empty((0, self._n_components))
        n_features = min(512, max(2, len(texts)))
        vectorizer = TfidfVectorizer(max_features=n_features, stop_words="english")
        matrix = vectorizer.fit_transform(texts)
        n_comp = min(self._n_components, matrix.shape[1], max(1, matrix.shape[0] - 1))
        if n_comp < matrix.shape[1]:
            svd = TruncatedSVD(n_components=n_comp, random_state=42)
            return svd.fit_transform(matrix)
        return matrix.toarray()


class BgeEmbedder(Embedder):
    """Local BGE embeddings via sentence-transformers (no paid API)."""

    _model_cache: ClassVar[dict[str, Any]] = {}

    def __init__(self, model_name: str, batch_size: int) -> None:
        self._model_name = model_name
        self._batch_size = batch_size

    def _get_model(self) -> Any:
        if self._model_name not in BgeEmbedder._model_cache:
            from sentence_transformers import SentenceTransformer

            BgeEmbedder._model_cache[self._model_name] = SentenceTransformer(self._model_name)
        return BgeEmbedder._model_cache[self._model_name]

    def embed(self, reviews: list[ScrubbedReview]) -> np.ndarray:
        texts = [r.body for r in reviews]
        if not texts:
            return np.empty((0, 384))
        model = self._get_model()
        vectors = model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(vectors, dtype=np.float64)


def _content_hash(reviews: list[ScrubbedReview]) -> str:
    payload = [(r.review_id, r.body) for r in reviews]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def embeddings_cache_path(iso_week: str, product_id: str) -> Path:
    root = get_project_root() / "data" / "embeddings" / iso_week
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{product_id}.npz"


def load_cached_embeddings(
    path: Path,
    reviews: list[ScrubbedReview],
    *,
    model: str,
) -> np.ndarray | None:
    if not path.exists():
        return None
    data = np.load(path, allow_pickle=True)
    if str(data.get("content_hash", "")) != _content_hash(reviews):
        return None
    if str(data.get("model", "")) != model:
        return None
    ids: list[str] = list(data["review_ids"])
    matrix = data["embeddings"]
    index = {rid: i for i, rid in enumerate(ids)}
    try:
        return np.array([matrix[index[r.review_id]] for r in reviews], dtype=np.float64)
    except KeyError:
        return None


def save_cached_embeddings(
    path: Path,
    reviews: list[ScrubbedReview],
    embeddings: np.ndarray,
    *,
    model: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        review_ids=np.array([r.review_id for r in reviews]),
        embeddings=embeddings,
        content_hash=_content_hash(reviews),
        model=model,
    )


def build_embedder(config: EmbeddingsConfig) -> Embedder:
    if config.provider == "bge":
        return BgeEmbedder(model_name=config.model, batch_size=config.batch_size)
    return TfidfEmbedder()


def embed_reviews(
    reviews: list[ScrubbedReview],
    config: EmbeddingsConfig,
    *,
    iso_week: str | None = None,
    product_id: str | None = None,
    use_cache: bool = True,
) -> np.ndarray:
    """Embed scrubbed reviews with optional disk cache."""
    cache_path = None
    if use_cache and iso_week and product_id:
        cache_path = embeddings_cache_path(iso_week, product_id)
        cached = load_cached_embeddings(cache_path, reviews, model=config.model)
        if cached is not None:
            return cached

    embedder = build_embedder(config)
    matrix = embedder.embed(reviews)
    if cache_path is not None:
        save_cached_embeddings(cache_path, reviews, matrix, model=config.model)
    return matrix
