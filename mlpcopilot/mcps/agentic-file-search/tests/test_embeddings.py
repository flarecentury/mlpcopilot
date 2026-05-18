"""Tests for the embedding provider."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import pytest

from fs_explorer.embeddings import EmbeddingProvider


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeEmbedding:
    values: list[float]


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding]


class _FakeModels:
    """Records calls and returns deterministic embeddings."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def embed_content(
        self, *, model: str, contents: list[str], config: dict
    ) -> _FakeEmbedResult:
        self.calls.append({"model": model, "contents": contents, "config": config})
        dim = config.get("output_dimensionality", 768)
        return _FakeEmbedResult(
            embeddings=[
                _FakeEmbedding(values=[float(i)] * dim) for i in range(len(contents))
            ]
        )


class _FakeClient:
    def __init__(self) -> None:
        self.models = _FakeModels()


# ---------------------------------------------------------------------------
# Unit tests (mock-based, no API key needed)
# ---------------------------------------------------------------------------


def test_embed_texts_returns_correct_count() -> None:
    client = _FakeClient()
    provider = EmbeddingProvider(client=client, dim=4, batch_size=50)

    embeddings = provider.embed_texts(["hello", "world"])

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 4


def test_embed_texts_uses_document_task_type() -> None:
    client = _FakeClient()
    provider = EmbeddingProvider(client=client, dim=4)

    provider.embed_texts(["test"])

    call = client.models.calls[0]
    assert call["config"]["task_type"] == "RETRIEVAL_DOCUMENT"


def test_embed_query_uses_query_task_type() -> None:
    client = _FakeClient()
    provider = EmbeddingProvider(client=client, dim=4)

    result = provider.embed_query("search query")

    assert len(result) == 4
    call = client.models.calls[0]
    assert call["config"]["task_type"] == "RETRIEVAL_QUERY"


def test_embed_texts_batching() -> None:
    client = _FakeClient()
    provider = EmbeddingProvider(client=client, dim=4, batch_size=3)

    texts = [f"text_{i}" for i in range(7)]
    embeddings = provider.embed_texts(texts)

    assert len(embeddings) == 7
    # 7 texts with batch_size=3 → 3 API calls (3+3+1)
    assert len(client.models.calls) == 3
    assert len(client.models.calls[0]["contents"]) == 3
    assert len(client.models.calls[1]["contents"]) == 3
    assert len(client.models.calls[2]["contents"]) == 1


def test_env_overrides(monkeypatch) -> None:
    client = _FakeClient()
    monkeypatch.setenv("FS_EXPLORER_EMBEDDING_MODEL", "custom-model-001")
    monkeypatch.setenv("FS_EXPLORER_EMBEDDING_DIM", "256")
    monkeypatch.setenv("FS_EXPLORER_EMBEDDING_BATCH_SIZE", "10")

    provider = EmbeddingProvider(client=client)

    assert provider.model == "custom-model-001"
    assert provider.dim == 256
    assert provider.batch_size == 10

    provider.embed_texts(["test"])
    call = client.models.calls[0]
    assert call["model"] == "custom-model-001"
    assert call["config"]["output_dimensionality"] == 256


def test_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
        EmbeddingProvider(api_key=None, client=None)


# ---------------------------------------------------------------------------
# Real API integration test (skipped unless GOOGLE_API_KEY is set)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY"),
    reason="GOOGLE_API_KEY not set — skipping real embedding test",
)
def test_real_embedding_api() -> None:
    provider = EmbeddingProvider(dim=128)

    texts = ["The purchase price is $45 million.", "Risk assessment summary."]
    embeddings = provider.embed_texts(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == 128
    assert all(isinstance(v, float) for v in embeddings[0])

    query_emb = provider.embed_query("purchase price")
    assert len(query_emb) == 128
