"""Compatibility facade for the modularized MLP Copilot TUI."""
# ruff: noqa: F401,I001

from __future__ import annotations

from mlpcopilot.runtime.tui.app import run_tui
from mlpcopilot.runtime.tui.overlays.approvals import (
    _APPROVAL_ACTIONS,
    _APPROVAL_DECISION_COMMANDS,
    _APPROVAL_ID_RE,
    _approval_action_label,
    _approval_action_shortcut,
    _approval_arguments,
    _approval_block_message,
    _approval_border_style,
    _approval_focus_renderable,
    _approval_risk_level,
    _approval_risk_style,
    _approval_target,
    _approvals_panel_title,
    _approvals_renderable,
    _first_pending_approval,
    _is_allowed_while_approval_pending,
    _normalize_tui_command_alias,
    _selected_approval_action,
)
from mlpcopilot.runtime.tui.views.artifacts_panel import (
    _artifacts_panel_title,
    _artifacts_renderable,
)
from mlpcopilot.runtime.tui.views.campaign import (
    _campaign_panel_title,
    _campaign_renderable,
)
from mlpcopilot.runtime.tui.views.chat import (
    _CHAT_MARKDOWN_ROLES,
    _chat_message_renderable,
    _chat_panel_title,
    _chat_renderable,
    _chat_rendered_lines,
    _chat_scroll_metrics,
    _chat_transcript_renderable,
    _chat_viewport_size,
    _clamp_scroll_from_bottom,
    _looks_like_markdown,
    _max_scroll_from_bottom,
    _message_rendered_lines,
    _open_pager_for_latest_message,
    _pager_ansi,
    _render_pager_ansi,
    _slice_chat_lines_from_bottom,
)
from mlpcopilot.runtime.tui.commands import (
    TuiSlashCommand,
    TuiInputController,
    _TUI_SLASH_COMMANDS,
    _TUI_SLASH_COMMAND_BY_NAME,
    _accept_tui_buffer,
    _format_model_status,
    _handle_tui_approval_command,
    _is_tui_stop_command,
    _model_candidates,
    _navigate_input_history,
    _task_running_block_message,
    dispatch_tui_command,
    handle_tui_runtime_command,
    stop_tui_job,
    switch_tui_layout,
    switch_tui_model,
)
from mlpcopilot.runtime.tui.common import (
    _channel_enabled,
    _compact_log_message,
    _display_workspace_path,
    _format_args,
    _format_size,
    _log_source_label,
    _provider_unavailable_message,
    _render_rich_ansi,
    _short,
    _tool_approval_policy,
    _write_policy,
)
from mlpcopilot.runtime.tui.input.completer import _make_tui_completer
from mlpcopilot.runtime.tui.controller import (
    TuiRuntimeController,
    _is_new_session_command,
    _reset_tui_session_view,
)
from mlpcopilot.runtime.tui.layouts.footer import (
    _footer_help_line,
    _footer_segments,
    _footer_status,
)
from mlpcopilot.runtime.tui.input.interactive_app import (
    _is_vscode_terminal,
    _run_interactive_app,
    _tui_full_screen_enabled,
)
from mlpcopilot.runtime.tui.input.keymap import (
    approval_pending_filter,
    build_tui_key_bindings,
    pager_open_filter,
    resolved_tui_keymap,
    tui_action_key_label,
)
from mlpcopilot.runtime.tui.overlays.job_picker import (
    _render_job_picker_ansi,
    job_picker_jobs,
    selected_job,
)
from mlpcopilot.runtime.tui.overlays.layout_picker import (
    _render_layout_picker_ansi,
    layout_picker_specs,
    selected_layout,
    sync_layout_picker_selection,
)
from mlpcopilot.runtime.tui.overlays.model_picker import (
    _render_model_picker_ansi,
    model_picker_models,
    selected_model,
    sync_model_picker_selection,
)
from mlpcopilot.runtime.tui.layouts.layout import (
    _active_overlay_filter,
    _render_job_picker_for_terminal,
    _render_layout_picker_for_terminal,
    _render_model_picker_for_terminal,
    _render_slash_menu_for_terminal,
    _render_tool_log_pager_for_terminal,
    _slash_menu_filter,
    build_tui_prompt_layout,
    rounded_input_frame,
    tui_style_dict,
)
from mlpcopilot.runtime.tui.layouts.layout_registry import (
    DEFAULT_TUI_LAYOUT,
    TuiLayoutSpec,
    format_tui_layouts,
    get_tui_layout_spec,
    list_tui_layout_specs,
)
from mlpcopilot.runtime.tui.input.line_fallback import _run_line_fallback
from mlpcopilot.runtime.tui.views.logs import (
    _mcp_count_label,
    _record_tui_log_message,
    _render_tool_log_pager_ansi,
    _tool_log_panel_title,
    _tool_log_renderable,
    capture_tui_logs,
    format_tool_log_text,
    load_persisted_tool_log,
    save_persisted_tool_log,
)
from mlpcopilot.runtime.tui.overlays import (
    APPROVAL_OVERLAY,
    JOB_PICKER_OVERLAY,
    LAYOUT_PICKER_OVERLAY,
    MODEL_PICKER_OVERLAY,
    PAGER_OVERLAY,
    TOOL_LOG_PAGER_OVERLAY,
    TuiOverlaySpec,
    active_tui_overlay,
    active_tui_overlay_id,
    get_tui_overlay_spec,
    is_tui_overlay_esc_closable,
)
from mlpcopilot.runtime.tui.layouts.render import (
    _render_body_ansi,
    _render_status_ansi,
    render_tui,
    render_tui_body,
)
from mlpcopilot.runtime.tui.layouts.body_layout import (
    render_approval_focus_body,
    render_campaign_focus_body,
    render_compact_body,
    render_four_pane_body,
)
from mlpcopilot.runtime.tui.layouts.render_data import TuiRenderData, collect_tui_render_data
from mlpcopilot.runtime.tui.runtime_factory import (
    TuiRuntimeBundle,
    TuiUnavailableProvider,
    build_tui_agent_loop,
)
from mlpcopilot.runtime.tui.views.session_view import _load_session_chat
from mlpcopilot.runtime.tui.overlays.slash_menu import (
    _render_slash_menu_ansi,
    input_text_before_cursor,
    slash_menu_candidates,
    slash_menu_selected_command,
    slash_menu_visible,
)
from mlpcopilot.runtime.tui.queue_items import TuiQueuedInput
from mlpcopilot.runtime.tui.state import (
    _CHAT_HISTORY_LIMIT,
    RuntimeTuiState,
    ToolLogEntry,
    TuiMessage,
)
from mlpcopilot.runtime.tui.stores.state_store import (
    apply_persisted_tui_state,
    load_tui_state,
    save_tui_state,
    tui_state_path,
)
