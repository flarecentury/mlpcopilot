"""
DuckDB storage backend for index persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import duckdb

from .base import ChunkRecord, DocumentRecord, SchemaRecord


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def _query_terms(query: str, max_terms: int = 8) -> list[str]:
    terms = re.findall(r"[a-zA-Z0-9_]{3,}", query.lower())
    unique_terms: list[str] = []
    for term in terms:
        if term not in unique_terms:
            unique_terms.append(term)
        if len(unique_terms) >= max_terms:
            break
    if unique_terms:
        return unique_terms
    fallback = query.strip().lower()
    return [fallback] if fallback else []


class DuckDBStorage:
    """DuckDB-backed persistence for corpora, documents, chunks, and schemas."""

    def __init__(
        self,
        db_path: str,
        *,
        read_only: bool = False,
        initialize: bool = True,
        embedding_dim: int = 768,
    ) -> None:
        self.db_path = str(Path(db_path).expanduser().resolve())
        self.read_only = read_only
        self.embedding_dim = embedding_dim
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(self.db_path, read_only=read_only)
        self._vss_available = False
        if initialize and not read_only:
            self.initialize()
        if not read_only:
            self._try_load_vss()

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._conn.close()

    def initialize(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS corpora (
                id VARCHAR PRIMARY KEY,
                root_path VARCHAR NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id VARCHAR PRIMARY KEY,
                corpus_id VARCHAR NOT NULL REFERENCES corpora(id),
                relative_path VARCHAR NOT NULL,
                absolute_path VARCHAR NOT NULL,
                content VARCHAR NOT NULL,
                metadata_json VARCHAR NOT NULL DEFAULT '{}',
                file_mtime DOUBLE NOT NULL,
                file_size BIGINT NOT NULL,
                content_sha256 VARCHAR NOT NULL,
                last_indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE,
                UNIQUE(corpus_id, relative_path)
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id VARCHAR PRIMARY KEY,
                doc_id VARCHAR NOT NULL REFERENCES documents(id),
                text VARCHAR NOT NULL,
                position INTEGER NOT NULL,
                start_char INTEGER NOT NULL,
                end_char INTEGER NOT NULL
            );
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schemas (
                id VARCHAR PRIMARY KEY,
                corpus_id VARCHAR NOT NULL REFERENCES corpora(id),
                name VARCHAR NOT NULL,
                schema_def VARCHAR NOT NULL,
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(corpus_id, name)
            );
            """
        )
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id VARCHAR PRIMARY KEY REFERENCES chunks(id),
                corpus_id VARCHAR NOT NULL,
                embedding FLOAT[{self.embedding_dim}] NOT NULL
            );
            """
        )

    def _try_load_vss(self) -> None:
        """Attempt to install and load the vss extension for HNSW acceleration."""
        try:
            self._conn.execute("INSTALL vss")
            self._conn.execute("LOAD vss")
            self._vss_available = True
        except Exception:
            self._vss_available = False

    def get_or_create_corpus(self, root_path: str) -> str:
        normalized = str(Path(root_path).resolve())
        corpus_id = _stable_id("corpus", normalized)
        self._conn.execute(
            """
            INSERT INTO corpora (id, root_path)
            VALUES (?, ?)
            ON CONFLICT(root_path) DO NOTHING
            """,
            [corpus_id, normalized],
        )
        row = self._conn.execute(
            "SELECT id FROM corpora WHERE root_path = ?",
            [normalized],
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to create corpus for path: {normalized}")
        return str(row[0])

    def get_corpus_id(self, root_path: str) -> str | None:
        normalized = str(Path(root_path).resolve())
        row = self._conn.execute(
            "SELECT id FROM corpora WHERE root_path = ?",
            [normalized],
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def upsert_document(
        self, document: DocumentRecord, chunks: list[ChunkRecord]
    ) -> None:
        # Cascade-delete embeddings for old chunks, then remove old chunks.
        self._conn.execute(
            """
            DELETE FROM chunk_embeddings
            WHERE chunk_id IN (SELECT id FROM chunks WHERE doc_id = ?)
            """,
            [document.id],
        )
        self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", [document.id])

        self._conn.execute(
            """
            INSERT INTO documents (
                id, corpus_id, relative_path, absolute_path, content, metadata_json,
                file_mtime, file_size, content_sha256, is_deleted
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE)
            ON CONFLICT(id) DO UPDATE SET
                corpus_id = excluded.corpus_id,
                relative_path = excluded.relative_path,
                absolute_path = excluded.absolute_path,
                content = excluded.content,
                metadata_json = excluded.metadata_json,
                file_mtime = excluded.file_mtime,
                file_size = excluded.file_size,
                content_sha256 = excluded.content_sha256,
                last_indexed_at = now(),
                is_deleted = FALSE
            """,
            [
                document.id,
                document.corpus_id,
                document.relative_path,
                document.absolute_path,
                document.content,
                document.metadata_json,
                document.file_mtime,
                document.file_size,
                document.content_sha256,
            ],
        )

        if chunks:
            self._conn.executemany(
                """
                INSERT INTO chunks (id, doc_id, text, position, start_char, end_char)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.id,
                        chunk.doc_id,
                        chunk.text,
                        chunk.position,
                        chunk.start_char,
                        chunk.end_char,
                    )
                    for chunk in chunks
                ],
            )

    def mark_deleted_missing_documents(
        self,
        *,
        corpus_id: str,
        active_relative_paths: set[str],
    ) -> int:
        if not active_relative_paths:
            self._conn.execute(
                """
                UPDATE documents
                SET is_deleted = TRUE
                WHERE corpus_id = ? AND is_deleted = FALSE
                """,
                [corpus_id],
            )
        else:
            placeholders = ", ".join(["?"] * len(active_relative_paths))
            params: list[Any] = [corpus_id]
            params.extend(sorted(active_relative_paths))
            self._conn.execute(
                f"""
                UPDATE documents
                SET is_deleted = TRUE
                WHERE corpus_id = ?
                  AND is_deleted = FALSE
                  AND relative_path NOT IN ({placeholders})
                """,
                params,
            )

        row = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM documents
            WHERE corpus_id = ? AND is_deleted = TRUE
            """,
            [corpus_id],
        ).fetchone()
        return int(row[0]) if row else 0

    def list_documents(
        self,
        *,
        corpus_id: str,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT id, relative_path, absolute_path, file_size, file_mtime, is_deleted
            FROM documents
            WHERE corpus_id = ?
        """
        params: list[Any] = [corpus_id]
        if not include_deleted:
            sql += " AND is_deleted = FALSE"
        sql += " ORDER BY relative_path"

        rows = self._conn.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "id": str(row[0]),
                    "relative_path": str(row[1]),
                    "absolute_path": str(row[2]),
                    "file_size": int(row[3]),
                    "file_mtime": float(row[4]),
                    "is_deleted": bool(row[5]),
                }
            )
        return results

    def count_chunks(self, *, corpus_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*)
            FROM chunks c
            JOIN documents d ON d.id = c.doc_id
            WHERE d.corpus_id = ? AND d.is_deleted = FALSE
            """,
            [corpus_id],
        ).fetchone()
        return int(row[0]) if row else 0

    def search_chunks(
        self,
        *,
        corpus_id: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        terms = _query_terms(query)
        if not terms:
            return []

        score_expr = " + ".join(
            ["CASE WHEN lower(c.text) LIKE '%' || ? || '%' THEN 1 ELSE 0 END"]
            * len(terms)
        )
        sql = f"""
            SELECT * FROM (
                SELECT
                    d.id AS doc_id,
                    d.relative_path,
                    d.absolute_path,
                    c.position,
                    c.text,
                    ({score_expr}) AS score
                FROM chunks c
                JOIN documents d ON d.id = c.doc_id
                WHERE d.corpus_id = ?
                  AND d.is_deleted = FALSE
            ) ranked
            WHERE score > 0
            ORDER BY score DESC, relative_path ASC, position ASC
            LIMIT ?
        """
        params: list[Any] = []
        params.extend(terms)
        params.append(corpus_id)
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "doc_id": str(row[0]),
                    "relative_path": str(row[1]),
                    "absolute_path": str(row[2]),
                    "position": int(row[3]),
                    "text": str(row[4]),
                    "score": int(row[5]),
                }
            )
        return results

    def search_documents_by_metadata(
        self,
        *,
        corpus_id: str,
        filters: list[dict[str, Any]],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not filters:
            return []

        sql = """
            SELECT
                d.id,
                d.relative_path,
                d.absolute_path,
                substring(d.content, 1, 320) AS preview_text
            FROM documents d
            WHERE d.corpus_id = ?
              AND d.is_deleted = FALSE
        """
        params: list[Any] = [corpus_id]

        for flt in filters:
            field = str(flt["field"])
            operator = str(flt["operator"])
            value = flt["value"]
            clause, clause_params = self._metadata_clause(
                field=field,
                operator=operator,
                value=value,
            )
            sql += f"\n  AND {clause}"
            params.extend(clause_params)

        sql += "\nORDER BY d.relative_path ASC\nLIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        metadata_score = len(filters)
        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "doc_id": str(row[0]),
                    "relative_path": str(row[1]),
                    "absolute_path": str(row[2]),
                    "preview_text": str(row[3]),
                    "metadata_score": metadata_score,
                }
            )
        return results

    def get_document(self, *, doc_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT
                id, corpus_id, relative_path, absolute_path, content, metadata_json, is_deleted
            FROM documents
            WHERE id = ?
            LIMIT 1
            """,
            [doc_id],
        ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "corpus_id": str(row[1]),
            "relative_path": str(row[2]),
            "absolute_path": str(row[3]),
            "content": str(row[4]),
            "metadata_json": str(row[5]),
            "is_deleted": bool(row[6]),
        }

    def save_schema(
        self,
        *,
        corpus_id: str,
        name: str,
        schema_def: dict[str, Any],
        is_active: bool = True,
    ) -> str:
        schema_id = _stable_id("schema", f"{corpus_id}:{name}")
        if is_active:
            self._conn.execute(
                "UPDATE schemas SET is_active = FALSE WHERE corpus_id = ?",
                [corpus_id],
            )

        self._conn.execute(
            """
            INSERT INTO schemas (id, corpus_id, name, schema_def, is_active)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(corpus_id, name) DO UPDATE SET
                schema_def = excluded.schema_def,
                is_active = excluded.is_active
            """,
            [
                schema_id,
                corpus_id,
                name,
                json.dumps(schema_def, sort_keys=True),
                is_active,
            ],
        )
        return schema_id

    def list_schemas(self, *, corpus_id: str) -> list[SchemaRecord]:
        rows = self._conn.execute(
            """
            SELECT id, corpus_id, name, schema_def, is_active, created_at
            FROM schemas
            WHERE corpus_id = ?
            ORDER BY created_at DESC, name ASC
            """,
            [corpus_id],
        ).fetchall()
        return [self._row_to_schema_record(row) for row in rows]

    def get_schema_by_name(self, *, corpus_id: str, name: str) -> SchemaRecord | None:
        row = self._conn.execute(
            """
            SELECT id, corpus_id, name, schema_def, is_active, created_at
            FROM schemas
            WHERE corpus_id = ? AND name = ?
            LIMIT 1
            """,
            [corpus_id, name],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_schema_record(row)

    def get_active_schema(self, *, corpus_id: str) -> SchemaRecord | None:
        row = self._conn.execute(
            """
            SELECT id, corpus_id, name, schema_def, is_active, created_at
            FROM schemas
            WHERE corpus_id = ? AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [corpus_id],
        ).fetchone()
        if row is None:
            return None
        return self._row_to_schema_record(row)

    @staticmethod
    def make_document_id(corpus_id: str, relative_path: str) -> str:
        return _stable_id("doc", f"{corpus_id}:{relative_path}")

    @staticmethod
    def make_chunk_id(
        doc_id: str, position: int, start_char: int, end_char: int
    ) -> str:
        return _stable_id("chunk", f"{doc_id}:{position}:{start_char}:{end_char}")

    @staticmethod
    def _row_to_schema_record(row: tuple[Any, ...]) -> SchemaRecord:
        return SchemaRecord(
            id=str(row[0]),
            corpus_id=str(row[1]),
            name=str(row[2]),
            schema_def=json.loads(str(row[3])),
            is_active=bool(row[4]),
            created_at=str(row[5]),
        )

    def store_chunk_embeddings(
        self,
        *,
        corpus_id: str,
        chunk_embeddings: list[tuple[str, list[float]]],
    ) -> int:
        """Bulk-store (chunk_id, embedding) pairs. Return count written."""
        if not chunk_embeddings:
            return 0
        self._conn.executemany(
            """
            INSERT INTO chunk_embeddings (chunk_id, corpus_id, embedding)
            VALUES (?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                corpus_id = excluded.corpus_id,
                embedding = excluded.embedding
            """,
            [(cid, corpus_id, emb) for cid, emb in chunk_embeddings],
        )
        return len(chunk_embeddings)

    def search_chunks_semantic(
        self,
        *,
        corpus_id: str,
        query_embedding: list[float],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search chunks by cosine similarity against a query embedding."""
        sql = """
            SELECT
                d.id AS doc_id,
                d.relative_path,
                d.absolute_path,
                c.position,
                c.text,
                array_cosine_similarity(ce.embedding, ?::FLOAT[{dim}]) AS score
            FROM chunk_embeddings ce
            JOIN chunks c ON c.id = ce.chunk_id
            JOIN documents d ON d.id = c.doc_id
            WHERE ce.corpus_id = ?
              AND d.is_deleted = FALSE
            ORDER BY score DESC
            LIMIT ?
        """.format(dim=self.embedding_dim)
        rows = self._conn.execute(sql, [query_embedding, corpus_id, limit]).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "doc_id": str(row[0]),
                    "relative_path": str(row[1]),
                    "absolute_path": str(row[2]),
                    "position": int(row[3]),
                    "text": str(row[4]),
                    "score": float(row[5]),
                }
            )
        return results

    def get_metadata_field_values(
        self,
        *,
        corpus_id: str,
        field_names: list[str],
        max_distinct: int = 10,
    ) -> dict[str, list[str]]:
        """Return up to *max_distinct* distinct non-empty values per metadata field."""
        result: dict[str, list[str]] = {}
        for field in field_names:
            rows = self._conn.execute(
                """
                SELECT DISTINCT json_extract_string(d.metadata_json, ?) AS val
                FROM documents d
                WHERE d.corpus_id = ?
                  AND d.is_deleted = FALSE
                  AND val IS NOT NULL
                  AND val != ''
                LIMIT ?
                """,
                [f"$.{field}", corpus_id, max_distinct],
            ).fetchall()
            result[field] = [str(row[0]) for row in rows]
        return result

    def has_embeddings(self, *, corpus_id: str) -> bool:
        """Return True if the corpus has stored embeddings."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM chunk_embeddings WHERE corpus_id = ?",
            [corpus_id],
        ).fetchone()
        return bool(row and int(row[0]) > 0)

    def create_hnsw_index(self, *, corpus_id: str) -> bool:
        """Create an HNSW index on chunk embeddings if vss is available.

        Returns True if the index was created, False otherwise.
        """
        if not self._vss_available:
            return False
        try:
            index_name = f"hnsw_{corpus_id.replace('-', '_')}"
            self._conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {index_name}
                ON chunk_embeddings
                USING HNSW (embedding)
                WITH (metric = 'cosine')
                """
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _metadata_clause(
        *,
        field: str,
        operator: str,
        value: Any,
    ) -> tuple[str, list[Any]]:
        json_expr = "json_extract_string(d.metadata_json, ?)"
        json_path = f"$.{field}"

        if operator in {"eq", "ne"}:
            comparator = "=" if operator == "eq" else "<>"
            if isinstance(value, bool):
                return (
                    f"lower(coalesce({json_expr}, '')) {comparator} ?",
                    [json_path, "true" if value else "false"],
                )
            if isinstance(value, (int, float)):
                return (
                    f"try_cast({json_expr} AS DOUBLE) {comparator} ?",
                    [json_path, float(value)],
                )
            return (
                f"lower(coalesce({json_expr}, '')) {comparator} lower(?)",
                [json_path, str(value)],
            )

        if operator in {"gt", "gte", "lt", "lte"}:
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"Metadata operator {operator!r} requires numeric value for field {field!r}."
                )
            comparator_map = {
                "gt": ">",
                "gte": ">=",
                "lt": "<",
                "lte": "<=",
            }
            comparator = comparator_map[operator]
            return (
                f"try_cast({json_expr} AS DOUBLE) {comparator} ?",
                [json_path, float(value)],
            )

        if operator == "contains":
            return (
                f"lower(coalesce({json_expr}, '')) LIKE '%' || lower(?) || '%'",
                [json_path, str(value)],
            )

        if operator == "in":
            if not isinstance(value, list) or not value:
                raise ValueError(
                    f"Metadata `in` filter for field {field!r} has no values."
                )

            if all(isinstance(item, bool) for item in value):
                placeholders = ", ".join(["?"] * len(value))
                return (
                    f"lower(coalesce({json_expr}, '')) IN ({placeholders})",
                    [
                        json_path,
                        *["true" if bool(item) else "false" for item in value],
                    ],
                )

            if all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in value
            ):
                placeholders = ", ".join(["?"] * len(value))
                return (
                    f"try_cast({json_expr} AS DOUBLE) IN ({placeholders})",
                    [json_path, *[float(item) for item in value]],
                )

            placeholders = ", ".join(["?"] * len(value))
            return (
                f"lower(coalesce({json_expr}, '')) IN ({placeholders})",
                [json_path, *[str(item).lower() for item in value]],
            )

        raise ValueError(f"Unsupported metadata operator: {operator!r}")
