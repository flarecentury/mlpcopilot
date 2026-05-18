"""FastMCP server for FsExplorer tools and the built-in OpenAI-compatible file agent."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from argparse import ArgumentParser, Namespace
from collections.abc import Callable
from importlib import metadata
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

from .embeddings import EmbeddingProvider
from .fs import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_PREVIEW_CHARS,
    DEFAULT_SCAN_PREVIEW_CHARS,
    describe_dir_content,
    glob_paths,
    grep_file_content,
    parse_file as fs_parse_file,
    preview_file as fs_preview_file,
    read_file,
    scan_folder as fs_scan_folder,
)
from .index_config import resolve_db_path
from .indexing import IndexingPipeline
from .search import (
    IndexedQueryEngine,
    MetadataFilterParseError,
    supported_filter_syntax,
)
from .storage import DuckDBStorage


_PACKAGE_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
_CWD_ENV_PATH = Path.cwd() / ".env"
for _env_path in (_PACKAGE_ENV_PATH, _CWD_ENV_PATH):
    if _env_path.exists():
        load_dotenv(_env_path)

mcp = FastMCP("fs-explorer")

ToolHandler = Callable[[dict[str, Any]], Any]

DEFAULT_AGENT_MODEL = "local-model"
DEFAULT_AGENT_MAX_STEPS = 12
DEFAULT_AGENT_TIMEOUT_SECONDS = 120
DEFAULT_AGENT_TEMPERATURE = 0.1
DEFAULT_AGENT_MAX_TOOL_CHARS = 30000
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_HTTP_PATH = "/mcp"

AGENT_TOOL_NAMES = frozenset(
    {
        "describe_directory",
        "scan_folder",
        "preview_file",
        "parse_file",
        "read",
        "grep",
        "glob",
        "index_status",
        "search_index",
        "list_indexed_documents",
        "get_indexed_document",
    }
)


def _package_version() -> str:
    try:
        return metadata.version("fs-explorer")
    except metadata.PackageNotFoundError:
        return "0.1.0"


def _allowed_root() -> Path | None:
    raw = os.getenv("FS_EXPLORER_MCP_ROOT")
    if raw is None or raw.strip() == "":
        return None
    return Path(raw).expanduser().resolve()


def _resolve_user_path(raw_path: str, *, must_be: str) -> str:
    path = Path(raw_path).expanduser().resolve()
    allowed = _allowed_root()
    if allowed is not None and not _is_relative_to(path, allowed):
        raise ValueError(
            f"Path {path} is outside FS_EXPLORER_MCP_ROOT ({allowed})."
        )
    if must_be == "file" and not path.is_file():
        raise ValueError(f"No such file: {path}")
    if must_be == "directory" and not path.is_dir():
        raise ValueError(f"No such directory: {path}")
    return str(path)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _required_str(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"`{key}` must be a non-empty string.")
    return value


def _optional_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"`{key}` must be a string when provided.")
    return value


def _bool_arg(args: dict[str, Any], key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"`{key}` must be a boolean.")
    return value


def _int_arg(
    args: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    value = args.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"`{key}` must be an integer.")
    if value < minimum:
        raise ValueError(f"`{key}` must be >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"`{key}` must be <= {maximum}.")
    return value


def _metadata_profile_arg(args: dict[str, Any]) -> dict[str, Any] | None:
    value = args.get("metadata_profile")
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("`metadata_profile` must be an object or JSON object string.")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _float_arg(
    args: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = args.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"`{key}` must be a number.")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"`{key}` must be >= {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"`{key}` must be <= {maximum}.")
    return result


def _agent_base_url(args: dict[str, Any]) -> str:
    base_url = (
        _optional_str(args, "base_url")
        or os.getenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL")
        or os.getenv("FS_EXPLORER_AGENT_BASE_URL")
    )
    if base_url is None or base_url.strip() == "":
        raise ValueError(
            "`base_url` is required unless FS_EXPLORER_OPENAI_COMPAT_BASE_URL or legacy FS_EXPLORER_OPENAI_COMPAT_BASE_URL or legacy FS_EXPLORER_AGENT_BASE_URL is set."
        )
    return base_url.strip()


def _completion_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    return f"{trimmed}/v1/chat/completions"


def _post_chat_completion(
    *,
    url: str,
    payload: dict[str, Any],
    api_key: str | None,
    timeout: int,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _chat_completion(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: int,
    api_key: str | None = None,
) -> str:
    url = _completion_url(base_url)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    try:
        data = _post_chat_completion(
            url=url,
            payload=payload,
            api_key=api_key,
            timeout=timeout,
        )
    except urllib.error.HTTPError as exc:
        # Some llama.cpp/OpenAI-compatible servers do not implement
        # response_format. Retry once with prompt-only JSON enforcement.
        if exc.code != 400:
            raise
        payload.pop("response_format", None)
        data = _post_chat_completion(
            url=url,
            payload=payload,
            api_key=api_key,
            timeout=timeout,
        )

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected chat completion response: {data}") from exc
    if not isinstance(content, str):
        raise ValueError(f"Chat completion content is not text: {content!r}")
    return content


def _strip_model_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_model_thinking(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        parsed = json.loads(fenced.group(1))
        if isinstance(parsed, dict):
            return parsed

    start = cleaned.find("{")
    if start == -1:
        raise ValueError(f"LLM response did not contain a JSON object: {text}")

    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(cleaned)):
        char = cleaned[pos]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                parsed = json.loads(cleaned[start : pos + 1])
                if isinstance(parsed, dict):
                    return parsed
                break

    raise ValueError(f"Could not parse JSON object from LLM response: {text}")


def _truncate_tool_result(result: str, max_chars: int) -> str:
    if len(result) <= max_chars:
        return result
    return (
        result[:max_chars]
        + f"\n\n[Tool result truncated to {max_chars:,} characters.]"
    )


def _agent_tool_descriptions(allow_indexing: bool) -> str:
    allowed = set(AGENT_TOOL_NAMES)
    if allow_indexing:
        allowed.add("index_folder")
    lines = []
    for tool in TOOLS:
        name = tool["name"]
        if name not in allowed:
            continue
        schema = tool["inputSchema"]
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        params = ", ".join(
            f"{key}{'*' if key in required else ''}" for key in properties
        )
        lines.append(f"- {name}({params}): {tool.get('description', '')}")
    return "\n".join(lines)


class OpenAICompatibleFileSearchAgent:
    """Small ReAct-style file search agent backed by an OpenAI-compatible LLM."""

    def __init__(
        self,
        *,
        task: str,
        folder: str,
        base_url: str,
        model: str,
        db_path: str | None,
        use_index: bool,
        allow_indexing: bool,
        allow_embeddings: bool,
        allow_metadata: bool,
        max_steps: int,
        max_tool_chars: int,
        temperature: float,
        timeout: int,
        api_key: str | None,
    ) -> None:
        self.task = task
        self.folder = folder
        self.base_url = base_url
        self.model = model
        self.db_path = db_path
        self.use_index = use_index
        self.allow_indexing = allow_indexing
        self.allow_embeddings = allow_embeddings
        self.allow_metadata = allow_metadata
        self.max_steps = max_steps
        self.max_tool_chars = max_tool_chars
        self.temperature = temperature
        self.timeout = timeout
        self.api_key = api_key
        self.trace: list[dict[str, Any]] = []

    def run(self) -> str:
        messages = self._initial_messages()
        for step in range(1, self.max_steps + 1):
            raw_response = _chat_completion(
                base_url=self.base_url,
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                timeout=self.timeout,
                api_key=self.api_key,
            )
            try:
                action = _extract_json_object(raw_response)
            except ValueError as exc:
                messages.append({"role": "assistant", "content": raw_response})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your response was not valid JSON. Reply with exactly "
                            "one JSON object matching the required schema. "
                            f"Parser error: {exc}"
                        ),
                    }
                )
                continue

            action_type = str(action.get("action", "")).lower()
            if action_type == "final":
                answer = action.get("answer") or action.get("final_answer")
                if not isinstance(answer, str) or not answer.strip():
                    answer = raw_response
                return self._format_final(answer)

            if action_type != "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid action. Use either "
                            '{"action":"tool",...} or {"action":"final",...}.'
                        ),
                    }
                )
                continue

            tool_name = action.get("tool_name") or action.get("tool")
            arguments = action.get("arguments") or action.get("tool_input") or {}
            reason = action.get("reason", "")
            if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid tool action: tool_name and arguments "
                            "are required."
                        ),
                    }
                )
                continue

            result, is_error = self._execute_tool(tool_name, arguments)
            self.trace.append(
                {
                    "step": step,
                    "tool": tool_name,
                    "arguments": arguments,
                    "reason": reason,
                    "is_error": is_error,
                }
            )
            tool_result = _truncate_tool_result(result, self.max_tool_chars)
            messages.append({"role": "assistant", "content": _json_dumps(action)})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Tool result for {tool_name} "
                        f"(is_error={str(is_error).lower()}):\n\n{tool_result}\n\n"
                        "Choose the next tool or return a final answer."
                    ),
                }
            )

        return self._format_final(
            "Reached the maximum number of agent steps before producing a final answer."
        )

    def _initial_messages(self) -> list[dict[str, str]]:
        directory_description = describe_dir_content(self.folder)
        index_status = ""
        if self.use_index:
            index_args: dict[str, Any] = {"folder": self.folder}
            if self.db_path:
                index_args["db_path"] = self.db_path
            index_status = _tool_index_status(index_args)

        system_prompt = (
            "You are FsExplorer, an agent running inside an MCP server. "
            "Your job is to answer questions about local files by repeatedly "
            "choosing tools, inspecting their results, and then producing a "
            "cited final answer.\n\n"
            "Return exactly one JSON object on every turn. Do not use markdown "
            "outside the JSON object.\n\n"
            "Tool action schema:\n"
            '{"action":"tool","tool_name":"scan_folder","arguments":{},'
            '"reason":"why this tool is needed"}\n\n'
            "Final answer schema:\n"
            '{"action":"final","answer":"direct answer with citations and a '
            'Sources section"}\n\n'
            "Citation rules: cite factual claims with the actual filename and "
            "section/page when available. Prefer scan_folder or search_index "
            "first, then parse_file or get_indexed_document for detailed evidence. "
            "Use absolute paths from tool results when reading files.\n\n"
            f"Available tools:\n{_agent_tool_descriptions(self.allow_indexing)}"
        )

        user_prompt = (
            f"Task: {self.task}\n\n"
            f"Root folder: {self.folder}\n\n"
            f"Directory listing:\n```text\n{directory_description}\n```"
        )
        if self.use_index:
            user_prompt += f"\n\nIndex status:\n```json\n{index_status}\n```"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> tuple[str, bool]:
        allowed = set(AGENT_TOOL_NAMES)
        if self.allow_indexing:
            allowed.add("index_folder")
        if tool_name not in allowed:
            return f"Tool {tool_name!r} is not available to the agent.", True

        prepared = dict(arguments)
        self._apply_tool_defaults(tool_name, prepared)
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return f"Unknown tool: {tool_name}", True
        try:
            result = handler(prepared)
        except Exception as exc:
            return f"Error: {exc}", True
        return str(result), False

    def _apply_tool_defaults(self, tool_name: str, arguments: dict[str, Any]) -> None:
        if tool_name in {"describe_directory", "scan_folder", "glob"}:
            arguments.setdefault("directory", self.folder)
        if tool_name == "index_status":
            arguments.setdefault("folder", self.folder)
        if tool_name == "index_folder":
            arguments.setdefault("folder", self.folder)
            if not self.allow_embeddings:
                arguments["with_embeddings"] = False
            if not self.allow_metadata:
                arguments["with_metadata"] = False
                arguments.pop("metadata_profile", None)
        if tool_name in {"search_index", "list_indexed_documents"}:
            arguments.setdefault("corpus_folder", self.folder)
        if tool_name in {
            "index_folder",
            "index_status",
            "search_index",
            "list_indexed_documents",
            "get_indexed_document",
        } and self.db_path:
            arguments.setdefault("db_path", self.db_path)

    def _format_final(self, answer: str) -> str:
        payload = {
            "answer": answer,
            "agent": {
                "model": self.model,
                "base_url": self.base_url,
                "steps": len(self.trace),
                "use_index": self.use_index,
            },
            "trace": self.trace,
        }
        return _json_dumps(payload)


def _tool_describe_directory(args: dict[str, Any]) -> str:
    directory = _resolve_user_path(
        _required_str(args, "directory"),
        must_be="directory",
    )
    return describe_dir_content(directory)


def _tool_scan_folder(args: dict[str, Any]) -> str:
    directory = _resolve_user_path(
        _required_str(args, "directory"),
        must_be="directory",
    )
    max_workers = _int_arg(args, "max_workers", DEFAULT_MAX_WORKERS, maximum=16)
    preview_chars = _int_arg(args, "preview_chars", DEFAULT_SCAN_PREVIEW_CHARS)
    return fs_scan_folder(
        directory=directory,
        max_workers=max_workers,
        preview_chars=preview_chars,
    )


def _tool_preview_file(args: dict[str, Any]) -> str:
    file_path = _resolve_user_path(_required_str(args, "file_path"), must_be="file")
    max_chars = _int_arg(args, "max_chars", DEFAULT_PREVIEW_CHARS)
    return fs_preview_file(file_path=file_path, max_chars=max_chars)


def _tool_parse_file(args: dict[str, Any]) -> str:
    file_path = _resolve_user_path(_required_str(args, "file_path"), must_be="file")
    return fs_parse_file(file_path=file_path)


def _tool_read(args: dict[str, Any]) -> str:
    file_path = _resolve_user_path(_required_str(args, "file_path"), must_be="file")
    return read_file(file_path=file_path)


def _tool_grep(args: dict[str, Any]) -> str:
    file_path = _resolve_user_path(_required_str(args, "file_path"), must_be="file")
    pattern = _required_str(args, "pattern")
    return grep_file_content(file_path=file_path, pattern=pattern)


def _tool_glob(args: dict[str, Any]) -> str:
    directory = _resolve_user_path(
        _required_str(args, "directory"),
        must_be="directory",
    )
    pattern = _required_str(args, "pattern")
    return glob_paths(directory=directory, pattern=pattern)


def _tool_index_folder(args: dict[str, Any]) -> str:
    folder = _resolve_user_path(_required_str(args, "folder"), must_be="directory")
    db_path = resolve_db_path(_optional_str(args, "db_path"))
    with_embeddings = _bool_arg(args, "with_embeddings")
    embedding_provider: EmbeddingProvider | None = None
    if with_embeddings:
        embedding_provider = EmbeddingProvider()

    storage = DuckDBStorage(db_path)
    try:
        pipeline = IndexingPipeline(
            storage=storage,
            embedding_provider=embedding_provider,
        )
        with_metadata = _bool_arg(args, "with_metadata")
        metadata_profile = _metadata_profile_arg(args)
        result = pipeline.index_folder(
            folder,
            discover_schema=_bool_arg(args, "discover_schema"),
            schema_name=_optional_str(args, "schema_name"),
            with_metadata=with_metadata or metadata_profile is not None,
            metadata_profile=metadata_profile,
        )
    finally:
        storage.close()

    return _json_dumps(
        {
            "db_path": db_path,
            "folder": folder,
            "corpus_id": result.corpus_id,
            "indexed_files": result.indexed_files,
            "skipped_files": result.skipped_files,
            "deleted_files": result.deleted_files,
            "chunks_written": result.chunks_written,
            "active_documents": result.active_documents,
            "schema_used": result.schema_used,
            "embeddings_written": result.embeddings_written,
            "metadata_mode": (
                "langextract"
                if with_metadata or metadata_profile is not None
                else "heuristic"
            ),
        }
    )


def _tool_index_status(args: dict[str, Any]) -> str:
    folder = _resolve_user_path(_required_str(args, "folder"), must_be="directory")
    db_path = resolve_db_path(_optional_str(args, "db_path"))
    db_file = Path(db_path)
    if not db_file.exists():
        return _json_dumps({"indexed": False, "folder": folder, "db_path": db_path})

    try:
        storage = DuckDBStorage(db_path, read_only=True, initialize=False)
    except Exception:
        return _json_dumps({"indexed": False, "folder": folder, "db_path": db_path})

    try:
        corpus_id = storage.get_corpus_id(folder)
        if corpus_id is None:
            return _json_dumps({"indexed": False, "folder": folder, "db_path": db_path})

        documents = storage.list_documents(corpus_id=corpus_id, include_deleted=False)
        active_schema = storage.get_active_schema(corpus_id=corpus_id)
        schema_fields: list[str] = []
        schema_name: str | None = None
        has_metadata = False
        if active_schema is not None:
            schema_name = active_schema.name
            has_metadata = active_schema.schema_def.get("metadata_profile") is not None
            fields = active_schema.schema_def.get("fields")
            if isinstance(fields, list):
                schema_fields = [
                    str(field["name"])
                    for field in fields
                    if isinstance(field, dict) and isinstance(field.get("name"), str)
                ]

        return _json_dumps(
            {
                "indexed": True,
                "folder": folder,
                "db_path": db_path,
                "corpus_id": corpus_id,
                "document_count": len(documents),
                "schema_name": schema_name,
                "has_metadata": has_metadata,
                "has_embeddings": storage.has_embeddings(corpus_id=corpus_id),
                "schema_fields": schema_fields,
            }
        )
    finally:
        storage.close()


def _tool_search_index(args: dict[str, Any]) -> str:
    folder = _resolve_user_path(
        _required_str(args, "corpus_folder"),
        must_be="directory",
    )
    query = _required_str(args, "query")
    filters = _optional_str(args, "filters")
    limit = _int_arg(args, "limit", 5, maximum=50)
    db_path = resolve_db_path(_optional_str(args, "db_path"))

    storage = DuckDBStorage(db_path, read_only=True, initialize=False)
    try:
        corpus_id = storage.get_corpus_id(folder)
        if corpus_id is None:
            raise ValueError(f"No index found for folder: {folder}")

        embedding_provider: EmbeddingProvider | None = None
        if storage.has_embeddings(corpus_id=corpus_id):
            try:
                embedding_provider = EmbeddingProvider()
            except ValueError:
                embedding_provider = None

        engine = IndexedQueryEngine(storage, embedding_provider=embedding_provider)
        try:
            hits = engine.search(
                corpus_id=corpus_id,
                query=query,
                filters=filters,
                limit=limit,
            )
        except MetadataFilterParseError as exc:
            raise ValueError(f"{exc}\n{supported_filter_syntax()}") from exc

        return _json_dumps(
            {
                "corpus_folder": folder,
                "db_path": db_path,
                "query": query,
                "hits": [
                    {
                        "doc_id": hit.doc_id,
                        "relative_path": hit.relative_path,
                        "absolute_path": hit.absolute_path,
                        "position": hit.position,
                        "text": hit.text,
                        "semantic_score": hit.semantic_score,
                        "metadata_score": hit.metadata_score,
                        "score": hit.score,
                        "matched_by": hit.matched_by,
                    }
                    for hit in hits
                ],
            }
        )
    finally:
        storage.close()


def _tool_list_indexed_documents(args: dict[str, Any]) -> str:
    folder = _resolve_user_path(
        _required_str(args, "corpus_folder"),
        must_be="directory",
    )
    db_path = resolve_db_path(_optional_str(args, "db_path"))
    storage = DuckDBStorage(db_path, read_only=True, initialize=False)
    try:
        corpus_id = storage.get_corpus_id(folder)
        if corpus_id is None:
            raise ValueError(f"No index found for folder: {folder}")
        documents = storage.list_documents(corpus_id=corpus_id, include_deleted=False)
        return _json_dumps(
            {
                "corpus_folder": folder,
                "db_path": db_path,
                "documents": documents,
            }
        )
    finally:
        storage.close()


def _tool_get_indexed_document(args: dict[str, Any]) -> str:
    doc_id = _required_str(args, "doc_id")
    db_path = resolve_db_path(_optional_str(args, "db_path"))
    storage = DuckDBStorage(db_path, read_only=True, initialize=False)
    try:
        document = storage.get_document(doc_id=doc_id)
        if document is None:
            raise ValueError(f"No indexed document found for doc_id={doc_id!r}")
        if document["is_deleted"]:
            raise ValueError(f"Document {doc_id!r} is marked deleted in the index.")
        path = Path(str(document["absolute_path"])).resolve()
        allowed = _allowed_root()
        if allowed is not None and not _is_relative_to(path, allowed):
            raise ValueError(
                f"Indexed document path {path} is outside FS_EXPLORER_MCP_ROOT."
            )
        return _json_dumps(
            {
                "doc_id": doc_id,
                "relative_path": document["relative_path"],
                "absolute_path": document["absolute_path"],
                "content": document["content"],
                "metadata": json.loads(str(document.get("metadata_json") or "{}")),
            }
        )
    finally:
        storage.close()


def _tool_explore(args: dict[str, Any]) -> str:
    task = _required_str(args, "task")
    folder_arg = args.get("folder", ".")
    if not isinstance(folder_arg, str):
        raise ValueError("`folder` must be a string when provided.")
    folder = _resolve_user_path(
        folder_arg,
        must_be="directory",
    )
    db_path = _optional_str(args, "db_path")
    model = (
        _optional_str(args, "model")
        or os.getenv("FS_EXPLORER_OPENAI_COMPAT_MODEL")
        or os.getenv("FS_EXPLORER_AGENT_MODEL")
        or DEFAULT_AGENT_MODEL
    )
    api_key = (
        _optional_str(args, "api_key")
        or os.getenv("FS_EXPLORER_OPENAI_COMPAT_API_KEY")
        or os.getenv("FS_EXPLORER_AGENT_API_KEY")
    )
    agent = OpenAICompatibleFileSearchAgent(
        task=task,
        folder=folder,
        base_url=_agent_base_url(args),
        model=model,
        db_path=db_path,
        use_index=_bool_arg(args, "use_index"),
        allow_indexing=_bool_arg(args, "allow_indexing"),
        allow_embeddings=_bool_arg(args, "allow_embeddings"),
        allow_metadata=_bool_arg(args, "allow_metadata"),
        max_steps=_int_arg(
            args,
            "max_steps",
            int(os.getenv("FS_EXPLORER_AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS)),
            maximum=30,
        ),
        max_tool_chars=_int_arg(
            args,
            "max_tool_chars",
            int(
                os.getenv(
                    "FS_EXPLORER_AGENT_MAX_TOOL_CHARS",
                    DEFAULT_AGENT_MAX_TOOL_CHARS,
                )
            ),
            maximum=200000,
        ),
        temperature=_float_arg(
            args,
            "temperature",
            float(
                os.getenv(
                    "FS_EXPLORER_AGENT_TEMPERATURE",
                    DEFAULT_AGENT_TEMPERATURE,
                )
            ),
            minimum=0,
            maximum=2,
        ),
        timeout=_int_arg(
            args,
            "timeout",
            int(
                os.getenv(
                    "FS_EXPLORER_AGENT_TIMEOUT",
                    DEFAULT_AGENT_TIMEOUT_SECONDS,
                )
            ),
            maximum=600,
        ),
        api_key=api_key,
    )
    return agent.run()


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "explore": _tool_explore,
    "describe_directory": _tool_describe_directory,
    "scan_folder": _tool_scan_folder,
    "preview_file": _tool_preview_file,
    "parse_file": _tool_parse_file,
    "read": _tool_read,
    "grep": _tool_grep,
    "glob": _tool_glob,
    "index_folder": _tool_index_folder,
    "index_status": _tool_index_status,
    "search_index": _tool_search_index,
    "list_indexed_documents": _tool_list_indexed_documents,
    "get_indexed_document": _tool_get_indexed_document,
}


def _clean_args(**kwargs: Any) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if value is not None}


@mcp.tool
def explore(
    task: str,
    folder: str = ".",
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    use_index: bool = False,
    db_path: str | None = None,
    allow_indexing: bool = False,
    allow_embeddings: bool = False,
    allow_metadata: bool = False,
    max_steps: int = DEFAULT_AGENT_MAX_STEPS,
    max_tool_chars: int = DEFAULT_AGENT_MAX_TOOL_CHARS,
    temperature: float = DEFAULT_AGENT_TEMPERATURE,
    timeout: int = DEFAULT_AGENT_TIMEOUT_SECONDS,
) -> str:
    """Run the built-in OpenAI-compatible file exploration agent."""
    return _tool_explore(
        _clean_args(
            task=task,
            folder=folder,
            base_url=base_url,
            model=model,
            api_key=api_key,
            use_index=use_index,
            db_path=db_path,
            allow_indexing=allow_indexing,
            allow_embeddings=allow_embeddings,
            allow_metadata=allow_metadata,
            max_steps=max_steps,
            max_tool_chars=max_tool_chars,
            temperature=temperature,
            timeout=timeout,
        )
    )


@mcp.tool
def describe_directory(directory: str) -> str:
    """List files and subdirectories in a local directory."""
    return _tool_describe_directory({"directory": directory})


@mcp.tool
def scan_folder(
    directory: str,
    max_workers: int = DEFAULT_MAX_WORKERS,
    preview_chars: int = DEFAULT_SCAN_PREVIEW_CHARS,
) -> str:
    """Parse supported documents in a folder in parallel and return previews."""
    return _tool_scan_folder(
        {
            "directory": directory,
            "max_workers": max_workers,
            "preview_chars": preview_chars,
        }
    )


@mcp.tool
def preview_file(file_path: str, max_chars: int = DEFAULT_PREVIEW_CHARS) -> str:
    """Return the first part of a supported document as markdown."""
    return _tool_preview_file({"file_path": file_path, "max_chars": max_chars})


@mcp.tool
def parse_file(file_path: str) -> str:
    """Parse a complete supported document and return markdown text."""
    return _tool_parse_file({"file_path": file_path})


@mcp.tool
def read(file_path: str) -> str:
    """Read a plain text file."""
    return _tool_read({"file_path": file_path})


@mcp.tool
def grep(file_path: str, pattern: str) -> str:
    """Search a text file with a regular expression."""
    return _tool_grep({"file_path": file_path, "pattern": pattern})


@mcp.tool
def glob(directory: str, pattern: str) -> str:
    """Find files matching a glob pattern under a directory."""
    return _tool_glob({"directory": directory, "pattern": pattern})


@mcp.tool
def index_folder(
    folder: str,
    db_path: str | None = None,
    discover_schema: bool = False,
    schema_name: str | None = None,
    with_metadata: bool = False,
    metadata_profile: dict[str, Any] | str | None = None,
    with_embeddings: bool = False,
) -> str:
    """Build or refresh a DuckDB index for supported documents."""
    return _tool_index_folder(
        _clean_args(
            folder=folder,
            db_path=db_path,
            discover_schema=discover_schema,
            schema_name=schema_name,
            with_metadata=with_metadata,
            metadata_profile=metadata_profile,
            with_embeddings=with_embeddings,
        )
    )


@mcp.tool
def index_status(folder: str, db_path: str | None = None) -> str:
    """Check whether a folder has an existing DuckDB index."""
    return _tool_index_status(_clean_args(folder=folder, db_path=db_path))


@mcp.tool
def search_index(
    corpus_folder: str,
    query: str,
    filters: str | None = None,
    limit: int = 5,
    db_path: str | None = None,
) -> str:
    """Search an indexed corpus."""
    return _tool_search_index(
        _clean_args(
            corpus_folder=corpus_folder,
            query=query,
            filters=filters,
            limit=limit,
            db_path=db_path,
        )
    )


@mcp.tool
def list_indexed_documents(
    corpus_folder: str,
    db_path: str | None = None,
) -> str:
    """List documents currently active in an indexed corpus."""
    return _tool_list_indexed_documents(
        _clean_args(corpus_folder=corpus_folder, db_path=db_path)
    )


@mcp.tool
def get_indexed_document(doc_id: str, db_path: str | None = None) -> str:
    """Return full content and metadata for an indexed document id."""
    return _tool_get_indexed_document(_clean_args(doc_id=doc_id, db_path=db_path))


TOOLS: list[dict[str, Any]] = [
    {
        "name": "explore",
        "title": "Agentic File Exploration",
        "description": (
            "Run the built-in FsExplorer agent. The MCP server calls a local "
            "OpenAI-compatible endpoint, chooses document tools, "
            "executes them, and returns a cited final answer plus trace."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Question or task to answer from local files.",
                },
                "folder": {
                    "type": "string",
                    "default": ".",
                    "description": "Root folder for the agent to inspect.",
                },
                "base_url": {
                    "type": "string",
                    "description": (
                        "OpenAI-compatible base URL. Can be omitted when "
                        "FS_EXPLORER_OPENAI_COMPAT_BASE_URL or legacy FS_EXPLORER_AGENT_BASE_URL is set."
                    ),
                },
                "model": {
                    "type": "string",
                    "default": DEFAULT_AGENT_MODEL,
                    "description": "Model name sent to the chat completion API.",
                },
                "api_key": {
                    "type": "string",
                    "description": (
                        "Optional API key. Prefer FS_EXPLORER_OPENAI_COMPAT_API_KEY "
                        "instead of passing secrets as tool arguments."
                    ),
                },
                "use_index": {
                    "type": "boolean",
                    "default": False,
                    "description": "Let the agent use existing index search tools.",
                },
                "db_path": {"type": "string", "description": "Optional DuckDB path."},
                "allow_indexing": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow the agent to build a local DuckDB index.",
                },
                "allow_embeddings": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow index_folder to generate embeddings.",
                },
                "allow_metadata": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow index_folder to run metadata extraction.",
                },
                "max_steps": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 30,
                    "default": DEFAULT_AGENT_MAX_STEPS,
                },
                "max_tool_chars": {
                    "type": "integer",
                    "minimum": 1000,
                    "maximum": 200000,
                    "default": DEFAULT_AGENT_MAX_TOOL_CHARS,
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": DEFAULT_AGENT_TEMPERATURE,
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 600,
                    "default": DEFAULT_AGENT_TIMEOUT_SECONDS,
                },
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
    {
        "name": "describe_directory",
        "title": "Describe Directory",
        "description": "List files and subdirectories in a local directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to inspect.",
                }
            },
            "required": ["directory"],
            "additionalProperties": False,
        },
    },
    {
        "name": "scan_folder",
        "title": "Scan Folder",
        "description": (
            "Parse supported documents in a folder in parallel and return previews. "
            "Use this to triage a document set before deep reading."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Folder to scan."},
                "max_workers": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "default": DEFAULT_MAX_WORKERS,
                },
                "preview_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "default": DEFAULT_SCAN_PREVIEW_CHARS,
                },
            },
            "required": ["directory"],
            "additionalProperties": False,
        },
    },
    {
        "name": "preview_file",
        "title": "Preview File",
        "description": "Return the first part of a supported document as markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Document path."},
                "max_chars": {
                    "type": "integer",
                    "minimum": 1,
                    "default": DEFAULT_PREVIEW_CHARS,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "parse_file",
        "title": "Parse File",
        "description": "Parse a complete supported document and return markdown text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Document path."}
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read",
        "title": "Read Text File",
        "description": "Read a plain text file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Text file path."}
            },
            "required": ["file_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "grep",
        "title": "Grep File",
        "description": "Search a text file with a regular expression.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Text file path."},
                "pattern": {"type": "string", "description": "Python regex pattern."},
            },
            "required": ["file_path", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "glob",
        "title": "Glob Paths",
        "description": "Find files matching a glob pattern under a directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to search."},
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern, for example '*.md' or '**/*.pdf'.",
                },
            },
            "required": ["directory", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "index_folder",
        "title": "Index Folder",
        "description": (
            "Build or refresh a DuckDB index for supported documents. Embeddings and "
            "langextract metadata are optional and require the configured provider."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Folder to index."},
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional DuckDB path. Defaults to FS_EXPLORER_DB_PATH "
                        "or ~/.fs_explorer/index.duckdb."
                    ),
                },
                "discover_schema": {"type": "boolean", "default": False},
                "schema_name": {"type": "string"},
                "with_metadata": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable langextract metadata extraction.",
                },
                "metadata_profile": {
                    "type": ["object", "string"],
                    "description": "Metadata profile object or JSON object string.",
                },
                "with_embeddings": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Generate embeddings using the configured "
                        "EmbeddingProvider."
                    ),
                },
            },
            "required": ["folder"],
            "additionalProperties": False,
        },
    },
    {
        "name": "index_status",
        "title": "Index Status",
        "description": "Check whether a folder has an existing DuckDB index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Indexed folder path."},
                "db_path": {"type": "string", "description": "Optional DuckDB path."},
            },
            "required": ["folder"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_index",
        "title": "Search Index",
        "description": (
            "Search an indexed corpus. Uses stored embeddings when available and a "
            "query embedding provider is configured; otherwise falls back to "
            "keyword search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_folder": {
                    "type": "string",
                    "description": "Folder path used when building the index.",
                },
                "query": {"type": "string", "description": "Search query."},
                "filters": {
                    "type": "string",
                    "description": "Optional metadata filter expression.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 5,
                },
                "db_path": {"type": "string", "description": "Optional DuckDB path."},
            },
            "required": ["corpus_folder", "query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_indexed_documents",
        "title": "List Indexed Documents",
        "description": "List documents currently active in an indexed corpus.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "corpus_folder": {
                    "type": "string",
                    "description": "Folder path used when building the index.",
                },
                "db_path": {"type": "string", "description": "Optional DuckDB path."},
            },
            "required": ["corpus_folder"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_indexed_document",
        "title": "Get Indexed Document",
        "description": "Return full content and metadata for an indexed document id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "string", "description": "Indexed document id."},
                "db_path": {"type": "string", "description": "Optional DuckDB path."},
            },
            "required": ["doc_id"],
            "additionalProperties": False,
        },
    },
]


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
    parser = ArgumentParser(description="FsExplorer MCP server.")
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
