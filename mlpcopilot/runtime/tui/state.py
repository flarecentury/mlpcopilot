"""State objects for the MLP Copilot TUI."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from mlpcopilot.runtime.tui.common import (
    _compact_log_message,
    _format_args,
    _log_source_label,
)

_CHAT_HISTORY_LIMIT = 100
_TOOL_LOG_HISTORY_LIMIT = 200

@dataclass(slots=True)
class TuiMessage:
    role: str
    content: str

@dataclass(slots=True)
class ToolLogEntry:
    name: str
    status: str
    detail: str = ""
    started_at: float = field(default_factory=time.monotonic)
    created_at: float = field(default_factory=time.time)
    duration_s: float | None = None
    error: str | None = None
    call_id: str = ""
    raw_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "started_at": self.started_at,
            "created_at": self.created_at,
            "duration_s": self.duration_s,
            "error": self.error,
            "call_id": self.call_id,
            "raw_path": self.raw_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolLogEntry":
        return cls(
            name=str(data.get("name") or "tool"),
            status=str(data.get("status") or "log"),
            detail=str(data.get("detail") or ""),
            started_at=float(data.get("started_at") or 0.0),
            created_at=float(data.get("created_at") or time.time()),
            duration_s=(
                data.get("duration_s")
                if isinstance(data.get("duration_s"), (int, float))
                else None
            ),
            error=str(data.get("error")) if data.get("error") is not None else None,
            call_id=str(data.get("call_id") or ""),
            raw_path=str(data.get("raw_path") or ""),
        )

@dataclass(slots=True)
class RuntimeTuiState:
    chat: list[TuiMessage] = field(default_factory=list)
    tool_log: list[ToolLogEntry] = field(default_factory=list)
    root_session_id: str = "tui:default"
    active_session_id: str = "tui:default"
    active_run_id: str | None = None
    mcp_status: dict[str, Any] | None = None
    running: bool = False
    queued_count: int = 0
    current_input: str = ""
    approval_selection: int = 0
    layout_name: str = "four_pane"
    chat_scroll: int = 0
    overlay_stack: list[str] = field(default_factory=list)
    pager_open: bool = False
    pager_scroll: int = 0
    pager_message_index: int | None = None
    tool_log_pager_scroll: int = 0
    slash_menu_selection: int = 0
    slash_menu_suppressed_text: str = ""
    job_picker_selection: int = 0
    layout_picker_selection: int = 0
    model_picker_selection: int = 0
    approval_continuation_results: list[str] = field(default_factory=list)

    def add_chat(self, role: str, content: str) -> None:
        self.chat.append(TuiMessage(role=role, content=content))
        trimmed = max(0, len(self.chat) - _CHAT_HISTORY_LIMIT)
        if trimmed:
            del self.chat[:trimmed]
        if self.pager_message_index is not None:
            self.pager_message_index = min(
                max(0, self.pager_message_index - trimmed),
                len(self.chat) - 1,
            )

    def start_chat_stream(self, role: str = "assistant") -> int:
        self.add_chat(role, "")
        return len(self.chat) - 1

    def append_chat_stream(self, index: int | None, delta: str, role: str = "assistant") -> int:
        if index is None or index < 0 or index >= len(self.chat):
            self.add_chat(role, delta)
            return len(self.chat) - 1
        self.chat[index].content += delta
        return index

    def record_tool_events(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            if not isinstance(event, dict):
                continue
            name = str(event.get("name") or "tool")
            phase = str(event.get("phase") or "")
            call_id = str(event.get("call_id") or "")
            detail = _format_args(event.get("arguments"))
            raw_path = str(event.get("raw_path") or "")
            if phase == "start":
                self.tool_log.append(
                    ToolLogEntry(
                        name=name,
                        status="running",
                        detail=detail,
                        call_id=call_id,
                        raw_path=raw_path,
                    )
                )
                continue

            entry = self._find_tool_entry(call_id)
            if entry is None:
                entry = ToolLogEntry(
                    name=name,
                    status="running",
                    detail=detail,
                    call_id=call_id,
                    raw_path=raw_path,
                )
                self.tool_log.append(entry)
            if detail and not entry.detail:
                entry.detail = detail
            if raw_path:
                entry.raw_path = raw_path
            if phase == "error":
                error = str(event.get("error") or "Tool execution failed")
                if _is_approval_pending_tool_error(error):
                    entry.status = "approval_pending"
                    entry.duration_s = None
                    entry.error = None
                    continue
                entry.status = "error"
                entry.duration_s = max(0.0, time.monotonic() - entry.started_at)
                entry.error = error
                continue
            entry.status = "background" if _is_background_exec_result(event.get("result")) else "ok"
            entry.duration_s = max(0.0, time.monotonic() - entry.started_at)

        self.trim_tool_log()

    def _find_tool_entry(self, call_id: str) -> ToolLogEntry | None:
        if not call_id:
            return None
        for entry in reversed(self.tool_log):
            if entry.call_id == call_id:
                return entry
        return None

    def record_log(self, level: str, source: str, message: str) -> None:
        """Record a runtime log line in the TUI without writing over the terminal."""
        message = message.strip()
        if not message:
            return
        name = _log_source_label(source, message)
        status = level.lower()
        detail = _compact_log_message(source, message)
        for entry in reversed(self.tool_log[-8:]):
            if entry.name == name and entry.status == status and entry.detail == detail:
                return
        self.tool_log.append(
            ToolLogEntry(
                name=name,
                status=status,
                detail=detail,
            )
        )
        self.trim_tool_log()

    def cancel_running_tool_entries(self, reason: str = "stopped by user") -> int:
        """Mark currently running tool log entries as cancelled for this TUI session."""
        count = 0
        now = time.monotonic()
        for entry in self.tool_log:
            if entry.status != "running":
                continue
            entry.status = "cancelled"
            entry.duration_s = max(0.0, now - entry.started_at)
            if not entry.error:
                entry.error = reason
            count += 1
        if count:
            self.trim_tool_log()
        return count

    def trim_tool_log(self) -> None:
        del self.tool_log[:-_TOOL_LOG_HISTORY_LIMIT]

    def open_overlay(self, overlay_id: str) -> None:
        self.close_overlay(overlay_id)
        self.overlay_stack.append(overlay_id)
        self._sync_overlay_compat_flags()

    def close_overlay(self, overlay_id: str) -> None:
        self.overlay_stack = [item for item in self.overlay_stack if item != overlay_id]
        self._sync_overlay_compat_flags()

    def close_all_overlays(self) -> None:
        self.overlay_stack.clear()
        self._sync_overlay_compat_flags()

    def is_overlay_open(self, overlay_id: str) -> bool:
        if overlay_id == "pager" and self.pager_open:
            return True
        return overlay_id in self.overlay_stack

    def _sync_overlay_compat_flags(self) -> None:
        self.pager_open = "pager" in self.overlay_stack

def _is_approval_pending_tool_error(error: str) -> bool:
    return "Approval required before executing" in error

def _is_background_exec_result(result: Any) -> bool:
    return isinstance(result, str) and result.startswith("Background exec started.")
