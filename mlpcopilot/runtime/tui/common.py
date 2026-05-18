"""Shared formatting helpers for the MLP Copilot TUI."""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console

from mlpcopilot.utils.path import abbreviate_path

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

_ANSI_CSI_RE = re.compile(r"\x1b\[([0-?]*)([ -/]*)([@-~])")
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
_ANSI_STANDALONE_ESC_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\([0-9A-Za-z]|\)[0-9A-Za-z])")
_ANSI_INCOMPLETE_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*(?=\n|$)")
_UNSAFE_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1a\x1c-\x1f\x7f]")

def _render_rich_ansi(renderable: Any, *, width: int, height: int) -> str:
    stream = io.StringIO()
    render_console = Console(
        file=stream,
        force_terminal=True,
        color_system="standard",
        width=width,
        height=height,
    )
    render_console.print(renderable)
    return stream.getvalue()

def _sanitize_terminal_output_for_tui(text: str) -> str:
    """Keep SGR colors, but remove terminal controls that can corrupt panes."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ANSI_OSC_RE.sub("", text)
    text = _ANSI_CSI_RE.sub(
        lambda match: match.group(0) if match.group(3) == "m" else "",
        text,
    )
    text = _ANSI_INCOMPLETE_CSI_RE.sub("", text)
    text = _ANSI_STANDALONE_ESC_RE.sub("", text)
    return _UNSAFE_CONTROL_RE.sub("", text)

def _display_workspace_path(workspace: Path, *, max_len: int = 52) -> str:
    return abbreviate_path(str(workspace), max_len=max_len)

def _channel_enabled(config: Config, name: str) -> bool:
    value = getattr(config.channels, name, None)
    if isinstance(value, dict):
        return bool(value.get("enabled"))
    return bool(getattr(value, "enabled", False))

def _format_args(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, dict):
        compact = _format_known_args(value)
        if compact:
            return _short(compact, 160)
    try:
        return _short(json.dumps(value, ensure_ascii=False, sort_keys=True), 160)
    except (TypeError, ValueError):
        return _short(str(value), 160)

def _format_known_args(value: dict[str, Any]) -> str:
    command = value.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip()

    path = value.get("path") or value.get("file_path")
    if isinstance(path, str) and path.strip():
        return path.strip()

    action = value.get("action")
    key = value.get("key")
    if isinstance(action, str) and isinstance(key, str):
        return f"{action} {key}"

    query = value.get("query")
    if isinstance(query, str) and query.strip():
        return f"query: {query.strip()}"

    if 0 < len(value) <= 3:
        parts: list[str] = []
        for key, raw in value.items():
            if raw is None:
                continue
            if isinstance(raw, (str, int, float, bool)):
                parts.append(f"{key}={raw}")
        if parts:
            return " ".join(parts)

    return ""

def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    return f"{size_bytes / (1024 * 1024):.1f} MiB"

def _write_policy(config: Config) -> str:
    gated = bool(getattr(config.tools, "approval_gated_writes", False))
    if gated:
        return "workspace+approval"
    return "ungated"

def _tool_approval_policy(config: Config) -> str:
    return "gated" if getattr(config.tools, "approval_required_for_tools", False) else "ungated"

def _log_source_label(source: str, message: str) -> str:
    if ".mcp" in source or message.startswith("MCP "):
        return "mcp"
    if message.startswith("No MCP servers connected successfully"):
        return "agent"
    if source.startswith("mlpcopilot."):
        source = source.removeprefix("mlpcopilot.")
    if source.startswith("agent.loop"):
        return "agent"
    return source.rsplit(".", 1)[-1] or "log"

def _compact_log_message(source: str, message: str) -> str:
    if ".mcp" in source and "MCP server '" in message and "failed to connect" in message:
        server = message.split("MCP server '", 1)[1].split("'", 1)[0]
        return f"{server}: connect failed"
    if message.startswith("No MCP servers connected successfully"):
        return "No MCP servers connected; retrying"
    return _short(message, 220)

def _provider_unavailable_message(reason: str) -> str:
    return (
        "Model provider is not configured, so chat requests are disabled.\n"
        f"{reason}\n\n"
        "The TUI can still show workspace status, artifacts, approvals, runs, "
        "and local slash commands."
    )

def _short(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."
