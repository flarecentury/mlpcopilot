"""
Vector-based semantic search engine.

Embeds a query and searches chunk embeddings via cosine similarity,
falling back to keyword matching when embeddings are unavailable.
"""

from __future__ import annotations

from typing import Any

from ..embeddings import EmbeddingProvider
from ..storage import StorageBackend


class SemanticSearchEngine:
    """Embed a query and search stored chunk embeddings."""

    def __init__(
        self,
        storage: StorageBackend,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.storage = storage
        self.embedding_provider = embedding_provider

    def search(
        self,
        *,
        corpus_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return ranked chunk hits using vector cosine similarity."""
        query_embedding = self.embedding_provider.embed_query(query)
        return self.storage.search_chunks_semantic(
            corpus_id=corpus_id,
            query_embedding=query_embedding,
            limit=limit,
        )
