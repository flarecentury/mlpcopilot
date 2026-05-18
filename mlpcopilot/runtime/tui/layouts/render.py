"""Rich layout rendering for the MLP Copilot TUI."""

from __future__ import annotations

import shutil
from contextlib import suppress
from typing import TYPE_CHECKING

from rich.layout import Layout

from mlpcopilot.runtime.jobs import JobStore
from mlpcopilot.runtime.tui.common import _render_rich_ansi
from mlpcopilot.runtime.tui.layouts.body_layout import render_tui_body
from mlpcopilot.runtime.tui.layouts.footer import _footer_help_line
from mlpcopilot.runtime.tui.layouts.render_data import collect_tui_render_data
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.views.logs import load_persisted_tool_log

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def render_tui(config: Config, state: RuntimeTuiState | None = None) -> Layout:
    """Render the four-pane MLP Copilot runtime view."""
    if state is None:
        with suppress(OSError):
            JobStore(config.workspace_path).reconcile_stale(mark_missing_pid=True)
        state = RuntimeTuiState()
        state.tool_log = load_persisted_tool_log(
            config.workspace_path,
            session_id=state.active_session_id,
            fallback_to_global=False,
        )
    data = collect_tui_render_data(config, session_id=state.active_session_id)

    layout = Layout(name="root")
    layout.split_column(
        render_tui_body(config, state, data=data),
        Layout(
            _footer_help_line(config, state, data.pending),
            name="status",
            size=1,
        ),
    )

    return layout

def _render_body_ansi(config: Config, state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    body_height = max(10, rows - 4)
    return _render_rich_ansi(
        render_tui_body(
            config,
            state,
            viewport_width=columns,
            viewport_height=body_height,
        ),
        width=columns,
        height=body_height,
    )

def _render_status_ansi(config: Config, state: RuntimeTuiState) -> str:
    columns, _rows = shutil.get_terminal_size(fallback=(120, 30))
    pending = collect_tui_render_data(config, session_id=state.active_session_id).pending
    return _render_rich_ansi(
        _footer_help_line(config, state, pending),
        width=columns,
        height=1,
    )
