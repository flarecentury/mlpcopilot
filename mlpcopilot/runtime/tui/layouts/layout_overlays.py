"""Prompt-toolkit overlay filters and terminal render wrappers."""

from __future__ import annotations

import shutil
from typing import Any

from prompt_toolkit.filters import Condition

from mlpcopilot.runtime.tui.overlays import active_tui_overlay_id
from mlpcopilot.runtime.tui.overlays.approvals import _first_pending_approval
from mlpcopilot.runtime.tui.overlays.job_picker import (
    _render_job_picker_ansi,
    job_picker_jobs,
)
from mlpcopilot.runtime.tui.overlays.layout_picker import (
    _render_layout_picker_ansi,
    layout_picker_specs,
)
from mlpcopilot.runtime.tui.overlays.model_picker import _render_model_picker_ansi
from mlpcopilot.runtime.tui.overlays.slash_menu import (
    _render_slash_menu_ansi,
    input_text_before_cursor,
    slash_menu_visible,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.views.logs import _render_tool_log_pager_ansi


def _has_pending_approval(config: Any, state: RuntimeTuiState) -> bool:
    return _first_pending_approval(config, session_id=state.active_session_id) is not None


def _active_overlay_filter(config: Any, state: RuntimeTuiState, overlay_id: str) -> Condition:
    return Condition(
        lambda: active_tui_overlay_id(
            approval_pending=_has_pending_approval(config, state),
            pager_open=state.is_overlay_open("pager"),
            tool_log_pager_open=state.is_overlay_open("tool_log_pager"),
            overlay_stack=state.overlay_stack,
        )
        == overlay_id
    )


def _slash_menu_filter(config: Any, state: RuntimeTuiState, input_box: Any) -> Condition:
    return Condition(
        lambda: active_tui_overlay_id(
            approval_pending=_has_pending_approval(config, state),
            pager_open=state.is_overlay_open("pager"),
            tool_log_pager_open=state.is_overlay_open("tool_log_pager"),
            overlay_stack=state.overlay_stack,
        )
        is None
        and slash_menu_visible(state, input_text_before_cursor(input_box), config)
    )


def _render_tool_log_pager_for_terminal(state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    return _render_tool_log_pager_ansi(
        state,
        width=max(20, columns - 8),
        height=max(6, rows - 8),
    )


def _render_slash_menu_for_terminal(config: Any, state: RuntimeTuiState, input_box: Any) -> str:
    columns, _rows = shutil.get_terminal_size(fallback=(120, 30))
    return _render_slash_menu_ansi(
        state,
        input_text_before_cursor(input_box),
        width=max(20, columns - 8),
        height=8,
        config=config,
    )


def _render_job_picker_for_terminal(config: Any, state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    return _render_job_picker_ansi(
        state,
        job_picker_jobs(config.workspace_path),
        width=max(20, columns - 8),
        height=max(6, rows - 8),
    )


def _render_layout_picker_for_terminal(state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    return _render_layout_picker_ansi(
        state,
        layout_picker_specs(),
        width=max(20, columns - 8),
        height=max(6, rows - 8),
    )


def _render_model_picker_for_terminal(config: Any, state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    return _render_model_picker_ansi(
        state,
        config,
        width=max(20, columns - 8),
        height=max(6, rows - 8),
    )
