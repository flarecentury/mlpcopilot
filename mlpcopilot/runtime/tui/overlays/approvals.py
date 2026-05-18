"""Approval rendering and approval-gate helpers for the TUI."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from rich.table import Table
from rich.text import Text

from mlpcopilot.runtime.approval import ApprovalManager, ApprovalRecord
from mlpcopilot.runtime.tui.commands.command_registry import (
    get_tui_command,
)
from mlpcopilot.runtime.tui.commands.command_registry import (
    normalize_tui_command_alias as _registry_normalize_tui_command_alias,
)
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.input.keymap import tui_action_key_label

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

_APPROVAL_ID_RE = re.compile(r"^apr_[0-9a-f]{12}$", re.IGNORECASE)
_APPROVAL_DECISION_COMMANDS = {"/approve", "/reject", "/changes"}
_APPROVAL_ACTIONS: tuple[tuple[str, str], ...] = (
    ("approve", "Approve"),
    ("reject", "Reject"),
    ("changes", "Request changes"),
)

def _list_pending_approvals(config: Config, session_id: str | None = None) -> list[ApprovalRecord]:
    return _combined_approval_records(config, session_id, kind="pending")


def _list_decision_approvals(config: Config, session_id: str | None = None) -> list[ApprovalRecord]:
    return _combined_approval_records(config, session_id, kind="decisions")


def _first_pending_approval(config: Config, session_id: str | None = None) -> ApprovalRecord | None:
    pending = _list_pending_approvals(config, session_id=session_id)
    return pending[0] if pending else None


def _combined_approval_records(
    config: Config,
    session_id: str | None,
    *,
    kind: str,
) -> list[ApprovalRecord]:
    records: list[ApprovalRecord] = []
    seen: set[str] = set()
    for manager in _approval_managers(config, session_id):
        loaded = manager.list_pending() if kind == "pending" else manager.list_decisions()
        for record in loaded:
            if record.approval_id in seen:
                continue
            seen.add(record.approval_id)
            records.append(record)
    return records


def _approval_managers(config: Config, session_id: str | None) -> list[ApprovalManager]:
    managers: list[ApprovalManager] = []
    if session_id:
        managers.append(ApprovalManager(config.workspace_path, session_key=session_id))
    managers.append(ApprovalManager(config.workspace_path))
    return managers

def _approval_block_message(config: Config, raw: str, session_id: str | None = None) -> str | None:
    record = _first_pending_approval(config, session_id=session_id)
    if record is None:
        return None
    normalized = _normalize_tui_command_alias(raw.strip())
    if _is_allowed_while_approval_pending(normalized):
        return None
    target = _approval_target(record)
    return (
        "Approval required before continuing. "
        f"{record.approval_id} is waiting for {_approval_action_label(record)}"
        f"{f' on {target}' if target else ''}. "
        f"Use /approve {record.approval_id}, /reject {record.approval_id}, "
        f"or /changes {record.approval_id} <reason>. "
        f"Shortcuts: {tui_action_key_label(config, 'approve')} approve, "
        f"{tui_action_key_label(config, 'reject')} reject, "
        f"{tui_action_key_label(config, 'changes')} request changes."
    )

def _is_allowed_while_approval_pending(raw: str) -> bool:
    parts = raw.strip().split(maxsplit=1)
    if not parts:
        return True
    command = parts[0].lower()
    if command in _APPROVAL_DECISION_COMMANDS:
        return True
    metadata = get_tui_command(command)
    return metadata is not None and command in {"/help", "/status", "/stop"}

def _normalize_tui_command_alias(raw: str) -> str:
    return _registry_normalize_tui_command_alias(raw)

def _approvals_renderable(
    pending: list[ApprovalRecord],
    decisions: list[ApprovalRecord] | None = None,
    *,
    viewport_width: int | None = None,
) -> Table:
    table = Table.grid(expand=True)
    table.add_column("Line", no_wrap=True)
    records = pending[:8]
    if records:
        for record in records:
            table.add_row(_approval_row_line(record, viewport_width, state=_approval_risk_level(record)))
        return table
    recent_decisions = list(reversed(decisions or []))[:8]
    if not recent_decisions:
        table.add_row("(none)")
        return table
    for record in recent_decisions:
        table.add_row(_approval_row_line(record, viewport_width, state=record.status))
    return table

def _approvals_panel_title(pending: list[ApprovalRecord]) -> str:
    return f"Approvals ({len(pending)})"


def _approval_row_line(
    record: ApprovalRecord,
    width: int | None,
    *,
    state: str,
) -> str:
    id_width, state_width, action_width, target_width, run_width = _approval_column_widths(
        width,
        has_run=bool(record.run_id),
    )
    approval_id = _fit_approval_cell(record.approval_id, id_width)
    state_text = _fit_approval_cell(state, state_width)
    action = _fit_approval_cell(_approval_action_label(record), action_width)
    target = _fit_approval_cell(_approval_target(record) or record.title, target_width)
    if run_width:
        run = _fit_approval_cell(record.run_id or "", run_width)
        return " ".join((approval_id, state_text, action, target, run))
    return " ".join((approval_id, state_text, action, target)).rstrip()


def _approval_column_widths(width: int | None, *, has_run: bool) -> tuple[int, int, int, int, int]:
    if width is None:
        return 16, 10, 16, 24, 12 if has_run else 0
    id_width = 16
    state_width = 8 if width < 72 else 10
    action_width = 12 if width < 72 else 16
    run_width = 12 if has_run and width >= 82 else 0
    spaces = 3 + (1 if run_width else 0)
    target_width = max(8, width - id_width - state_width - action_width - run_width - spaces)
    return id_width, state_width, action_width, target_width, run_width


def _fit_approval_cell(value: str, width: int) -> str:
    return _short(" ".join(str(value).split()), width).ljust(width)

def _approval_focus_renderable(
    record: ApprovalRecord,
    selection: int = 0,
    config: Config | None = None,
) -> Text:
    risk = _approval_risk_level(record)
    selected_idx = selection % len(_APPROVAL_ACTIONS)
    text = Text()
    text.append(f"{record.approval_id} ", style="bold")
    text.append(f"[{risk}]\n", style=_approval_risk_style(risk))
    text.append("Action: ", style="bold")
    text.append(f"{_approval_action_label(record)}\n")
    if target := _approval_target(record):
        text.append("Target: ", style="bold")
        text.append(f"{target}\n")
    if args := _approval_arguments(record):
        text.append("Args: ", style="bold")
        text.append(f"{args}\n")
    for idx, (action, label) in enumerate(_APPROVAL_ACTIONS):
        marker = "> " if idx == selected_idx else "  "
        shortcut = _approval_action_shortcut(action, config)
        style = "bold black on yellow" if idx == selected_idx else "yellow"
        text.append(f"{marker}{label}", style=style)
        text.append(f"  /{action} {record.approval_id}", style=style)
        if shortcut:
            text.append(f"  {shortcut}", style=style)
        if idx < len(_APPROVAL_ACTIONS) - 1:
            text.append("\n")
    return text

def _selected_approval_action(selection: int) -> str:
    return _APPROVAL_ACTIONS[selection % len(_APPROVAL_ACTIONS)][0]

def _approval_action_shortcut(action: str, config: Config | None = None) -> str:
    if action == "approve":
        return f"Enter/{tui_action_key_label(config, 'approve')}"
    if action == "reject":
        return f"Esc/{tui_action_key_label(config, 'reject')}"
    if action == "changes":
        return tui_action_key_label(config, "changes")
    return ""

def _approval_action_label(record: ApprovalRecord) -> str:
    metadata = record.metadata or {}
    tool = metadata.get("tool")
    if tool == "exec" or record.action_type in {"exec_command", "destructive_exec"}:
        return "Exec Command"
    if isinstance(tool, str) and tool.startswith("mcp_"):
        return "MCP Tool Call"
    if tool in {"write_file", "edit_file", "notebook_edit"} or record.action_type.endswith("_update"):
        return "File Update"
    if record.action_type == "run_artifact_overwrite":
        return "Artifact Overwrite"
    if record.action_type == "tool_execution":
        return "Tool Call"
    return record.action_type.replace("_", " ").title()

def _approval_target(record: ApprovalRecord) -> str:
    metadata = record.metadata or {}
    for key in ("command", "path", "tool"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    arguments = metadata.get("arguments")
    if isinstance(arguments, dict):
        for key in ("path", "dataset_path", "checkpoint_path", "run_id", "url"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return record.title.strip()

def _approval_arguments(record: ApprovalRecord) -> str:
    metadata = record.metadata or {}
    arguments = metadata.get("arguments")
    if arguments is None:
        arguments = {
            key: value
            for key, value in metadata.items()
            if key not in {"args_hash"} and value is not None
        }
    if not arguments:
        return ""
    try:
        return _short(json.dumps(arguments, ensure_ascii=False, sort_keys=True), 180)
    except (TypeError, ValueError):
        return _short(str(arguments), 180)

def _approval_risk_level(record: ApprovalRecord) -> str:
    metadata = record.metadata or {}
    explicit = metadata.get("risk_level") or metadata.get("risk")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    tool = metadata.get("tool")
    command = str(metadata.get("command") or "").lower()
    if record.action_type == "destructive_exec" or re.search(r"\b(rm|sudo|chmod|chown|dd|mkfs|kill)\b", command):
        return "high"
    if isinstance(tool, str) and tool.startswith("mcp_"):
        return "high"
    if record.action_type in {"memory_update", "project_update", "run_artifact_overwrite"}:
        return "high"
    if record.action_type in {"file_update", "tool_execution", "exec_command"}:
        return "medium"
    return "low"

def _approval_risk_style(risk: str) -> str:
    risk = risk.lower()
    if risk in {"critical", "fatal"}:
        return "bold white on red"
    if risk == "high":
        return "bold red"
    if risk == "medium":
        return "bold yellow"
    return "bold green"

def _approval_border_style(record: ApprovalRecord) -> str:
    risk = _approval_risk_level(record)
    if risk in {"critical", "fatal", "high"}:
        return "red"
    return "yellow"
