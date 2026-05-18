"""Compatibility facade for TUI input helpers and command dispatch."""
# ruff: noqa: F401,I001

from __future__ import annotations

from mlpcopilot.runtime.tui.commands.command_approvals import (
    _approval_tool_detail,
    _handle_tui_approval_command,
    _record_resumed_approval_tool,
    _resumed_result_is_background,
    _resumed_result_is_error,
)
from mlpcopilot.runtime.tui.commands.command_dispatcher import (
    dispatch_tui_command,
)
from mlpcopilot.runtime.tui.commands.command_runtime import (
    _format_model_status,
    _format_tui_artifacts,
    _format_tui_history,
    _format_tui_jobs,
    _format_tui_raw_tool_result,
    _format_tui_runs,
    _format_tui_tool_log,
    _model_candidates,
    handle_tui_runtime_command,
    stop_tui_job,
    switch_tui_layout,
    switch_tui_model,
)
from mlpcopilot.runtime.tui.commands.command_registry import (
    _TUI_SLASH_COMMANDS,
    _TUI_SLASH_COMMAND_BY_NAME,
    TuiSlashCommand,
    format_tui_help,
    get_tui_command,
    is_immediate_local_tui_command,
    is_tui_approval_decision_command,
    is_tui_stop_command,
    normalize_tui_command_alias,
    task_running_block_message,
    tui_command_name,
)
from mlpcopilot.runtime.tui.input.input_controller import (
    TuiInputController,
    _accept_tui_buffer,
    _navigate_input_history,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState


def _task_running_block_message(state: RuntimeTuiState, raw: str) -> str | None:
    return task_running_block_message(state.running, raw)


def _is_tui_stop_command(raw: str) -> bool:
    return is_tui_stop_command(raw)


# Backward-compatible private aliases used by existing tests and modules.
_normalize_tui_command_alias = normalize_tui_command_alias
