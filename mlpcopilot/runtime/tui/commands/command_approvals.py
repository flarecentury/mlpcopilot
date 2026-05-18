"""Approval slash command handlers for the TUI."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from mlpcopilot.runtime.approval import ApprovalManager
from mlpcopilot.runtime.tui.common import (
    _format_args,
    _sanitize_terminal_output_for_tui,
    _short,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


async def _handle_tui_approval_command(
    config: Config,
    agent_loop: Any,
    raw: str,
    state: RuntimeTuiState | None = None,
) -> str | None:
    parts = raw.strip().split(maxsplit=2)
    if not parts:
        return None
    command = parts[0].lower()
    if command not in {"/approve", "/reject", "/changes"}:
        return None
    if len(parts) < 2:
        return f"Error: {command} requires an approval id"

    approval_id = parts[1]
    reason = parts[2] if len(parts) > 2 else None
    session_id = state.active_session_id if state is not None else None
    manager = ApprovalManager(config.workspace_path, session_key=session_id)
    try:
        record, changed = _apply_approval_decision(manager, command, approval_id, reason)
    except KeyError:
        if session_id is None:
            return f"Error: 'Approval not found: {approval_id}'"
        manager = ApprovalManager(config.workspace_path)
        try:
            record, changed = _apply_approval_decision(manager, command, approval_id, reason)
        except (KeyError, ValueError) as exc:
            return f"Error: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"

    verb = "marked" if changed else "already"
    content = f"Approval {record.approval_id} {verb} {record.status}"
    if command == "/approve":
        from mlpcopilot.agent.tools.session_context import bind_session_key, reset_session_key
        from mlpcopilot.runtime.approval import resume_approved_action

        running_entry = (
            _record_resumed_approval_start(state, record)
            if state is not None
            else None
        )
        started = time.monotonic()
        session_token = bind_session_key(session_id)
        try:
            resumed = await resume_approved_action(agent_loop, record)
        finally:
            reset_session_key(session_token)
        duration_s = max(0.0, time.monotonic() - started)
        if resumed:
            if state is not None:
                _record_resumed_approval_tool(
                    state,
                    record,
                    resumed,
                    duration_s,
                    entry=running_entry,
                )
            content = _format_resumed_approval_message(content, record, resumed, duration_s)
        elif running_entry is not None:
            running_entry.status = "ok"
            running_entry.duration_s = duration_s
    return content


def _apply_approval_decision(
    manager: ApprovalManager,
    command: str,
    approval_id: str,
    reason: str | None,
):
    if command == "/approve":
        return manager.approve_or_get(approval_id, decided_by="tui", reason=reason)
    if command == "/reject":
        return manager.reject(approval_id, decided_by="tui", reason=reason), True
    return manager.needs_changes(approval_id, decided_by="tui", reason=reason), True


def _record_resumed_approval_start(
    state: RuntimeTuiState,
    record: Any,
) -> ToolLogEntry | None:
    metadata = record.metadata or {}
    tool_name = metadata.get("tool")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    entry = ToolLogEntry(
        name=tool_name,
        status="running",
        detail=_approval_tool_detail(record),
        call_id=record.approval_id,
    )
    state.tool_log.append(entry)
    state.trim_tool_log()
    return entry


def _record_resumed_approval_tool(
    state: RuntimeTuiState,
    record: Any,
    resumed: str,
    duration_s: float,
    *,
    entry: ToolLogEntry | None = None,
) -> None:
    metadata = record.metadata or {}
    tool_name = metadata.get("tool")
    if not isinstance(tool_name, str) or not tool_name:
        return
    detail = _approval_tool_detail(record)
    if _resumed_result_is_background(resumed):
        status = "background"
    else:
        status = "error" if _resumed_result_is_error(resumed) else "ok"
    if entry is None:
        entry = ToolLogEntry(name=tool_name, status=status, detail=detail)
        state.tool_log.append(entry)
    entry.status = status
    entry.detail = detail
    entry.duration_s = duration_s
    state.trim_tool_log()


def _approval_tool_detail(record: Any) -> str:
    metadata = record.metadata or {}
    if record.action_type in {"exec_command", "destructive_exec"}:
        command = metadata.get("command")
        return command if isinstance(command, str) else ""
    arguments = metadata.get("arguments")
    return _format_args(arguments)


def _format_resumed_approval_message(
    prefix: str,
    record: Any,
    resumed: str,
    duration_s: float,
) -> str:
    subject = _approval_resume_subject(record)
    payload = _resumed_payload(resumed)
    duration = f"{duration_s:.2f}s"
    if _resumed_result_is_background(resumed):
        details = _background_result_details(payload)
        suffix = f"{subject} started in background in {duration}."
        return f"{prefix}\n{suffix}{details}"
    if _resumed_result_is_error(resumed):
        return (
            f"{prefix}\n"
            f"{subject} failed in {duration}.\n"
            f"Output:\n{_limit_tui_resume_output(payload)}"
        )

    useful_output = _strip_success_exit_code(payload)
    if not useful_output:
        return f"{prefix}\n{subject} completed OK in {duration}."
    return (
        f"{prefix}\n"
        f"{subject} completed OK in {duration}.\n"
        f"Output:\n{_limit_tui_resume_output(useful_output)}"
    )


def approval_continuation_result(approval_result: str | None) -> str | None:
    """Normalize one approval command result for later agent continuation."""
    if not approval_result:
        return None
    if not approval_result.startswith("Approval "):
        return None
    return _limit_tui_resume_output(approval_result, limit=5000)


def approval_continuation_prompt(approval_results: list[str] | str | None) -> str | None:
    """Build an internal agent follow-up after an approval batch resolves."""
    if isinstance(approval_results, str):
        results = [approval_results]
    else:
        results = list(approval_results or [])
    normalized = [result for item in results if (result := approval_continuation_result(item))]
    if not normalized:
        return None
    payload = "\n\n---\n\n".join(normalized)
    return (
        "The currently pending approval decisions in the TUI have been resolved. "
        "Continue the user's previous task using these decisions and tool results. "
        "If a tool failed, returned no matches, was rejected, or still leaves "
        "insufficient evidence, choose the next diagnostic or search step instead "
        "of stopping.\n\n"
        "<approval_results>\n"
        f"{payload}\n"
        "</approval_results>"
    )


def _approval_resume_subject(record: Any) -> str:
    metadata = record.metadata or {}
    tool_name = metadata.get("tool")
    tool_label = tool_name if isinstance(tool_name, str) and tool_name else "tool"
    detail = _approval_tool_detail(record)
    if not detail:
        return tool_label
    if tool_label == "exec":
        return f'exec "{_short(detail, 80)}"'
    return f"{tool_label} {_short(detail, 80)}"


def _resumed_payload(resumed: str) -> str:
    marker = "\n"
    return resumed.split(marker, 1)[1] if marker in resumed else resumed


def _strip_success_exit_code(payload: str) -> str:
    lines = [
        line.rstrip()
        for line in payload.rstrip().splitlines()
        if line.strip() != "Exit code: 0"
    ]
    return "\n".join(lines).strip()


def _background_result_details(payload: str) -> str:
    wanted_prefixes = ("Job:", "PID:", "Log:")
    lines = [
        line.strip()
        for line in payload.splitlines()
        if line.strip().startswith(wanted_prefixes)
    ]
    if not lines:
        return ""
    return "\n" + "\n".join(lines[:3])


def _limit_tui_resume_output(text: str, limit: int = 2000) -> str:
    text = _sanitize_terminal_output_for_tui(text).rstrip()
    if _visible_output_len(text) <= limit:
        return text
    return (
        _truncate_ansi_output(text, max(1, limit - 80)).rstrip()
        + "\x1b[0m\n\n... (output truncated; use /tool-log, /raw, or the job log for details)"
    )


def _visible_output_len(text: str) -> int:
    visible = 0
    index = 0
    while index < len(text):
        ansi_end = _ansi_sequence_end(text, index)
        if ansi_end is not None:
            index = ansi_end
            continue
        visible += 1
        index += 1
    return visible


def _truncate_ansi_output(text: str, limit: int) -> str:
    output: list[str] = []
    visible = 0
    index = 0
    while index < len(text) and visible < limit:
        ansi_end = _ansi_sequence_end(text, index)
        if ansi_end is not None:
            output.append(text[index:ansi_end])
            index = ansi_end
            continue
        output.append(text[index])
        visible += 1
        index += 1
    return "".join(output)


def _ansi_sequence_end(text: str, index: int) -> int | None:
    if not text.startswith("\x1b[", index):
        return None
    pos = index + 2
    while pos < len(text):
        char = text[pos]
        if "@" <= char <= "~":
            return pos + 1
        pos += 1
    return None


def _resumed_result_is_error(resumed: str) -> bool:
    result = _resumed_payload(resumed)
    return result.lstrip().startswith("Error:")


def _resumed_result_is_background(resumed: str) -> bool:
    result = _resumed_payload(resumed)
    return result.lstrip().startswith("Background exec started.")
