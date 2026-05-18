"""Focused Rich body layouts for Campaign and Approvals."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.layout import Layout
from rich.panel import Panel

from mlpcopilot.runtime.tui.layouts.body_common import (
    approval_wrapped_body,
    side_chat_viewport_size,
    side_left_content_width,
    side_right_content_width,
    split_half_content_width,
    tool_log_viewport_height,
)
from mlpcopilot.runtime.tui.layouts.render_data import TuiRenderData, collect_tui_render_data
from mlpcopilot.runtime.tui.overlays.approvals import _approvals_panel_title, _approvals_renderable
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.views.artifacts_panel import (
    _artifacts_panel_title,
    _artifacts_renderable,
)
from mlpcopilot.runtime.tui.views.campaign import _campaign_panel_title, _campaign_renderable
from mlpcopilot.runtime.tui.views.chat import _chat_panel_title, _chat_renderable
from mlpcopilot.runtime.tui.views.logs import _tool_log_panel_title, _tool_log_renderable

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def render_campaign_focus_body(
    config: Config,
    state: RuntimeTuiState,
    *,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    data: TuiRenderData | None = None,
) -> Layout:
    workspace = config.workspace_path
    data = data or collect_tui_render_data(config, session_id=state.active_session_id)
    chat_width, chat_height = side_chat_viewport_size(
        viewport_width,
        viewport_height,
        has_pending=bool(data.pending),
    )
    tool_log_height = tool_log_viewport_height(
        viewport_height,
        has_pending=bool(data.pending),
    )
    left_width = side_left_content_width(viewport_width)
    right_width = side_right_content_width(viewport_width)

    layout = Layout(name="body")
    body = approval_wrapped_body(config, layout, data, state)
    body.split_row(
        Layout(name="left", ratio=2, minimum_size=40),
        Layout(name="right", ratio=3, minimum_size=50),
    )
    _left_chat_tools(
        config,
        body["left"],
        state,
        data,
        chat_width,
        chat_height,
        tool_log_height,
        left_width,
    )
    body["right"].split_column(
        Layout(
            Panel(
                _campaign_renderable(
                    workspace,
                    data.companion_display,
                    data.workstate_display,
                    stale_after_seconds=config.tui.companion_stale_after_seconds,
                ),
                title=_campaign_panel_title(),
                border_style="blue",
            ),
            name="campaign",
            ratio=3,
            minimum_size=8,
        ),
        Layout(name="right_bottom", ratio=1, minimum_size=5),
    )
    _bottom_artifacts_approvals(workspace, body["right"]["right_bottom"], data, right_width)
    return layout


def render_approval_focus_body(
    config: Config,
    state: RuntimeTuiState,
    *,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    data: TuiRenderData | None = None,
) -> Layout:
    workspace = config.workspace_path
    data = data or collect_tui_render_data(config)
    chat_width, chat_height = side_chat_viewport_size(
        viewport_width,
        viewport_height,
        has_pending=bool(data.pending),
    )
    tool_log_height = tool_log_viewport_height(
        viewport_height,
        has_pending=bool(data.pending),
    )
    left_width = side_left_content_width(viewport_width)
    right_width = side_right_content_width(viewport_width)

    layout = Layout(name="body")
    body = approval_wrapped_body(config, layout, data, state)
    body.split_row(
        Layout(name="left", ratio=2, minimum_size=38),
        Layout(name="right", ratio=3, minimum_size=46),
    )
    _left_chat_tools(
        config,
        body["left"],
        state,
        data,
        chat_width,
        chat_height,
        tool_log_height,
        left_width,
    )
    body["right"].split_column(
        Layout(
            Panel(
                _approvals_renderable(data.pending, data.decisions, viewport_width=right_width),
                title=_approvals_panel_title(data.pending),
                border_style="yellow",
            ),
            name="approvals",
            ratio=3,
            minimum_size=8,
        ),
        Layout(
            Panel(
                _artifacts_renderable(data.runs, data.recent_files, data.artifacts_display),
                title=_artifacts_panel_title(workspace, data.artifacts_display),
                border_style="green",
            ),
            name="artifacts",
            ratio=1,
            minimum_size=5,
        ),
    )
    return layout


def _left_chat_tools(
    config: Config,
    left: Layout,
    state: RuntimeTuiState,
    data: TuiRenderData,
    chat_width: int | None,
    chat_height: int | None,
    tool_log_height: int | None,
    tool_log_width: int | None,
) -> None:
    left.split_column(
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
                    viewport_width=tool_log_width,
                ),
                title=_tool_log_panel_title(data.mcp_servers, data.skills, state.mcp_status),
                border_style="magenta",
            ),
            name="tools",
            ratio=1,
            minimum_size=4,
        ),
    )


def _bottom_artifacts_approvals(
    workspace,
    target: Layout,
    data: TuiRenderData,
    viewport_width: int | None = None,
) -> None:
    pane_width = split_half_content_width(viewport_width)
    target.split_row(
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
                _approvals_renderable(data.pending, data.decisions, viewport_width=pane_width),
                title=_approvals_panel_title(data.pending),
                border_style="yellow",
            ),
            name="approvals",
        ),
    )
