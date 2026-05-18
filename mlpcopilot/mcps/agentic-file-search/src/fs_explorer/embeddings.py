"""
Embedding provider for vector-based semantic search.

Wraps the Google GenAI embedding API for batch and single-query embedding
with configurable model, dimensions, and batch size.
"""

from __future__ import annotations

import os
from typing import Any

from google.genai import Client as GenAIClient


_DEFAULT_MODEL = "gemini-embedding-001"
_DEFAULT_DIM = 768
_DEFAULT_BATCH_SIZE = 50


class EmbeddingProvider:
    """Generate text embeddings via Google GenAI."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        batch_size: int | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("FS_EXPLORER_EMBEDDING_MODEL", _DEFAULT_MODEL)
        self.dim = dim or int(os.getenv("FS_EXPLORER_EMBEDDING_DIM", str(_DEFAULT_DIM)))
        self.batch_size = batch_size or int(
            os.getenv("FS_EXPLORER_EMBEDDING_BATCH_SIZE", str(_DEFAULT_BATCH_SIZE))
        )

        if client is not None:
            self._client = client
        else:
            resolved_key = api_key or os.getenv("GOOGLE_API_KEY")
            if resolved_key is None:
                raise ValueError(
                    "GOOGLE_API_KEY not found. "
                    "Provide api_key or set the environment variable."
                )
            self._client = GenAIClient(api_key=resolved_key)

    def embed_texts(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> list[list[float]]:
        """Embed a list of texts in batches.

        Returns a list of embedding vectors in the same order as *texts*.
        """
        all_embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            result = self._client.models.embed_content(
                model=self.model,
                contents=batch,
                config={
                    "task_type": task_type,
                    "output_dimensionality": self.dim,
                },
            )
            for emb in result.embeddings:
                all_embeddings.append(list(emb.values))
        return all_embeddings

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query text for retrieval."""
        result = self._client.models.embed_content(
            model=self.model,
            contents=[query],
            config={
                "task_type": "RETRIEVAL_QUERY",
                "output_dimensionality": self.dim,
            },
        )
        return list(result.embeddings[0].values)
