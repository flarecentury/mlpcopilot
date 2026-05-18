"""Compact Rich body layout."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.layout import Layout
from rich.panel import Panel

from mlpcopilot.runtime.tui.layouts.body_common import (
    approval_wrapped_body,
    compact_chat_viewport_size,
    compact_content_width,
    compact_tool_log_viewport_height,
    split_half_content_width,
)
from mlpcopilot.runtime.tui.layouts.render_data import TuiRenderData, collect_tui_render_data
from mlpcopilot.runtime.tui.overlays.approvals import _approvals_panel_title, _approvals_renderable
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.views.artifacts_panel import (
    _artifacts_panel_title,
    _artifacts_renderable,
)
from mlpcopilot.runtime.tui.views.chat import _chat_panel_title, _chat_renderable
from mlpcopilot.runtime.tui.views.logs import _tool_log_panel_title, _tool_log_renderable

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def render_compact_body(
    config: Config,
    state: RuntimeTuiState,
    *,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    data: TuiRenderData | None = None,
) -> Layout:
    workspace = config.workspace_path
    data = data or collect_tui_render_data(config, session_id=state.active_session_id)
    chat_width, chat_height = compact_chat_viewport_size(
        viewport_width,
        viewport_height,
        has_pending=bool(data.pending),
    )
    tool_log_height = compact_tool_log_viewport_height(
        viewport_height,
        has_pending=bool(data.pending),
    )
    full_width = compact_content_width(viewport_width)
    bottom_width = split_half_content_width(viewport_width)

    layout = Layout(name="body")
    body = approval_wrapped_body(config, layout, data, state)
    body.split_column(
        Layout(
            Panel(
                _chat_renderable(state, viewport_width=chat_width, viewport_height=chat_height),
                title=_chat_panel_title(config, state),
                border_style="cyan",
            ),
            name="chat",
            ratio=3,
            minimum_size=8,
        ),
        Layout(
            Panel(
                _tool_log_renderable(
                    state,
                    data.mcp_servers,
                    data.skills,
                    state.mcp_status,
                    viewport_height=tool_log_height,
                    viewport_width=full_width,
                ),
                title=_tool_log_panel_title(data.mcp_servers, data.skills, state.mcp_status),
                border_style="magenta",
            ),
            name="tools",
            ratio=1,
            minimum_size=4,
        ),
        Layout(name="bottom", ratio=1, minimum_size=5),
    )
    body["bottom"].split_row(
        Layout(
            Panel(
                _artifacts_renderable(data.runs, data.recent_files, data.artifacts_display),
                title=_artifacts_panel_title(workspace, data.artifacts_display),
                border_style="green",
            ),
            name="artifacts",
        ),
        Layout(
            Panel(
                _approvals_renderable(data.pending, data.decisions, viewport_width=bottom_width),
                title=_approvals_panel_title(data.pending),
                border_style="yellow",
            ),
            name="approvals",
        ),
    )
    return layout
