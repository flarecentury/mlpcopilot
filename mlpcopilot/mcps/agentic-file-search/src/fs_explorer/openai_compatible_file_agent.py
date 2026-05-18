
"""OpenAI-compatible agentic file-search implementation.

This module contains the nested agent loop and internal filesystem/index tools
used by MCP wrappers. MCP servers should import this module instead of importing
from ``mcp_server_full.py``.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

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
from .search import IndexedQueryEngine, MetadataFilterParseError, supported_filter_syntax
from .storage import DuckDBStorage

ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class TaskPolicy:
    """Guidance inferred from the user's task before the LLM chooses tools."""

    intent: str
    recommended_start: str
    output_focus: str
    guidance: tuple[str, ...]
    target_hints: tuple[str, ...]


_PATH_HINT_RE = re.compile(
    r"(?:~|/|\.\.?/)?[\w./@+-]+\.[A-Za-z0-9_+-]{1,12}|/[\w./@+-]+"
)


def _extract_target_hints(task: str) -> tuple[str, ...]:
    hints: list[str] = []
    for match in _PATH_HINT_RE.finditer(task):
        hint = match.group(0).strip("`'\".,，。；;:：()[]{}")
        if hint and hint not in hints:
            hints.append(hint)
    return tuple(hints[:8])


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _infer_task_policy(task: str) -> TaskPolicy:
    normalized = task.strip()
    lowered = normalized.lower()
    target_hints = _extract_target_hints(normalized)

    procedure_terms = (
        "install",
        "installation",
        "setup",
        "deploy",
        "runbook",
        "start service",
        "systemd",
        "docker",
        "usage steps",
        "how to run",
        "安装",
        "部署",
        "启动",
        "运行",
        "使用方法",
        "用法",
        "具体步骤",
        "具体安装",
        "安装步骤",
        "安装方法",
        "怎么安装",
        "怎么用",
    )
    risk_terms = (
        "risk",
        "risks",
        "security",
        "danger",
        "permission",
        "privilege",
        "delete",
        "network",
        "风险",
        "安全",
        "权限",
        "危险",
        "删除",
        "外部下载",
    )
    inventory_terms = (
        "list all",
        "list files",
        "what files",
        "inventory",
        "目录",
        "文件列表",
        "有哪些文件",
        "都有啥",
    )
    read_terms = (
        "read ",
        "cat ",
        "open ",
        "show ",
        "summarize ",
        "查看",
        "读取",
        "看看",
        "总结",
    )
    compare_terms = ("compare", "difference", "diff", "对比", "比较", "区别")

    if _has_any(lowered, procedure_terms):
        return TaskPolicy(
            intent="procedure",
            recommended_start=(
                "Locate the referenced script/runbook first. If no explicit file is "
                "named, scan or grep for installer/workflow terms, then read the most "
                "relevant file."
            ),
            output_focus=(
                "Return concrete ordered steps, prerequisites, modes, commands or "
                "entry points, configuration files, service/container actions, "
                "verification, uninstall/rollback behavior, and risks."
            ),
            guidance=(
                "Do not stop at a generic feature summary.",
                "For shell scripts, identify branches such as Docker/systemd/manual modes.",
                "Preserve user intent: if the task asks for installation, answer installation directly.",
            ),
            target_hints=target_hints,
        )

    if _has_any(lowered, risk_terms):
        return TaskPolicy(
            intent="risk_review",
            recommended_start=(
                "Read or parse the referenced file; if only a topic is given, grep/scan "
                "for relevant files before deep reading."
            ),
            output_focus=(
                "Return concrete risks, affected operations, required privileges, "
                "external network/download actions, destructive actions, secret handling, "
                "and safer follow-up checks."
            ),
            guidance=(
                "Separate confirmed findings from inferences.",
                "Quote only short snippets needed to justify risk findings.",
            ),
            target_hints=target_hints,
        )

    if _has_any(lowered, inventory_terms):
        return TaskPolicy(
            intent="inventory",
            recommended_start="Use describe_directory or glob to list the configured knowledge root.",
            output_focus="Return a concise inventory with file names and likely purpose when inferable.",
            guidance=("Do not read every file unless the task asks for content details.",),
            target_hints=target_hints,
        )

    if _has_any(lowered, compare_terms):
        return TaskPolicy(
            intent="compare",
            recommended_start="Locate the compared targets, read only the relevant files, then synthesize differences.",
            output_focus="Return the comparison dimensions, key differences, and cited source paths.",
            guidance=("If one side is ambiguous, identify candidate files before comparing.",),
            target_hints=target_hints,
        )

    if _has_any(lowered, read_terms):
        return TaskPolicy(
            intent="read_or_summarize",
            recommended_start=(
                "If task names a file/path, read that file. If it names a bare topic, "
                "grep or scan to find files mentioning that topic, then read the best match."
            ),
            output_focus=(
                "Summarize the relevant file or topic. If the task also asks for a "
                "specific aspect, answer that aspect directly."
            ),
            guidance=(
                "Do not reproduce large files verbatim unless explicitly requested.",
                "For scripts, include purpose, key branches, configuration, and operational effects.",
            ),
            target_hints=target_hints,
        )

    return TaskPolicy(
        intent="answer",
        recommended_start=(
            "Use the directory listing to choose between scan_folder, grep, read, "
            "or indexed search based on the question."
        ),
        output_focus="Answer the user's question directly with concise sources.",
        guidance=(
            "Prefer locating evidence before finalizing.",
            "For follow-up-style tasks, infer the likely target from visible files and the task text.",
        ),
        target_hints=target_hints,
    )


def _format_task_policy(policy: TaskPolicy) -> str:
    lines = [
        "Internal task policy:",
        f"- Classified intent: {policy.intent}",
        f"- Recommended start: {policy.recommended_start}",
        f"- Output focus: {policy.output_focus}",
    ]
    if policy.target_hints:
        lines.append(f"- Target hints from task: {', '.join(policy.target_hints)}")
    if policy.guidance:
        lines.append("- Extra guidance:")
        lines.extend(f"  - {item}" for item in policy.guidance)
    return "\n".join(lines)

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
            "`base_url` is required unless FS_EXPLORER_OPENAI_COMPAT_BASE_URL or legacy FS_EXPLORER_AGENT_BASE_URL is set."
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
    lines = [
        "- describe_directory(directory*): List files and subdirectories in a local directory.",
        "- scan_folder(directory*, max_workers, preview_chars): Parse supported documents in a folder in parallel and return previews.",
        "- preview_file(file_path*, max_chars): Return the first part of a supported document as markdown.",
        "- parse_file(file_path*): Parse a complete supported document and return markdown text.",
        "- read(file_path*): Read a plain text file.",
        "- grep(file_path*, pattern*): Search a text file with a regular expression.",
        "- glob(directory*, pattern*): Find files matching a glob pattern under a directory.",
        "- index_status(folder*, db_path): Check whether a folder has an existing DuckDB index.",
        "- search_index(corpus_folder*, query*, filters, limit, db_path): Search an indexed corpus.",
        "- list_indexed_documents(corpus_folder*, db_path): List documents currently active in an indexed corpus.",
        "- get_indexed_document(doc_id*, db_path): Return full content and metadata for an indexed document id.",
    ]
    if allow_indexing:
        lines.append(
            "- index_folder(folder*, db_path, discover_schema, schema_name, with_metadata, metadata_profile, with_embeddings): Build or refresh a DuckDB index for supported documents."
        )
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
                        "Choose the next tool or return a final answer. If this "
                        "result is long, summarize it instead of copying it back."
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
            "Exploration policy: first follow the Internal task policy supplied in "
            "the user message. Classify the task intent before choosing tools. "
            "Inventory, read/summary, procedure extraction, risk review, comparison, "
            "and general search require different tool choices and final answer "
            "formats. For a bare topic rather than a path, locate candidate files "
            "with scan or grep before deep reading.\n\n"
            "Output policy: when a tool returns long file contents, scripts, logs, "
            "tables, or documents, summarize the material first. Do not reproduce "
            "the whole source text or a large code block in the final answer unless "
            "the user explicitly asks for the complete verbatim content. For read "
            "and parse_file results, report the file purpose, key sections, notable "
            "values or risks, and cite the source path. Include only short excerpts "
            "when they are necessary to support the answer. If the file is an "
            "installer, shell script, runbook, or operational workflow, include the "
            "concrete procedure: prerequisites, selectable modes, commands or entry "
            "points, config files, service/container actions, verification steps, "
            "uninstall/rollback behavior, and risks. If the task asks for install "
            "method, usage steps, or operational details, answer those directly as "
            "ordered steps rather than giving a generic feature overview.\n\n"
            f"Available tools:\n{_agent_tool_descriptions(self.allow_indexing)}"
        )

        policy = _infer_task_policy(self.task)
        task_policy = _format_task_policy(policy)
        user_prompt = (
            f"Task: {self.task}\n\n"
            f"Root folder: {self.folder}\n\n"
            f"{task_policy}\n\n"
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

