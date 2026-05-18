"""Local runtime slash command handlers for the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mlpcopilot.command.registry import command_visible, get_command
from mlpcopilot.runtime.tui.commands.command_actions import (
    _format_model_status,
    stop_tui_job,
    switch_tui_layout,
    switch_tui_model,
)
from mlpcopilot.runtime.tui.commands.command_actions import (
    _model_candidates as _model_candidates,
)
from mlpcopilot.runtime.tui.commands.command_registry import (
    format_tui_help,
    normalize_tui_command_alias,
)
from mlpcopilot.runtime.tui.commands.command_views import (
    _format_tui_approvals,
    _format_tui_artifacts,
    _format_tui_history,
    _format_tui_jobs,
    _format_tui_raw_tool_result,
    _format_tui_runs,
    _format_tui_tool_log,
)
from mlpcopilot.runtime.tui.common import _tool_approval_policy, _write_policy
from mlpcopilot.runtime.tui.overlays.approvals import _APPROVAL_ID_RE, _approval_managers
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def handle_tui_runtime_command(
    config: Config,
    raw: str,
    agent_loop: Any | None = None,
    state: RuntimeTuiState | None = None,
    session_id: str | None = None,
) -> str | None:
    """Handle local runtime commands without sending them through the model."""
    raw = normalize_tui_command_alias(raw.strip())
    parts = raw.split(maxsplit=2)
    if not parts:
        return None
    if _APPROVAL_ID_RE.fullmatch(parts[0]) and len(parts) == 1:
        return (
            "Approval ID detected. Use "
            f"/approve {parts[0]}, /reject {parts[0]}, or /changes {parts[0]}."
        )
    command = parts[0].lower()
    spec = get_command(command)
    if spec is not None and not command_visible(spec, surface="tui", config=config):
        return None
    if command == "/model":
        if len(parts) == 1:
            return _format_model_status(config)
        if agent_loop is None:
            return "Error: /model <model> requires an active TUI runtime"
        return switch_tui_model(config, agent_loop, parts[1])
    if command in {"/profile", "/profiles"}:
        return (
            f"Current profile: {config.runtime_profile}. "
            "Profiles are selected by config file; start TUI with mlpcopilot tui -c <config>."
        )
    if command == "/status":
        mcp_allowlist = [
            item for item in getattr(config.tools, "approval_allowlist", [])
            if isinstance(item, str) and item.startswith("mcp_")
        ]
        mcp_policy = "gated+readonly" if not mcp_allowlist else f"gated+readonly+allowlist({len(mcp_allowlist)})"
        return (
            f"profile={config.runtime_profile} "
            f"workspace={config.workspace_path} "
            "read=workspace "
            f"writes={_write_policy(config)} "
            f"tools={_tool_approval_policy(config)} "
            f"mcp={mcp_policy}"
        )
    if command == "/runs":
        return _format_tui_runs(config)
    if command == "/jobs":
        return _format_tui_jobs(config)
    if command == "/tool-log":
        return _format_tui_tool_log(config, state)
    if command == "/raw":
        selector = parts[1] if len(parts) >= 2 else ""
        return _format_tui_raw_tool_result(config, state, selector)
    if command == "/artifacts":
        run_id = parts[1] if len(parts) >= 2 else ""
        return _format_tui_artifacts(config, run_id)
    if command == "/layout":
        layout_name = parts[1] if len(parts) >= 2 else ""
        return switch_tui_layout(state, layout_name, workspace=config.workspace_path)
    if command == "/history":
        count = parts[1] if len(parts) >= 2 else ""
        return _format_tui_history(state, count, config=config)
    if command == "/approvals":
        return _format_tui_approvals(config, state)
    if command == "/memory-audit":
        from mlpcopilot.runtime.memory_audit import format_memory_audit_report

        return format_memory_audit_report(config.workspace_path)
    if command == "/help":
        return format_tui_help(config)
    if command == "/stop":
        if len(parts) >= 2:
            return stop_tui_job(config, parts[1], state=state)
        if state is not None:
            marked = state.cancel_running_tool_entries("stale running entry cleared by /stop")
            if marked:
                return f"No active task to stop. Marked {marked} running tool log entr{'y' if marked == 1 else 'ies'} as cancelled."
        return "No active task to stop."
    if command not in {"/approve", "/reject", "/changes"}:
        return None
    if len(parts) < 2:
        return f"Error: {command} requires an approval id"

    approval_id = parts[1]
    reason = parts[2] if len(parts) > 2 else None
    record = None
    last_error: Exception | None = None
    for manager in _approval_managers(
        config,
        state.active_session_id if state is not None else None,
    ):
        try:
            if command == "/approve":
                record = manager.approve(approval_id, decided_by="tui", reason=reason)
            elif command == "/reject":
                record = manager.reject(approval_id, decided_by="tui", reason=reason)
            else:
                record = manager.needs_changes(approval_id, decided_by="tui", reason=reason)
            break
        except KeyError as exc:
            last_error = exc
            continue
        except ValueError as exc:
            return f"Error: {exc}"
    if record is None:
        return f"Error: {last_error or f'Approval not found: {approval_id}'}"
    return f"Approval {record.approval_id} marked {record.status}"
