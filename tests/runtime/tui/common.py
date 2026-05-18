# ruff: noqa: F401,I001

import asyncio
import os
from pathlib import Path

from rich.console import Console

from mlpcopilot.command.builtin import register_builtin_commands
from mlpcopilot.command.router import CommandRouter
from mlpcopilot.config.schema import Config
from mlpcopilot.runtime.approval import ApprovalManager
from mlpcopilot.runtime.artifacts import ArtifactIndex
from mlpcopilot.runtime.jobs import JobStore
from mlpcopilot.runtime.tui import (
    _CHAT_HISTORY_LIMIT,
    RuntimeTuiState,
    TuiInputController,
    TuiQueuedInput,
    TuiRuntimeController,
    TuiUnavailableProvider,
    ToolLogEntry,
    _accept_tui_buffer,
    _active_overlay_filter,
    _approval_block_message,
    _approval_focus_renderable,
    _campaign_renderable,
    _chat_message_renderable,
    _chat_renderable,
    _chat_scroll_metrics,
    _clamp_scroll_from_bottom,
    _display_workspace_path,
    _footer_help_line,
    _format_args,
    _is_tui_stop_command,
    _is_vscode_terminal,
    _load_session_chat,
    _make_tui_completer,
    _navigate_input_history,
    _open_pager_for_latest_message,
    _pager_ansi,
    _render_job_picker_ansi,
    _render_layout_picker_ansi,
    _render_model_picker_ansi,
    _render_slash_menu_ansi,
    _render_tool_log_pager_ansi,
    _reset_tui_session_view,
    _selected_approval_action,
    _slice_chat_lines_from_bottom,
    _task_running_block_message,
    _tool_log_panel_title,
    _tool_log_renderable,
    _tui_full_screen_enabled,
    active_tui_overlay_id,
    apply_persisted_tui_state,
    build_tui_agent_loop,
    build_tui_key_bindings,
    build_tui_prompt_layout,
    capture_tui_logs,
    dispatch_tui_command,
    get_tui_overlay_spec,
    handle_tui_runtime_command,
    is_tui_overlay_esc_closable,
    list_tui_layout_specs,
    load_persisted_tool_log,
    load_tui_state,
    render_approval_focus_body,
    render_campaign_focus_body,
    render_compact_body,
    render_four_pane_body,
    render_tui,
    render_tui_body,
    save_persisted_tool_log,
    save_tui_state,
    slash_menu_candidates,
    slash_menu_visible,
    tui_state_path,
    tui_style_dict,
)
from mlpcopilot.runtime.tui.commands.command_registry import (
    format_tui_help,
    get_tui_command,
    is_immediate_local_tui_command,
    is_tui_approval_decision_command,
)
from mlpcopilot.runtime.workspace import sync_mlpcopilot_workspace
from mlpcopilot.session.manager import Session, SessionManager

from .helpers import (
    _FakeCompletionState,
    _FakeExecTool,
    _FakeInputBox,
    _FakeInputBuffer,
    _FakeLoop,
    _FakeQueue,
    _FakeTask,
)

__all__ = [name for name in globals() if not name.startswith("__")]
