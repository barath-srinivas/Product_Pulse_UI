"""Unit tests for review embeddings."""

from datetime import date
from unittest.mock import MagicMock, patch

import numpy as np

from pulse.config import EmbeddingsConfig
from pulse.pipeline.embed import BgeEmbedder, TfidfEmbedder, build_embedder
from pulse.pipeline.models import ScrubbedReview


def _scrubbed(review_id: str, body: str) -> ScrubbedReview:
    return ScrubbedReview(
        review_id=review_id,
        product_id="groww",
        rating=3,
        body=body,
        review_date=date(2026, 5, 1),
    )


def test_build_embedder_bge() -> None:
    config = EmbeddingsConfig(provider="bge", model="BAAI/bge-small-en-v1.5")
    embedder = build_embedder(config)
    assert isinstance(embedder, BgeEmbedder)


def test_build_embedder_tfidf() -> None:
    embedder = build_embedder(EmbeddingsConfig(provider="tfidf"))
    assert isinstance(embedder, TfidfEmbedder)


def test_bge_embedder_calls_sentence_transformer() -> None:
    reviews = [
        _scrubbed("r1", "App crashes during market open every morning without fail"),
        _scrubbed("r2", "Customer support never responds to my withdrawal requests"),
    ]
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        BgeEmbedder._model_cache.clear()
        matrix = BgeEmbedder("BAAI/bge-small-en-v1.5", batch_size=64).embed(reviews)

    assert matrix.shape == (2, 2)
    mock_model.encode.assert_called_once()
