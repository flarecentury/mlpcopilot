# Implementation Plan: Hybrid Semantic + Agentic Search (Revised)

## Overview

Add semantic search with optional metadata filtering to `agentic-file-search` without regressing the current agentic workflow.

The revised approach keeps the current CLI and behavior stable first, introduces indexing as opt-in, and only enables auto-detection after compatibility and quality checks pass.

- Storage: DuckDB + `vss` (embedded, local file)
- Embeddings: Gemini embeddings (API-backed)
- Metadata extraction: `langextract` (optional)
- Infrastructure model: no external database service (no Docker/Postgres required)

---

## Goals

1. Preserve existing `explore --task` behavior and UX by default.
2. Add a fast indexed path for large corpora.
3. Support metadata-aware filtering when metadata is available.
4. Keep agentic deep-read and cross-reference behavior available.

## Non-Goals (Initial Release)

1. Replacing the existing agentic strategy entirely.
2. Forcing index usage for all queries.
3. Heuristic/NLP folder extraction from free-form task text.

---

## Current Codebase Constraints to Respect

1. CLI currently has one root command (`explore --task`) and no subcommands.
2. Workflow and server currently use shared/global process state (`os.chdir`, singleton agent).
3. Existing tests assert the current 6-tool model and prompt behavior.

These constraints require a staged rollout to avoid breaking current users.

---

## High-Level Architecture

```text
INDEX TIME
├── Parse documents (Docling)
├── Chunk content (paragraph/sentence-aware)
├── Generate embeddings (provider-configured dimension)
├── [optional] Extract metadata (langextract)
└── Persist in DuckDB (corpus-scoped)

QUERY TIME
├── Retrieve by semantic search
├── [optional] Retrieve by metadata filter
├── Union + rank results
├── Expand via cross-references where needed
└── Agent continues deep exploration using existing tools
```

---

## Data Model (DuckDB)

Use corpus-scoped tables and file freshness fields to prevent collisions and stale indexes.

```sql
-- Install and load extension programmatically
-- INSTALL vss; LOAD vss;

CREATE TABLE IF NOT EXISTS corpora (
    id VARCHAR PRIMARY KEY,
    root_path VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    corpus_id VARCHAR NOT NULL REFERENCES corpora(id),
    relative_path VARCHAR NOT NULL,
    absolute_path VARCHAR NOT NULL,
    content VARCHAR NOT NULL,
    metadata JSON NOT NULL DEFAULT '{}',
    file_mtime DOUBLE NOT NULL,
    file_size BIGINT NOT NULL,
    content_sha256 VARCHAR NOT NULL,
    last_indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(corpus_id, relative_path)
);

-- EMBEDDING_DIM is configured in code at index creation time.
CREATE TABLE IF NOT EXISTS chunks (
    id VARCHAR PRIMARY KEY,
    doc_id VARCHAR NOT NULL REFERENCES documents(id),
    text VARCHAR NOT NULL,
    embedding FLOAT[${EMBEDDING_DIM}] NOT NULL,
    embedding_dim INTEGER NOT NULL,
    position INTEGER NOT NULL,
    start_char INTEGER NOT NULL,
    end_char INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS schemas (
    id INTEGER PRIMARY KEY,
    corpus_id VARCHAR REFERENCES corpora(id),
    name VARCHAR,
    schema_def JSON NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    UNIQUE(corpus_id, name)
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding
ON chunks USING HNSW (embedding) WITH (metric = 'cosine');
```

### Embedding Dimension Rule

`EMBEDDING_DIM` must be a runtime config constant validated at startup. Do not hardcode `1536` across modules.

### DB Location

Default: `~/.fs_explorer/index.duckdb`
Override via:
- `FS_EXPLORER_DB_PATH`
- CLI: `--db-path`

---

## CLI Contract and Rollout

### Compatibility Rules (Required)

1. `uv run explore --task "..."` must keep working as-is.
2. Existing non-indexed behavior remains default in initial rollout.
3. New indexed behavior is opt-in first.

### New Commands

```bash
# Index management
uv run explore index <folder>
uv run explore index <folder> --with-metadata
uv run explore index <folder> --schema schema.json

# Indexed query path
uv run explore query --task "..." --folder <folder> [--filter "..."]

# Schema inspection
uv run explore schema --discover <folder>
uv run explore schema --show --folder <folder>

# Existing command (backward-compatible)
uv run explore --task "..." [--folder <folder>] [--use-index]
```

### Folder Resolution (Deterministic)

For commands that need corpus selection:
1. If `--folder` is provided, use it.
2. Else use current working directory (`.`).
3. Do not parse folder intent from natural language task text in v1.

### Auto-Detection Strategy

- v1: explicit `--use-index` only.
- v2: optional auto-detect behind feature flag `FS_EXPLORER_AUTO_INDEX=1`.
- v3: default auto-detect only after parity tests and quality benchmarks pass.

---

## Server and Concurrency Requirements

Before adding indexing/search endpoints:

1. Remove request-level `os.chdir` usage; pass absolute target folder through workflow state.
2. Avoid global singleton agent across concurrent requests; instantiate per workflow run/session.
3. Add per-corpus index lock to avoid concurrent write corruption.
4. Keep read queries concurrent-safe.

---

## Module Structure

```text
src/fs_explorer/
├── storage/
│   ├── __init__.py
│   ├── base.py
│   └── duckdb.py
├── indexing/
│   ├── __init__.py
│   ├── pipeline.py
│   ├── chunker.py
│   ├── metadata.py
│   └── schema.py
├── search/
│   ├── __init__.py
│   ├── query.py
│   ├── semantic.py
│   ├── filters.py
│   └── ranker.py
├── embeddings.py
└── index_config.py
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/fs_explorer/agent.py` | Add indexed tools and prompt guidance while keeping existing tools |
| `src/fs_explorer/models.py` | Extend `Tools` type alias |
| `src/fs_explorer/main.py` | Add subcommands + `--folder` + `--use-index` while preserving root command |
| `src/fs_explorer/workflow.py` | Remove global/shared run-state assumptions |
| `src/fs_explorer/fs.py` | Support safe path resolution without cwd mutation |
| `src/fs_explorer/server.py` | Add index/search endpoints and remove `os.chdir` coupling |
| `pyproject.toml` | Add `duckdb`, `langextract` |

---

## Implementation Phases

### Phase 0: Contracts and Safety (New)

1. Freeze CLI compatibility requirements (`explore --task` must remain stable).
2. Define deterministic folder resolution contract.
3. Define per-request state model for workflow/server.
4. Add failing tests for compatibility and concurrency assumptions.

### Phase 1: Storage + Embeddings

5. Implement `storage/base.py` (backend interface).
6. Implement `storage/duckdb.py` with corpus-scoped schema.
7. Implement `embeddings.py` with configurable embedding dimension.
8. Add storage/embedding tests (including dimension validation).

### Phase 2: Indexing Pipeline

9. Implement `indexing/chunker.py`.
10. Implement optional `indexing/metadata.py`.
11. Implement `indexing/schema.py`.
12. Implement `indexing/pipeline.py` with freshness checks (`mtime`, hash, deleted files).
13. Add indexing tests.

### Phase 3: Search Pipeline

14. Implement `search/filters.py`.
15. Implement `search/ranker.py`.
16. Implement `search/query.py` (parallel retrieval + union).
17. Implement cross-reference expansion hooks.
18. Add search tests.

### Phase 4: Agent Integration (Opt-in)

19. Add tools: `semantic_search`, `get_document`, `list_indexed_documents`.
20. Keep existing 6 filesystem tools available.
21. Add indexed prompt guidance without removing current strategy.
22. Add tool-selection tests for indexed and non-indexed paths.

### Phase 5: CLI + Server Integration

23. Add `explore index/query/schema` commands.
24. Add `--folder` and `--use-index` to root command.
25. Integrate indexed path into workflow when explicitly requested.
26. Add `/api/index` and `/api/search` endpoints.
27. Remove `os.chdir` in server workflow path.

### Phase 6: Auto-Detect Rollout (Guarded)

28. Add feature-flagged auto-detect (`FS_EXPLORER_AUTO_INDEX`).
29. Add parity checks between indexed and baseline runs on test corpora.
30. Keep fallback to legacy behavior on index errors.

### Phase 7: Testing and Docs

31. Full integration tests.
32. Backward compatibility tests.
33. Concurrency tests for WebSocket/API usage.
34. Performance benchmarks and docs updates.

---

## Revised Design Decisions

1. **Opt-in First**: indexed retrieval starts behind `--use-index` to avoid regressions.
2. **Deterministic Corpus Selection**: explicit `--folder` or `.` fallback only.
3. **Corpus-Scoped Storage**: avoid global path collisions by namespacing.
4. **Freshness Tracking**: incremental reindex using mtime/hash/deletion markers.
5. **No Global Request State**: remove `os.chdir` and shared singleton pitfalls in server flows.
6. **Configurable Embedding Dimension**: validated at runtime; not hardcoded everywhere.
7. **No External DB Service**: embedded local DB only; APIs are still external dependencies.

---

## Verification Steps

```bash
# Baseline safety (must stay green)
uv run pytest tests/test_models.py tests/test_fs.py tests/test_agent.py -v

# Phase 1-3
uv run pytest tests/test_storage.py tests/test_embeddings.py tests/test_search.py -v

# Index build + inspect
uv run explore index data/test_acquisition/
uv run python -c "import duckdb; db=duckdb.connect('~/.fs_explorer/index.duckdb'); print(db.execute('SELECT COUNT(*) FROM documents').fetchone())"

# Opt-in indexed execution
uv run explore --task "Search for acquisition terms" --folder data/test_acquisition --use-index

# Compatibility execution (legacy path)
uv run explore --task "Look in data/test_acquisition/. Who is the CTO?"

# CLI checks
uv run explore --help
uv run explore index --help
uv run explore query --help
uv run explore schema --help

# Full suite
uv run pytest tests/ -v
```

---

## Dependencies to Add

```toml
# pyproject.toml
dependencies = [
    # ... existing ...
    "duckdb>=1.0.0",
    "langextract>=1.0.0",
]
```

---

## Critical Files Summary

| Purpose | Path |
|---------|------|
| Storage interface | `src/fs_explorer/storage/base.py` |
| DuckDB backend | `src/fs_explorer/storage/duckdb.py` |
| Embeddings | `src/fs_explorer/embeddings.py` |
| Chunking | `src/fs_explorer/indexing/chunker.py` |
| Metadata extraction | `src/fs_explorer/indexing/metadata.py` |
| Schema discovery | `src/fs_explorer/indexing/schema.py` |
| Indexing pipeline | `src/fs_explorer/indexing/pipeline.py` |
| Query pipeline | `src/fs_explorer/search/query.py` |
| Filter parsing | `src/fs_explorer/search/filters.py` |
| Result ranking | `src/fs_explorer/search/ranker.py` |
| Agent tools/prompt | `src/fs_explorer/agent.py` |
| Tool types | `src/fs_explorer/models.py` |
| CLI commands | `src/fs_explorer/main.py` |
| Workflow safety | `src/fs_explorer/workflow.py` |
| Server safety/endpoints | `src/fs_explorer/server.py` |
