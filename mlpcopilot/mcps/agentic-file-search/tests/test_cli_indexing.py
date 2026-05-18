"""CLI tests for indexing and schema commands."""

from pathlib import Path

import fs_explorer.indexing.pipeline as pipeline_module
import fs_explorer.main as main_module
from fs_explorer.storage import DuckDBStorage
from typer.testing import CliRunner


def test_root_task_mode_remains_compatible(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}

    async def fake_run_workflow(
        task: str,
        folder: str = ".",
        *,
        use_index: bool = False,
        db_path: str | None = None,
    ) -> None:
        called["task"] = task
        called["folder"] = folder
        called["use_index"] = use_index
        called["db_path"] = db_path

    monkeypatch.setattr(main_module, "run_workflow", fake_run_workflow)

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        ["--task", "who is the CTO?", "--folder", str(tmp_path)],
    )

    assert result.exit_code == 0
    assert called["task"] == "who is the CTO?"
    assert called["folder"] == str(tmp_path)
    assert called["use_index"] is False


def test_query_command_enables_index_mode(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}

    async def fake_run_workflow(
        task: str,
        folder: str = ".",
        *,
        use_index: bool = False,
        db_path: str | None = None,
    ) -> None:
        called["task"] = task
        called["folder"] = folder
        called["use_index"] = use_index
        called["db_path"] = db_path

    monkeypatch.setattr(main_module, "run_workflow", fake_run_workflow)

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        [
            "query",
            "--task",
            "purchase price?",
            "--folder",
            str(tmp_path),
            "--db-path",
            "tmp.duckdb",
        ],
    )

    assert result.exit_code == 0
    assert called["task"] == "purchase price?"
    assert called["folder"] == str(tmp_path)
    assert called["use_index"] is True
    assert called["db_path"] == "tmp.duckdb"


def test_index_and_schema_commands(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "agreement.md").write_text("Purchase price is $10.")
    (corpus / "risk_report.md").write_text("Risk summary here.")

    # Replace Docling path with plain text read for this unit test.
    monkeypatch.setattr(
        pipeline_module,
        "parse_file",
        lambda file_path: Path(file_path).read_text(),
    )

    db_path = tmp_path / "index.duckdb"
    runner = CliRunner()

    index_result = runner.invoke(
        main_module.app,
        ["index", str(corpus), "--db-path", str(db_path), "--discover-schema"],
    )
    assert index_result.exit_code == 0
    assert "Index Complete" in index_result.stdout

    show_result = runner.invoke(
        main_module.app,
        ["schema", "show", str(corpus), "--db-path", str(db_path)],
    )
    assert show_result.exit_code == 0
    assert "auto_corpus" in show_result.stdout


def test_index_command_with_metadata_forces_schema_discovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    called: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, storage, embedding_provider=None) -> None:  # noqa: ANN001
            called["storage_type"] = type(storage).__name__

        def index_folder(
            self,
            folder: str,
            *,
            discover_schema: bool = False,
            schema_name: str | None = None,
            with_metadata: bool = False,
            metadata_profile: dict | None = None,
        ):
            called["folder"] = folder
            called["discover_schema"] = discover_schema
            called["schema_name"] = schema_name
            called["with_metadata"] = with_metadata
            called["metadata_profile"] = metadata_profile
            return pipeline_module.IndexingResult(
                corpus_id="corpus_123",
                indexed_files=1,
                skipped_files=0,
                deleted_files=0,
                chunks_written=1,
                active_documents=1,
                schema_used="auto_corpus",
            )

    monkeypatch.setattr(main_module, "IndexingPipeline", FakePipeline)

    db_path = tmp_path / "index.duckdb"
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        ["index", str(corpus), "--db-path", str(db_path), "--with-metadata"],
    )

    assert result.exit_code == 0
    assert called["with_metadata"] is True
    assert called["discover_schema"] is True
    assert called["metadata_profile"] is None


def test_index_command_with_metadata_profile_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    called: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, storage, embedding_provider=None) -> None:  # noqa: ANN001
            called["storage_type"] = type(storage).__name__

        def index_folder(
            self,
            folder: str,
            *,
            discover_schema: bool = False,
            schema_name: str | None = None,
            with_metadata: bool = False,
            metadata_profile: dict | None = None,
        ):
            called["folder"] = folder
            called["discover_schema"] = discover_schema
            called["schema_name"] = schema_name
            called["with_metadata"] = with_metadata
            called["metadata_profile"] = metadata_profile
            return pipeline_module.IndexingResult(
                corpus_id="corpus_123",
                indexed_files=1,
                skipped_files=0,
                deleted_files=0,
                chunks_written=1,
                active_documents=1,
                schema_used="auto_corpus",
            )

    monkeypatch.setattr(main_module, "IndexingPipeline", FakePipeline)

    db_path = tmp_path / "index.duckdb"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    metadata_profile_path = tmp_path / "profile.json"
    metadata_profile_path.write_text(
        (
            "{"
            '"prompt_description": "Extract organizations.", '
            '"fields": ['
            '{"name": "org_names", "type": "string", "source_class": "organization"}'
            "]"
            "}"
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        [
            "index",
            str(corpus),
            "--db-path",
            str(db_path),
            "--metadata-profile",
            str(metadata_profile_path),
        ],
    )

    assert result.exit_code == 0
    assert called["with_metadata"] is True
    assert called["discover_schema"] is True
    assert isinstance(called["metadata_profile"], dict)
    assert called["metadata_profile"]["fields"][0]["name"] == "org_names"


def test_index_command_with_embeddings_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """--with-embeddings creates an EmbeddingProvider and passes it to the pipeline."""
    calls: dict[str, object] = {}

    class FakePipeline:
        def __init__(self, storage, embedding_provider=None) -> None:  # noqa: ANN001
            calls["has_embedding_provider"] = embedding_provider is not None

        def index_folder(self, folder, **kwargs):  # noqa: ANN001, ANN003
            return pipeline_module.IndexingResult(
                corpus_id="corpus_123",
                indexed_files=1,
                skipped_files=0,
                deleted_files=0,
                chunks_written=1,
                active_documents=1,
                schema_used=None,
                embeddings_written=5,
            )

    class FakeEmbeddingProvider:
        def __init__(self, **kwargs):  # noqa: ANN003
            pass

    monkeypatch.setattr(main_module, "IndexingPipeline", FakePipeline)
    monkeypatch.setattr(main_module, "EmbeddingProvider", FakeEmbeddingProvider)

    db_path = tmp_path / "index.duckdb"
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        ["index", str(corpus), "--db-path", str(db_path), "--with-embeddings"],
    )

    assert result.exit_code == 0
    assert calls["has_embedding_provider"] is True
    assert "Embeddings Written" in result.stdout


def test_auto_index_env_var_enables_use_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """FS_EXPLORER_AUTO_INDEX=1 auto-enables --use-index when index exists."""
    called: dict[str, object] = {}

    async def fake_run_workflow(
        task: str,
        folder: str = ".",
        *,
        use_index: bool = False,
        db_path: str | None = None,
    ) -> None:
        called["use_index"] = use_index

    monkeypatch.setattr(main_module, "run_workflow", fake_run_workflow)
    monkeypatch.setenv("FS_EXPLORER_AUTO_INDEX", "1")

    # Create a real DuckDB with a corpus entry so auto-index detection works.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    db_path = tmp_path / "index.duckdb"
    storage = DuckDBStorage(str(db_path))
    storage.get_or_create_corpus(str(corpus.resolve()))
    storage.close()

    monkeypatch.setenv("FS_EXPLORER_DB_PATH", str(db_path))

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        ["--task", "test question", "--folder", str(corpus)],
    )

    assert result.exit_code == 0
    assert called["use_index"] is True


def test_auto_index_env_var_silent_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """FS_EXPLORER_AUTO_INDEX=1 gracefully falls back when no index exists."""
    called: dict[str, object] = {}

    async def fake_run_workflow(
        task: str,
        folder: str = ".",
        *,
        use_index: bool = False,
        db_path: str | None = None,
    ) -> None:
        called["use_index"] = use_index

    monkeypatch.setattr(main_module, "run_workflow", fake_run_workflow)
    monkeypatch.setenv("FS_EXPLORER_AUTO_INDEX", "1")

    corpus = tmp_path / "empty_corpus"
    corpus.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main_module.app,
        ["--task", "test question", "--folder", str(corpus)],
    )

    assert result.exit_code == 0
    assert called["use_index"] is False
