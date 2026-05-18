"""
Indexed query helpers for agent tools.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from ..embeddings import EmbeddingProvider
from ..storage import DuckDBStorage, StorageBackend
from .filters import MetadataFilter, parse_metadata_filters
from .ranker import RankedDocument, rank_documents


@dataclass(frozen=True)
class SearchHit:
    """Ranked document hit from indexed retrieval."""

    doc_id: str
    relative_path: str
    absolute_path: str
    position: int | None
    text: str
    semantic_score: float
    metadata_score: int
    score: float
    matched_by: str


class IndexedQueryEngine:
    """Parallel retrieval engine for semantic + metadata query paths."""

    def __init__(
        self,
        storage: StorageBackend,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.storage = storage
        self.embedding_provider = embedding_provider

    def search(
        self,
        *,
        corpus_id: str,
        query: str,
        filters: str | None = None,
        limit: int = 5,
        enable_semantic: bool = True,
        enable_metadata: bool = True,
    ) -> list[SearchHit]:
        normalized_limit = max(limit, 1)
        parsed_filters = self._parse_filters(corpus_id=corpus_id, filters=filters)
        semantic_limit = max(normalized_limit * 4, normalized_limit)
        metadata_limit = max(normalized_limit * 4, normalized_limit)

        run_semantic = enable_semantic
        run_metadata = enable_metadata and bool(parsed_filters)

        semantic_rows: list[dict[str, Any]]
        metadata_rows: list[dict[str, Any]]
        if run_semantic and run_metadata:
            semantic_rows, metadata_rows = self._search_parallel(
                corpus_id=corpus_id,
                query=query,
                metadata_filters=parsed_filters,
                semantic_limit=semantic_limit,
                metadata_limit=metadata_limit,
            )
        elif run_semantic:
            semantic_rows = self._semantic_query(
                corpus_id=corpus_id,
                query=query,
                limit=semantic_limit,
            )
            metadata_rows = []
        elif run_metadata:
            semantic_rows = []
            metadata_rows = self._metadata_query(
                corpus_id=corpus_id,
                metadata_filters=parsed_filters,
                limit=metadata_limit,
            )
        else:
            semantic_rows, metadata_rows = [], []

        ranked = self._merge_and_rank(
            semantic_rows=semantic_rows,
            metadata_rows=metadata_rows,
            limit=normalized_limit,
        )
        return [
            SearchHit(
                doc_id=doc.doc_id,
                relative_path=doc.relative_path,
                absolute_path=doc.absolute_path,
                position=doc.position,
                text=doc.text,
                semantic_score=doc.semantic_score,
                metadata_score=doc.metadata_score,
                score=doc.combined_score,
                matched_by=doc.matched_by,
            )
            for doc in ranked
        ]

    def _parse_filters(
        self, *, corpus_id: str, filters: str | None
    ) -> list[MetadataFilter]:
        if filters is None or not filters.strip():
            return []
        allowed_fields = self._allowed_filter_fields(corpus_id=corpus_id)
        return parse_metadata_filters(filters, allowed_fields=allowed_fields)

    def _allowed_filter_fields(self, *, corpus_id: str) -> set[str] | None:
        active_schema = self.storage.get_active_schema(corpus_id=corpus_id)
        if active_schema is None:
            return None
        fields = active_schema.schema_def.get("fields")
        if not isinstance(fields, list):
            return None
        allowed: set[str] = set()
        for field in fields:
            if isinstance(field, dict):
                name = field.get("name")
                if isinstance(name, str):
                    allowed.add(name)
        return allowed if allowed else None

    def _search_parallel(
        self,
        *,
        corpus_id: str,
        query: str,
        metadata_filters: list[MetadataFilter],
        semantic_limit: int,
        metadata_limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with ThreadPoolExecutor(max_workers=2) as executor:
            semantic_future = executor.submit(
                self._semantic_query,
                corpus_id=corpus_id,
                query=query,
                limit=semantic_limit,
            )
            metadata_future = executor.submit(
                self._metadata_query,
                corpus_id=corpus_id,
                metadata_filters=metadata_filters,
                limit=metadata_limit,
            )
            semantic_rows = semantic_future.result()
            metadata_rows = metadata_future.result()
        return semantic_rows, metadata_rows

    def _semantic_query(
        self,
        *,
        corpus_id: str,
        query: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        scoped_storage, cleanup = self._acquire_query_storage()
        try:
            if self.embedding_provider is not None and scoped_storage.has_embeddings(
                corpus_id=corpus_id
            ):
                query_embedding = self.embedding_provider.embed_query(query)
                return scoped_storage.search_chunks_semantic(
                    corpus_id=corpus_id,
                    query_embedding=query_embedding,
                    limit=limit,
                )
            return scoped_storage.search_chunks(
                corpus_id=corpus_id, query=query, limit=limit
            )
        finally:
            cleanup()

    def _metadata_query(
        self,
        *,
        corpus_id: str,
        metadata_filters: list[MetadataFilter],
        limit: int,
    ) -> list[dict[str, Any]]:
        scoped_storage, cleanup = self._acquire_query_storage()
        try:
            return scoped_storage.search_documents_by_metadata(
                corpus_id=corpus_id,
                filters=[flt.to_storage_dict() for flt in metadata_filters],
                limit=limit,
            )
        finally:
            cleanup()

    def _acquire_query_storage(self) -> tuple[StorageBackend, Callable[[], None]]:
        if isinstance(self.storage, DuckDBStorage):
            clone = DuckDBStorage(
                self.storage.db_path,
                read_only=self.storage.read_only,
                initialize=False,
                embedding_dim=self.storage.embedding_dim,
            )
            return clone, clone.close
        return self.storage, lambda: None

    @staticmethod
    def _merge_and_rank(
        *,
        semantic_rows: list[dict[str, Any]],
        metadata_rows: list[dict[str, Any]],
        limit: int,
    ) -> list[RankedDocument]:
        merged: dict[str, dict[str, Any]] = {}

        for row in semantic_rows:
            doc_id = str(row["doc_id"])
            score = float(row["score"])
            position = int(row["position"])
            entry = merged.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "relative_path": str(row["relative_path"]),
                    "absolute_path": str(row["absolute_path"]),
                    "position": position,
                    "text": str(row["text"]),
                    "semantic_score": 0.0,
                    "metadata_score": 0,
                },
            )
            if score > float(entry["semantic_score"]):
                entry["semantic_score"] = score
                entry["position"] = position
                entry["text"] = str(row["text"])

        for row in metadata_rows:
            doc_id = str(row["doc_id"])
            entry = merged.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "relative_path": str(row["relative_path"]),
                    "absolute_path": str(row["absolute_path"]),
                    "position": None,
                    "text": str(row.get("preview_text", "")),
                    "semantic_score": 0.0,
                    "metadata_score": 0,
                },
            )
            entry["metadata_score"] = max(
                int(entry["metadata_score"]),
                int(row.get("metadata_score", 1)),
            )
            if not entry["text"]:
                entry["text"] = str(row.get("preview_text", ""))

        documents = [
            RankedDocument(
                doc_id=str(entry["doc_id"]),
                relative_path=str(entry["relative_path"]),
                absolute_path=str(entry["absolute_path"]),
                position=int(entry["position"])
                if entry["position"] is not None
                else None,
                text=str(entry["text"]),
                semantic_score=float(entry["semantic_score"]),
                metadata_score=int(entry["metadata_score"]),
            )
            for entry in merged.values()
        ]
        return rank_documents(documents, limit=limit)
