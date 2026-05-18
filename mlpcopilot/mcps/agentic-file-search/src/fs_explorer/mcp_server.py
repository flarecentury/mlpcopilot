"""Single-tool FastMCP server for Agentic File Search.

The broad implementation with individual file/index tools is preserved in
``mcp_server_full.py``. This module exposes only ``agentic_explore`` to MCP
clients, while runtime configuration stays in environment variables / .env.
"""

from __future__ import annotations

import json
import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP

from .indexing.extensions import get_indexable_extensions
from .index_config import resolve_db_path
from .openai_compatible_file_agent import (
    DEFAULT_AGENT_MAX_STEPS,
    DEFAULT_AGENT_MAX_TOOL_CHARS,
    DEFAULT_AGENT_MODEL,
    DEFAULT_AGENT_TEMPERATURE,
    DEFAULT_AGENT_TIMEOUT_SECONDS,
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PATH,
    DEFAULT_HTTP_PORT,
    OpenAICompatibleFileSearchAgent,
    _tool_index_folder,
)
from .storage import DuckDBStorage


_PACKAGE_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
_CWD_ENV_PATH = Path.cwd() / ".env"
for _env_path in (_PACKAGE_ENV_PATH, _CWD_ENV_PATH):
    if _env_path.exists():
        load_dotenv(_env_path)

mcp = FastMCP("agentic-file-search-mcp")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}.")
    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number.") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}.")
    return value


def _allowed_root() -> Path | None:
    raw = os.getenv("FS_EXPLORER_MCP_ROOT")
    if raw is None or raw.strip() == "":
        return None
    return Path(raw).expanduser().resolve()


def _resolve_root() -> str:
    path = _allowed_root() or Path.cwd().resolve()
    if not path.is_dir():
        raise ValueError(f"No such directory: {path}")
    return str(path)


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _openai_compatible_base_url() -> str:
    base_url = _env_first(
        "FS_EXPLORER_OPENAI_COMPAT_BASE_URL",
        "FS_EXPLORER_AGENT_BASE_URL",
    )
    if base_url is None:
        raise ValueError(
            "FS_EXPLORER_OPENAI_COMPAT_BASE_URL must be set in .env or "
            "environment. Legacy FS_EXPLORER_AGENT_BASE_URL is also accepted."
        )
    return base_url


def _openai_compatible_model() -> str:
    return (
        _env_first("FS_EXPLORER_OPENAI_COMPAT_MODEL", "FS_EXPLORER_AGENT_MODEL")
        or DEFAULT_AGENT_MODEL
    )


def _openai_compatible_api_key() -> str | None:
    return _env_first(
        "FS_EXPLORER_OPENAI_COMPAT_API_KEY",
        "FS_EXPLORER_AGENT_API_KEY",
    )


def _db_path() -> str:
    return resolve_db_path(os.getenv("FS_EXPLORER_DB_PATH") or None)


def _live_supported_files(root: str) -> dict[str, tuple[int, float]]:
    live: dict[str, tuple[int, float]] = {}
    root_path = Path(root).resolve()
    for current_root, _, filenames in os.walk(root_path):
        for filename in filenames:
            path = Path(current_root) / filename
            if path.suffix.lower() not in get_indexable_extensions():
                continue
            relative = str(path.resolve().relative_to(root_path))
            stat = path.stat()
            live[relative] = (int(stat.st_size), float(stat.st_mtime))
    return live


def _index_staleness(root: str, db_path: str) -> dict[str, object]:
    db_file = Path(db_path).expanduser()
    live = _live_supported_files(root)
    if not db_file.exists():
        return {
            "indexed": False,
            "stale": True,
            "reason": "missing_db",
            "live_files": len(live),
            "indexed_files": 0,
            "new_files": sorted(live),
            "modified_files": [],
            "deleted_files": [],
        }

    try:
        storage = DuckDBStorage(db_path, read_only=True, initialize=False)
    except Exception:
        return {
            "indexed": False,
            "stale": True,
            "reason": "unreadable_db",
            "live_files": len(live),
            "indexed_files": 0,
            "new_files": sorted(live),
            "modified_files": [],
            "deleted_files": [],
        }

    try:
        corpus_id = storage.get_corpus_id(root)
        if corpus_id is None:
            return {
                "indexed": False,
                "stale": True,
                "reason": "missing_corpus",
                "live_files": len(live),
                "indexed_files": 0,
                "new_files": sorted(live),
                "modified_files": [],
                "deleted_files": [],
            }
        docs = storage.list_documents(corpus_id=corpus_id, include_deleted=False)
    finally:
        storage.close()

    indexed = {
        str(doc["relative_path"]): (int(doc["file_size"]), float(doc["file_mtime"]))
        for doc in docs
    }
    new_files = sorted(set(live) - set(indexed))
    deleted_files = sorted(set(indexed) - set(live))
    modified_files = sorted(
        path
        for path in set(live) & set(indexed)
        if live[path][0] != indexed[path][0] or abs(live[path][1] - indexed[path][1]) > 1e-6
    )
    stale = bool(new_files or modified_files or deleted_files)
    reason = "filesystem_changed" if stale else "fresh"
    return {
        "indexed": True,
        "stale": stale,
        "reason": reason,
        "live_files": len(live),
        "indexed_files": len(indexed),
        "new_files": new_files,
        "modified_files": modified_files,
        "deleted_files": deleted_files,
    }


def _auto_refresh_index_if_needed(root: str) -> dict[str, object] | None:
    if not _env_bool("FS_EXPLORER_AGENT_USE_INDEX", default=False):
        return None
    if not _env_bool("FS_EXPLORER_MCP_ALLOW_INDEXING", default=False):
        return None
    if not _env_bool("FS_EXPLORER_MCP_AUTO_REFRESH_INDEX", default=True):
        return None

    db_path = _db_path()
    before = _index_staleness(root, db_path)
    if not before.get("stale"):
        return {"checked": True, "refreshed": False, "db_path": db_path, "before": before}

    index_result = json.loads(
        _tool_index_folder(
            {
                "folder": root,
                "db_path": db_path,
                "discover_schema": _env_bool("FS_EXPLORER_MCP_DISCOVER_SCHEMA", default=False),
                "with_embeddings": False,
                "with_metadata": _env_bool("FS_EXPLORER_MCP_ALLOW_METADATA", default=False),
            }
        )
    )
    after = _index_staleness(root, db_path)
    return {
        "checked": True,
        "refreshed": True,
        "db_path": db_path,
        "before": before,
        "index_result": index_result,
        "after": after,
    }


@mcp.tool
async def agentic_explore(task: str) -> str:
    """Answer a focused question by exploring the configured local knowledge root.

    The root is configured by FS_EXPLORER_MCP_ROOT and is intentionally not a
    tool argument. Put file names or relative paths in task, for example
    `read test.txt` or `explain install steps in scripts/setup.sh`. The task
    wording matters: broad inventory questions return overviews, `read <path>`
    style questions return a summary of that file, and more specific follow-ups
    return more specific details. For follow-up questions, preserve both the
    previously discovered target and the user's new intent in task. Do not
    collapse a follow-up like "具体安装步骤?" into just `read /path/file.sh`; ask
    `from /path/file.sh, extract the concrete installation steps, prerequisites,
    config files, service actions, and risks`. You may call this tool repeatedly
    with follow-up tasks against the same configured corpus/path, for example
    after reading a shell script ask about install steps, required privileges,
    external downloads, environment variables, risks, or exact snippets. For
    large files, prefer summaries and short cited excerpts unless the user asks
    for complete verbatim content.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string.")

    resolved_root = _resolve_root()
    index_refresh = _auto_refresh_index_if_needed(resolved_root)
    effective_task = task
    if index_refresh is not None:
        effective_task = (
            f"{task}\n\n"
            "Server-side index freshness check before this query:\n"
            f"```json\n{json.dumps(index_refresh, ensure_ascii=False, indent=2)}\n```"
        )
    agent = OpenAICompatibleFileSearchAgent(
        task=effective_task,
        folder=resolved_root,
        base_url=_openai_compatible_base_url(),
        model=_openai_compatible_model(),
        db_path=_db_path(),
        use_index=_env_bool("FS_EXPLORER_AGENT_USE_INDEX", default=False),
        allow_indexing=_env_bool("FS_EXPLORER_MCP_ALLOW_INDEXING", default=False),
        allow_embeddings=_env_bool("FS_EXPLORER_MCP_ALLOW_EMBEDDINGS", default=False),
        allow_metadata=_env_bool("FS_EXPLORER_MCP_ALLOW_METADATA", default=False),
        max_steps=_env_int(
            "FS_EXPLORER_AGENT_MAX_STEPS",
            DEFAULT_AGENT_MAX_STEPS,
            maximum=30,
        ),
        max_tool_chars=_env_int(
            "FS_EXPLORER_AGENT_MAX_TOOL_CHARS",
            DEFAULT_AGENT_MAX_TOOL_CHARS,
            maximum=200000,
        ),
        temperature=_env_float(
            "FS_EXPLORER_AGENT_TEMPERATURE",
            DEFAULT_AGENT_TEMPERATURE,
            minimum=0,
            maximum=2,
        ),
        timeout=_env_int(
            "FS_EXPLORER_AGENT_TIMEOUT",
            DEFAULT_AGENT_TIMEOUT_SECONDS,
            maximum=600,
        ),
        api_key=_openai_compatible_api_key(),
    )
    return agent.run()


def serve_stdio() -> None:
    """Run the MCP server over FastMCP stdio transport."""
    mcp.run(transport="stdio", show_banner=False)


def serve_http(
    *,
    host: str = DEFAULT_HTTP_HOST,
    port: int = DEFAULT_HTTP_PORT,
    endpoint: str = DEFAULT_HTTP_PATH,
) -> None:
    """Run the MCP server with FastMCP Streamable HTTP transport."""
    mcp.run(
        transport="http",
        host=host,
        port=port,
        path=endpoint,
        show_banner=False,
    )


def _parse_args(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(description="Agentic File Search MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http"),
        default=os.getenv("FS_EXPLORER_MCP_TRANSPORT", "stdio"),
        help="MCP transport to serve. Defaults to stdio.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("FS_EXPLORER_MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
        help="HTTP host for Streamable HTTP mode.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("FS_EXPLORER_MCP_HTTP_PORT", DEFAULT_HTTP_PORT)),
        help="HTTP port for Streamable HTTP mode.",
    )
    parser.add_argument(
        "--path",
        default=os.getenv("FS_EXPLORER_MCP_HTTP_PATH", DEFAULT_HTTP_PATH),
        help="MCP HTTP endpoint path.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    try:
        if args.transport == "stdio":
            serve_stdio()
            return
        serve_http(host=args.host, port=args.port, endpoint=args.path)
    except KeyboardInterrupt:
        return


def main_http() -> None:
    args = _parse_args()
    try:
        serve_http(host=args.host, port=args.port, endpoint=args.path)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
