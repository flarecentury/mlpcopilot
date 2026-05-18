"""Tests for indexing and schema components."""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import fs_explorer.indexing.metadata as metadata_module
import fs_explorer.indexing.pipeline as pipeline_module
from fs_explorer.embeddings import EmbeddingProvider
from fs_explorer.indexing.chunker import SmartChunker
from fs_explorer.indexing.metadata import auto_discover_profile, normalize_langextract_profile
from fs_explorer.indexing.pipeline import IndexingPipeline
from fs_explorer.indexing.schema import SchemaDiscovery
from fs_explorer.storage import DuckDBStorage


def test_smart_chunker_overlap() -> None:
    text = "A" * 2500
    chunker = SmartChunker(chunk_size=1000, overlap=100)

    chunks = chunker.chunk_text(text)

    assert len(chunks) == 3
    assert chunks[1].start_char == chunks[0].end_char - 100
    assert chunks[2].start_char == chunks[1].end_char - 100


def test_schema_discovery_from_folder(tmp_path: Path) -> None:
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "01_master_agreement.md").write_text("# agreement\nprice: $10")
    (folder / "04_risk_report.md").write_text("# report\nrisk summary")

    schema = SchemaDiscovery().discover_from_folder(str(folder))

    fields = schema["fields"]
    field_names = {field["name"] for field in fields}
    assert "document_type" in field_names
    assert "mentions_currency" in field_names

    document_type_field = next(
        field for field in fields if field["name"] == "document_type"
    )
    assert "agreement" in document_type_field["enum"]
    assert "report" in document_type_field["enum"]


def test_schema_discovery_with_langextract_fields(tmp_path: Path, monkeypatch) -> None:
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "agreement.md").write_text("Purchase price with escrow and earnout.")

    # Mock auto_discover_profile to return the default profile so this test
    # stays deterministic (auto-discovery would call the real LLM).
    from fs_explorer.indexing.metadata import default_langextract_profile

    monkeypatch.setattr(
        "fs_explorer.indexing.schema.auto_discover_profile",
        lambda folder, **kwargs: default_langextract_profile(),
    )

    schema = SchemaDiscovery().discover_from_folder(
        str(folder),
        with_langextract=True,
    )
    field_names = {field["name"] for field in schema["fields"]}
    assert "lx_enabled" in field_names
    assert "lx_has_earnout" in field_names
    assert "lx_money_mentions" in field_names


def test_schema_discovery_with_custom_metadata_profile(tmp_path: Path) -> None:
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "notes.md").write_text("Acme Corp retained Jane Doe for diligence.")

    profile = {
        "prompt_description": "Extract organizations and people.",
        "fields": [
            {
                "name": "org_names",
                "type": "string",
                "source_class": "organization",
                "mode": "values",
            },
            {
                "name": "person_count",
                "type": "integer",
                "source_class": "person",
                "mode": "count",
            },
        ],
    }

    schema = SchemaDiscovery().discover_from_folder(
        str(folder),
        with_langextract=True,
        metadata_profile=profile,
    )
    field_names = {field["name"] for field in schema["fields"]}
    assert "org_names" in field_names
    assert "person_count" in field_names
    assert isinstance(schema.get("metadata_profile"), dict)


def test_indexable_extensions_include_mlp_input_files() -> None:
    assert {
        ".yml",
        ".inp",
        ".in",
        ".input",
        ".lmp",
        ".lammps",
    }.issubset(pipeline_module.INDEXABLE_EXTENSIONS)


def test_extra_indexable_extensions_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "FS_EXPLORER_EXTRA_INDEXABLE_EXTENSIONS",
        "foo, .bar *.baz;qux",
    )

    assert {
        ".foo",
        ".bar",
        ".baz",
        ".qux",
    }.issubset(pipeline_module.get_indexable_text_extensions())


def test_indexing_pipeline_indexes_simulation_input_files(tmp_path: Path) -> None:
    corpus = tmp_path / "inputs"
    corpus.mkdir()
    for filename in (
        "params.yml",
        "job.inp",
        "input.in",
        "control.input",
        "forcefield.lmp",
        "system.lammps",
    ):
        (corpus / filename).write_text(f"{filename}\nunits metal\n")

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    result = IndexingPipeline(storage=storage).index_folder(str(corpus))

    assert result.indexed_files == 6
    assert result.skipped_files == 0
    assert result.active_documents == 6


def test_indexing_pipeline_indexes_extra_env_extensions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FS_EXPLORER_EXTRA_INDEXABLE_EXTENSIONS", "custom")
    corpus = tmp_path / "inputs"
    corpus.mkdir()
    (corpus / "config.custom").write_text("custom input\n")

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    result = IndexingPipeline(storage=storage).index_folder(str(corpus))

    assert result.indexed_files == 1
    assert result.active_documents == 1


def test_indexing_pipeline_indexes_and_marks_deleted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    first = corpus / "a_agreement.md"
    second = corpus / "b_schedule.md"
    first.write_text("Purchase price is $45,000,000.\n\nSection 1.2")
    second.write_text("Schedule details.\n\nEffective Date: January 1, 2026")

    # Avoid Docling in this unit test; treat markdown as plain text.
    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    db_path = tmp_path / "index.duckdb"
    storage = DuckDBStorage(str(db_path))
    pipeline = IndexingPipeline(storage=storage)

    first_result = pipeline.index_folder(str(corpus), discover_schema=True)
    assert first_result.indexed_files == 2
    assert first_result.skipped_files == 0
    assert first_result.active_documents == 2
    assert first_result.schema_used is not None
    assert storage.count_chunks(corpus_id=first_result.corpus_id) > 0

    hits = storage.search_chunks(
        corpus_id=first_result.corpus_id,
        query="purchase price",
        limit=3,
    )
    assert hits
    top_doc = storage.get_document(doc_id=hits[0]["doc_id"])
    assert top_doc is not None
    assert "Purchase price" in top_doc["content"]

    metadata_hits = storage.search_documents_by_metadata(
        corpus_id=first_result.corpus_id,
        filters=[
            {
                "field": "document_type",
                "operator": "eq",
                "value": "agreement",
            }
        ],
        limit=5,
    )
    assert metadata_hits
    assert any(hit["relative_path"] == "a_agreement.md" for hit in metadata_hits)
    assert all(hit["relative_path"] != "b_schedule.md" for hit in metadata_hits)

    second.unlink()

    second_result = pipeline.index_folder(str(corpus))
    assert second_result.indexed_files == 1
    assert second_result.active_documents == 1

    all_docs = storage.list_documents(
        corpus_id=first_result.corpus_id,
        include_deleted=True,
    )
    deleted_paths = {doc["relative_path"] for doc in all_docs if doc["is_deleted"]}
    assert "b_schedule.md" in deleted_paths


def test_indexing_pipeline_with_langextract_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    doc_path = corpus / "agreement.md"
    doc_path.write_text("Purchase price and escrow details.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )
    # Use the default profile so the schema includes the expected fields
    from fs_explorer.indexing.metadata import default_langextract_profile

    monkeypatch.setattr(
        "fs_explorer.indexing.schema.auto_discover_profile",
        lambda folder, **kwargs: default_langextract_profile(),
    )
    monkeypatch.setattr(
        metadata_module,
        "_extract_langextract_metadata",
        lambda **_: {
            "lx_enabled": True,
            "lx_extraction_count": 3,
            "lx_entity_classes": "deal_term,organization",
            "lx_organizations": "TechCorp Industries",
            "lx_people": "",
            "lx_deal_terms": "escrow reserve",
            "lx_money_mentions": 1,
            "lx_date_mentions": 0,
            "lx_has_earnout": False,
            "lx_has_escrow": True,
        },
    )

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    pipeline = IndexingPipeline(storage=storage)
    result = pipeline.index_folder(
        str(corpus),
        discover_schema=True,
        with_metadata=True,
    )
    assert result.indexed_files == 1
    assert result.schema_used is not None

    docs = storage.list_documents(corpus_id=result.corpus_id, include_deleted=False)
    assert len(docs) == 1
    stored = storage.get_document(doc_id=docs[0]["id"])
    assert stored is not None
    metadata = json.loads(stored["metadata_json"])
    assert metadata["lx_enabled"] is True
    assert metadata["lx_has_escrow"] is True

    hits = storage.search_documents_by_metadata(
        corpus_id=result.corpus_id,
        filters=[{"field": "lx_has_escrow", "operator": "eq", "value": True}],
        limit=5,
    )
    assert hits
    assert hits[0]["relative_path"] == "agreement.md"


def test_indexing_pipeline_reuses_saved_metadata_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    doc_path = corpus / "custom.md"
    doc_path.write_text("Acme Corp and Jane Doe signed terms.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    seen_profiles: list[dict[str, object] | None] = []

    def fake_extract(**kwargs):  # noqa: ANN003
        seen_profiles.append(kwargs.get("profile"))
        return {
            "org_names": "Acme Corp",
            "person_present": True,
        }

    monkeypatch.setattr(metadata_module, "_extract_langextract_metadata", fake_extract)

    custom_profile = {
        "prompt_description": "Extract organizations and people.",
        "fields": [
            {
                "name": "org_names",
                "type": "string",
                "source_class": "organization",
                "mode": "values",
            },
            {
                "name": "person_present",
                "type": "boolean",
                "source_class": "person",
                "mode": "exists",
            },
        ],
    }

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    pipeline = IndexingPipeline(storage=storage)
    first_result = pipeline.index_folder(
        str(corpus),
        discover_schema=True,
        with_metadata=True,
        metadata_profile=custom_profile,
    )
    assert first_result.indexed_files == 1
    assert seen_profiles and isinstance(seen_profiles[0], dict)

    second_result = pipeline.index_folder(
        str(corpus),
        with_metadata=True,
    )
    assert second_result.indexed_files == 1
    assert len(seen_profiles) >= 2
    latest_profile = seen_profiles[-1]
    assert isinstance(latest_profile, dict)
    fields_obj = latest_profile.get("fields")
    assert isinstance(fields_obj, list)
    second_fields = {
        str(field["name"])
        for field in fields_obj
        if isinstance(field, dict) and isinstance(field.get("name"), str)
    }
    assert {"org_names", "person_present"}.issubset(second_fields)


# ---------------------------------------------------------------------------
# Auto-profile generation tests
# ---------------------------------------------------------------------------


def test_auto_discover_profile_with_mock_llm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "contract.md").write_text("TechCorp acquires StartupXYZ for $10M.")
    (corpus / "report.md").write_text("Quarterly revenue report for FY2025.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    llm_response_json = json.dumps(
        {
            "name": "test_auto",
            "description": "Auto-generated test profile.",
            "prompt_description": "Extract key metadata from documents.",
            "fields": [
                {
                    "name": "lx_organizations",
                    "type": "string",
                    "description": "Organization names.",
                    "source": "entities",
                    "source_classes": ["organization", "company"],
                    "mode": "values",
                },
                {
                    "name": "lx_money_count",
                    "type": "integer",
                    "description": "Count of monetary amounts.",
                    "source": "entities",
                    "source_classes": ["money"],
                    "mode": "count",
                },
            ],
        }
    )

    mock_response = MagicMock()
    mock_response.text = llm_response_json

    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response

    with patch(
        "fs_explorer.indexing.metadata._get_genai_client",
        return_value=mock_client_instance,
    ):
        profile = auto_discover_profile(str(corpus))

    # Should pass validation
    normalized = normalize_langextract_profile(profile)
    field_names = {f["name"] for f in normalized["fields"]}
    assert "lx_organizations" in field_names
    assert "lx_money_count" in field_names
    # Runtime fields should have been added automatically
    assert "lx_enabled" in field_names


def test_auto_discover_profile_falls_back_on_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "file.md").write_text("Some content.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")

    with patch(
        "fs_explorer.indexing.metadata._get_genai_client",
        side_effect=RuntimeError("API down"),
    ):
        profile = auto_discover_profile(str(corpus))

    # Should return default profile
    default_names = {
        f["name"] for f in metadata_module._DEFAULT_LANGEXTRACT_PROFILE["fields"]
    }
    got_names = {f["name"] for f in profile["fields"]}
    assert default_names == got_names


def test_auto_discover_profile_falls_back_without_api_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "file.md").write_text("Some content.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    profile = auto_discover_profile(str(corpus))

    default_names = {
        f["name"] for f in metadata_module._DEFAULT_LANGEXTRACT_PROFILE["fields"]
    }
    got_names = {f["name"] for f in profile["fields"]}
    assert default_names == got_names


def test_schema_discovery_uses_auto_profile_when_no_explicit_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "contract.md").write_text("Agreement terms.")

    # Capture what auto_discover_profile returns (mock it)
    auto_profile = {
        "name": "auto_test",
        "description": "Auto-generated.",
        "prompt_description": "Extract metadata.",
        "fields": [
            {
                "name": "lx_enabled",
                "type": "boolean",
                "required": False,
                "description": "Whether langextract succeeded.",
                "source": "runtime",
                "runtime": "enabled",
                "mode": "runtime",
                "source_classes": [],
                "contains_any": [],
            },
            {
                "name": "lx_orgs",
                "type": "string",
                "required": False,
                "description": "Organizations.",
                "source": "entities",
                "source_classes": ["organization"],
                "mode": "values",
                "contains_any": [],
            },
        ],
    }

    monkeypatch.setattr(
        "fs_explorer.indexing.schema.auto_discover_profile",
        lambda folder, **kwargs: auto_profile,
    )

    schema = SchemaDiscovery().discover_from_folder(
        str(corpus),
        with_langextract=True,
        metadata_profile=None,
    )
    field_names = {f["name"] for f in schema["fields"]}
    assert "lx_orgs" in field_names
    assert "lx_enabled" in field_names
    assert schema.get("metadata_profile") == auto_profile


# ---------------------------------------------------------------------------
# Mock embedding helpers for indexing tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeEmbedding:
    values: list[float]


@dataclass
class _FakeEmbedResult:
    embeddings: list[_FakeEmbedding]


class _FakeEmbedModels:
    def embed_content(
        self, *, model: str, contents: list[str], config: dict
    ) -> _FakeEmbedResult:
        dim = config.get("output_dimensionality", 4)
        return _FakeEmbedResult(
            embeddings=[
                _FakeEmbedding(values=[0.1 * i] * dim) for i in range(len(contents))
            ]
        )


class _FakeEmbedClient:
    def __init__(self) -> None:
        self.models = _FakeEmbedModels()


# ---------------------------------------------------------------------------
# Embedding indexing tests
# ---------------------------------------------------------------------------


def test_indexing_pipeline_with_embeddings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "agreement.md").write_text("Purchase price is $45,000,000.")
    (corpus / "report.md").write_text("Risk register summary.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    db_path = str(tmp_path / "index.duckdb")
    storage = DuckDBStorage(db_path, embedding_dim=4)
    provider = EmbeddingProvider(client=_FakeEmbedClient(), dim=4)
    pipeline = IndexingPipeline(storage=storage, embedding_provider=provider)

    result = pipeline.index_folder(str(corpus), discover_schema=True)

    assert result.indexed_files == 2
    assert result.embeddings_written > 0
    assert storage.has_embeddings(corpus_id=result.corpus_id)


def test_indexing_pipeline_without_embeddings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "agreement.md").write_text("Purchase price.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    db_path = str(tmp_path / "index.duckdb")
    storage = DuckDBStorage(db_path)
    pipeline = IndexingPipeline(storage=storage)

    result = pipeline.index_folder(str(corpus), discover_schema=True)

    assert result.embeddings_written == 0
    assert not storage.has_embeddings(corpus_id=result.corpus_id)


def test_embedding_cascade_on_reindex(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    doc = corpus / "agreement.md"
    doc.write_text("Purchase price is $45,000,000.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    db_path = str(tmp_path / "index.duckdb")
    storage = DuckDBStorage(db_path, embedding_dim=4)
    provider = EmbeddingProvider(client=_FakeEmbedClient(), dim=4)
    pipeline = IndexingPipeline(storage=storage, embedding_provider=provider)

    first = pipeline.index_folder(str(corpus), discover_schema=True)
    assert first.embeddings_written > 0

    # Update document and re-index; old embeddings should be replaced
    doc.write_text("Updated purchase price is $50,000,000.")
    second = pipeline.index_folder(str(corpus))
    assert second.embeddings_written > 0
    assert storage.has_embeddings(corpus_id=second.corpus_id)


# ---------------------------------------------------------------------------
# Parallel metadata extraction tests
# ---------------------------------------------------------------------------


def test_extract_metadata_batch_returns_correct_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "agreement.md").write_text("Purchase price is $45,000,000.")
    (corpus / "report.md").write_text("Risk register summary.")
    (corpus / "schedule.md").write_text("Effective Date: January 1, 2026")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    pipeline = IndexingPipeline(storage=storage, max_workers=2)

    root = str(corpus)
    parsed_docs = []
    import os

    for f in sorted(corpus.iterdir()):
        content = f.read_text()
        rel = os.path.relpath(str(f), root)
        parsed_docs.append((str(f), rel, content))

    metadata_map = pipeline._extract_metadata_batch(
        parsed_docs=parsed_docs,
        root_path=root,
        schema_def=None,
        with_langextract=False,
        langextract_profile=None,
    )

    assert len(metadata_map) == 3
    assert "agreement.md" in metadata_map
    assert "report.md" in metadata_map
    assert "schedule.md" in metadata_map

    # Check heuristic metadata
    assert metadata_map["agreement.md"]["mentions_currency"] is True
    assert metadata_map["schedule.md"]["mentions_dates"] is True
    assert metadata_map["report.md"]["document_type"] == "report"


def test_extract_metadata_batch_parallel_is_faster_than_sequential(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    for i in range(6):
        (corpus / f"doc_{i}.md").write_text(f"Document {i} content. Price is ${i}00.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    delay = 0.1
    original_extract = metadata_module.extract_metadata

    def slow_extract(**kwargs):
        time.sleep(delay)
        return original_extract(**kwargs)

    monkeypatch.setattr(pipeline_module, "extract_metadata", slow_extract)

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))
    pipeline = IndexingPipeline(storage=storage, max_workers=6)

    root = str(corpus)
    parsed_docs = []
    import os

    for f in sorted(corpus.iterdir()):
        content = f.read_text()
        rel = os.path.relpath(str(f), root)
        parsed_docs.append((str(f), rel, content))

    start = time.monotonic()
    metadata_map = pipeline._extract_metadata_batch(
        parsed_docs=parsed_docs,
        root_path=root,
        schema_def=None,
        with_langextract=False,
        langextract_profile=None,
    )
    elapsed = time.monotonic() - start

    assert len(metadata_map) == 6
    # 6 docs * 0.1s each = 0.6s sequential; parallel should finish in < 0.4s
    assert elapsed < 0.4, f"Parallel extraction too slow: {elapsed:.2f}s"


def test_parallel_and_sequential_produce_same_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    corpus = tmp_path / "docs"
    corpus.mkdir()
    (corpus / "a.md").write_text("Purchase price is $45,000,000.")
    (corpus / "b.md").write_text("Effective Date: January 1, 2026. Risk summary.")

    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    storage = DuckDBStorage(str(tmp_path / "index.duckdb"))

    root = str(corpus)
    parsed_docs = []
    import os

    for f in sorted(corpus.iterdir()):
        content = f.read_text()
        rel = os.path.relpath(str(f), root)
        parsed_docs.append((str(f), rel, content))

    # Sequential (max_workers=1)
    pipeline_seq = IndexingPipeline(storage=storage, max_workers=1)
    map_seq = pipeline_seq._extract_metadata_batch(
        parsed_docs=parsed_docs,
        root_path=root,
        schema_def=None,
        with_langextract=False,
        langextract_profile=None,
    )

    # Parallel (max_workers=4)
    pipeline_par = IndexingPipeline(storage=storage, max_workers=4)
    map_par = pipeline_par._extract_metadata_batch(
        parsed_docs=parsed_docs,
        root_path=root,
        schema_def=None,
        with_langextract=False,
        langextract_profile=None,
    )

    assert map_seq.keys() == map_par.keys()
    for key in map_seq:
        assert map_seq[key] == map_par[key], f"Mismatch for {key}"
