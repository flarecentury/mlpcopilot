"""Log capture and Tool Log pane rendering."""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from rich.table import Table

from mlpcopilot.runtime.jobs import JobStore
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry
from mlpcopilot.utils.helpers import safe_filename

_DT_WIDTH = 11
_STATE_WIDTH = 7
_TOOL_WIDTH = 16
_ACTION_WIDTH = 23
_TIME_WIDTH = 5
_RUNNING_STALE_AFTER_S = 120.0
_TOOL_LOG_RELATIVE_PATH = Path("logs") / "tool-log.jsonl"
_SESSION_TOOL_LOG_DIR = Path("logs") / "sessions"
_RAW_TOOL_RESULTS_DIR = Path("logs") / "raw-tool-results"
_RAW_TOOL_RESULT_MIN_CHARS = 2_000

@contextmanager
def capture_tui_logs(
    state: RuntimeTuiState,
    *,
    enabled: bool = True,
) -> Iterator[None]:
    """Route MLP Copilot warnings/errors into the TUI instead of stderr."""
    if not enabled:
        yield
        return

    from loguru import logger

    logger.remove()
    handler_id = logger.add(
        lambda message: _record_tui_log_message(state, message),
        level="WARNING",
        colorize=False,
        format="{message}",
    )
    try:
        yield
    finally:
        with suppress(Exception):
            logger.remove(handler_id)
        with suppress(Exception):
            logger.add(sys.stderr, level=os.environ.get("LOGURU_LEVEL", "DEBUG"))

def _record_tui_log_message(state: RuntimeTuiState, message: Any) -> None:
    record = getattr(message, "record", None) or {}
    level = record.get("level")
    level_name = getattr(level, "name", None) or str(level or "log")
    source = str(record.get("name") or "log")
    text = str(record.get("message") or message)
    state.record_log(level_name, source, text)

def _tool_log_renderable(
    state: RuntimeTuiState,
    mcp_servers: list[dict[str, Any]],
    skills: list[dict[str, str]],
    mcp_status: dict[str, Any] | None = None,
    *,
    viewport_height: int | None = None,
    viewport_width: int | None = None,
) -> Table:
    table = Table.grid(expand=True)
    table.add_column("Line", no_wrap=True)

    if state.tool_log:
        table.add_row(_tool_log_header_line(viewport_width))
        for entry in _visible_tool_log_entries(state, viewport_height):
            table.add_row(_tool_log_line(entry, viewport_width))
        return table

    if mcp_servers:
        connected = set((mcp_status or {}).get("connected") or [])
        errors = {
            str(item.get("server")): str(item.get("message"))
            for item in ((mcp_status or {}).get("errors") or [])
            if isinstance(item, dict) and item.get("server")
        }
        limit = _tool_log_body_row_count(viewport_height)
        for server in mcp_servers[:limit]:
            server_name = str(server["name"])
            if server_name in connected:
                status = "connected"
            elif server_name in errors:
                status = "failed"
            else:
                status = "configured"
            detail = f"{status} {server_name} {server.get('type') or 'mcp'}"
            if server_name in errors:
                detail = f"{detail}: {errors[server_name]}"
            table.add_row(_short(detail, 140))
        return table

    return table

def _visible_tool_log_entries(
    state: RuntimeTuiState,
    viewport_height: int | None,
) -> list[ToolLogEntry]:
    return state.tool_log[-_tool_log_body_row_count(viewport_height):]

def _tool_log_body_row_count(viewport_height: int | None) -> int:
    if viewport_height is None:
        return 10
    return max(1, viewport_height - 1)

def _tool_log_panel_title(
    mcp_servers: list[dict[str, Any]],
    skills: list[dict[str, str]],
    mcp_status: dict[str, Any] | None = None,
) -> str:
    return f"Tool Log | {_mcp_count_label(mcp_servers, mcp_status).replace(' ', '')} skills({len(skills)})"

def _tool_log_line(entry: ToolLogEntry, width: int | None = None) -> str:
    return _tool_log_line_with_width(entry, width)


def _tool_log_line_with_width(entry: ToolLogEntry, width: int | None) -> str:
    timestamp = datetime.fromtimestamp(entry.created_at).strftime("%m-%d %H:%M")
    duration = "-" if entry.duration_s is None else f"{entry.duration_s:.2f}s"
    action_width = _tool_log_action_width(width)
    return " ".join(
        (
            _fit_cell(timestamp, _DT_WIDTH),
            _fit_cell(_tool_log_state_label(_tool_log_effective_status(entry)), _STATE_WIDTH),
            _fit_cell(entry.name, _TOOL_WIDTH),
            _fit_cell(_tool_log_detail(entry), action_width),
            _fit_cell(duration, _TIME_WIDTH, align="right"),
        )
    )

def _session_log_stem(session_id: str) -> str:
    return safe_filename(session_id) or "default"


def tool_log_relative_path(session_id: str | None = None) -> Path:
    if not session_id:
        return _TOOL_LOG_RELATIVE_PATH
    return _SESSION_TOOL_LOG_DIR / f"{_session_log_stem(session_id)}.tool-log.jsonl"


def format_tool_log_text(
    entries: list[ToolLogEntry],
    *,
    limit: int = 20,
    session_id: str | None = None,
) -> str:
    if not entries:
        return "Tool log: none."
    visible = entries[-limit:]
    lines = ["Recent tool log:", _tool_log_header_line()]
    lines.extend(_tool_log_line(entry) for entry in visible)
    if any(entry.raw_path for entry in visible):
        lines.append("Raw results: /raw [last|call_id]")
    lines.append(f"Full log: {tool_log_relative_path(session_id).as_posix()}")
    return "\n".join(lines)

def _render_tool_log_pager_ansi(state: RuntimeTuiState, *, width: int, height: int) -> str:
    if not state.tool_log:
        return "No tool log entries are available.\n\nEsc closes this pager."

    content_height = max(1, height - 4)
    lines = [_tool_log_line_with_width(entry, max(20, width - 2)) for entry in state.tool_log]
    max_scroll = max(0, len(lines) - content_height)
    state.tool_log_pager_scroll = min(max(0, state.tool_log_pager_scroll), max_scroll)
    start = state.tool_log_pager_scroll
    end = min(len(lines), start + content_height)
    pct = 100 if max_scroll == 0 else int((state.tool_log_pager_scroll / max_scroll) * 100)
    header = (
        f"tool log {len(state.tool_log)} entr{'y' if len(state.tool_log) == 1 else 'ies'}"
        f" | {pct}% | PgUp/PgDn scroll | Home/End jump | Esc close"
    )
    divider = "-" * min(width, max(8, len(header)))
    return "\n".join([header, divider, _tool_log_header_line(max(20, width - 2)), *lines[start:end], divider])

def _tool_log_header_line(width: int | None = None) -> str:
    action_width = _tool_log_action_width(width)
    return " ".join(
        (
            _fit_cell("Datetime", _DT_WIDTH),
            _fit_cell("State", _STATE_WIDTH),
            _fit_cell("Tools", _TOOL_WIDTH),
            _fit_cell("Action", action_width),
            _fit_cell("Time", _TIME_WIDTH, align="right"),
        )
    )


def _tool_log_action_width(width: int | None) -> int:
    if width is None:
        return _ACTION_WIDTH
    fixed = _DT_WIDTH + _STATE_WIDTH + _TOOL_WIDTH + _TIME_WIDTH + 4
    return max(_ACTION_WIDTH, width - fixed)

def _tool_log_state_label(status: str) -> str:
    if status == "approval_pending":
        return "Pending"
    if status == "background":
        return "BG"
    if status == "ok":
        return "OK"
    if status == "error":
        return "Error"
    if status == "cancelled":
        return "Cancel"
    if status == "stale":
        return "Stale"
    if status == "running":
        return "Running"
    return status[:1].upper() + status[1:]

def _tool_log_effective_status(entry: ToolLogEntry) -> str:
    if entry.status == "running" and time.monotonic() - entry.started_at > _RUNNING_STALE_AFTER_S:
        return "stale"
    return entry.status

def _tool_log_detail(entry: ToolLogEntry) -> str:
    if entry.detail:
        if entry.name == "exec":
            return json.dumps(entry.detail, ensure_ascii=False)
        return entry.detail
    return entry.error or ""

def _fit_cell(value: str, width: int, *, align: str = "left") -> str:
    text = " ".join(str(value).split())
    if len(text) > width:
        text = text[: max(0, width - 3)] + "..."
    if align == "right":
        return text.rjust(width)
    return text.ljust(width)

def _mcp_count_label(
    mcp_servers: list[dict[str, Any]],
    mcp_status: dict[str, Any] | None = None,
) -> str:
    mcp_state = mcp_status or {}
    configured = int(mcp_state.get("configured_count", len(mcp_servers)) or 0)
    return f"mcp ({configured})"

def load_persisted_tool_log(
    workspace: Path,
    *,
    limit: int = 200,
    session_id: str | None = None,
    fallback_to_global: bool = True,
) -> list[ToolLogEntry]:
    path = _tool_log_path(workspace, session_id)
    entries = _read_tool_log_entries(path, limit=limit)
    if entries or session_id is None or not fallback_to_global:
        return entries
    return _read_tool_log_entries(_tool_log_path(workspace, None), limit=limit)


def _read_tool_log_entries(path: Path, *, limit: int) -> list[ToolLogEntry]:
    if not path.exists():
        return []
    entries: list[ToolLogEntry] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(ToolLogEntry.from_dict(data))
    return entries[-limit:]

def save_persisted_tool_log(
    workspace: Path,
    entries: list[ToolLogEntry],
    *,
    limit: int = 200,
    session_id: str | None = None,
) -> None:
    path = _tool_log_path(workspace, session_id)
    recent = entries[-limit:]
    _write_tool_log_entries(path, recent)
    if session_id is not None:
        _merge_global_tool_log(workspace, recent, limit=limit)


def _tool_log_path(workspace: Path, session_id: str | None = None) -> Path:
    return workspace.expanduser() / tool_log_relative_path(session_id)


def _write_tool_log_entries(path: Path, entries: list[ToolLogEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(entry.to_dict(), ensure_ascii=False, sort_keys=True) + "\n" for entry in entries)
    path.write_text(text, encoding="utf-8")


def _merge_global_tool_log(workspace: Path, entries: list[ToolLogEntry], *, limit: int) -> None:
    global_path = _tool_log_path(workspace, None)
    merged: dict[tuple[str, str, str, str], ToolLogEntry] = {
        _tool_log_entry_key(entry): entry
        for entry in _read_tool_log_entries(global_path, limit=limit)
    }
    for entry in entries:
        merged[_tool_log_entry_key(entry)] = entry
    ordered = sorted(merged.values(), key=lambda entry: entry.created_at)
    _write_tool_log_entries(global_path, ordered[-limit:])


def _tool_log_entry_key(entry: ToolLogEntry) -> tuple[str, str, str, str]:
    if entry.call_id:
        return (entry.call_id, "", entry.name, "")
    return (
        "",
        f"{entry.created_at:.6f}",
        entry.name,
        entry.detail,
    )

def persist_raw_tool_event_results(
    workspace: Path,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist raw MCP or large tool results and attach relative paths to events."""
    if not events:
        return events
    enriched: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            enriched.append(event)
            continue
        copied = dict(event)
        if copied.get("phase") == "end":
            raw_path = _write_raw_tool_result_if_needed(workspace, copied)
            if raw_path:
                copied["raw_path"] = raw_path
                _record_mcp_raw_result_job(workspace, copied, raw_path)
        enriched.append(copied)
    return enriched

def _record_mcp_raw_result_job(workspace: Path, event: dict[str, Any], raw_path: str) -> None:
    tool_name = str(event.get("name") or "")
    if not tool_name.startswith("mcp_"):
        return
    call_id = str(event.get("call_id") or "").strip()
    job_stem = safe_filename(call_id or f"{tool_name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    job_id = f"mcp_{job_stem or 'tool_result'}"
    try:
        store = JobStore(workspace)
        store.record_start(
            kind="mcp",
            command=_mcp_job_command(event),
            pid=None,
            job_id=job_id,
            cwd=str(workspace.expanduser()),
            log_path=workspace.expanduser() / raw_path,
        )
        store.finish(job_id, returncode=0)
    except OSError:
        return

def _mcp_job_command(event: dict[str, Any]) -> str:
    name = str(event.get("name") or "mcp")
    arguments = event.get("arguments")
    if not isinstance(arguments, dict) or not arguments:
        return name
    try:
        args_text = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        args_text = str(arguments)
    return _short(f"{name} {args_text}", 240)

def _write_raw_tool_result_if_needed(workspace: Path, event: dict[str, Any]) -> str | None:
    result = event.get("result")
    if result is None:
        return None
    tool_name = str(event.get("name") or "tool")
    text, suffix = _raw_tool_result_text(result)
    if not _should_persist_raw_tool_result(tool_name, text):
        return None
    call_id = str(event.get("call_id") or "").strip()
    stem = safe_filename(call_id or f"{tool_name}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}")
    if not stem:
        stem = "tool_result"
    relative = _RAW_TOOL_RESULTS_DIR / f"{stem}.{suffix}"
    path = workspace.expanduser() / relative
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return relative.as_posix()

def _raw_tool_result_text(result: Any) -> tuple[str, str]:
    if isinstance(result, str):
        return result, "txt"
    try:
        return json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str), "json"
    except (TypeError, ValueError):
        return str(result), "txt"

def _should_persist_raw_tool_result(tool_name: str, text: str) -> bool:
    return tool_name.startswith("mcp_") or len(text) > _RAW_TOOL_RESULT_MIN_CHARS
