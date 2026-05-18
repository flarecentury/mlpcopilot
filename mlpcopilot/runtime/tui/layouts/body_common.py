"""Shared helpers for Rich TUI body layouts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.layout import Layout
from rich.panel import Panel

from mlpcopilot.runtime.tui.layouts.render_data import TuiRenderData
from mlpcopilot.runtime.tui.overlays.approvals import (
    _approval_border_style,
    _approval_focus_renderable,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def approval_wrapped_body(
    config: Config,
    layout: Layout,
    data: TuiRenderData,
    state: RuntimeTuiState,
) -> Layout:
    body = layout
    if data.pending:
        body.split_column(
            Layout(
                Panel(
                    _approval_focus_renderable(
                        data.pending[0],
                        state.approval_selection,
                        config=config,
                    ),
                    title="Approval Required",
                    border_style=_approval_border_style(data.pending[0]),
                ),
                name="approval",
                size=9,
            ),
            Layout(name="main", ratio=1),
        )
        body = body["main"]
    return body


def tool_log_viewport_height(
    viewport_height: int | None,
    *,
    has_pending: bool,
) -> int | None:
    if viewport_height is None:
        return None
    body_height = viewport_height - (9 if has_pending else 0)
    bottom_height = max(5, body_height // 4)
    top_height = max(8 if has_pending else 12, body_height - bottom_height)
    tool_panel_height = max(4, top_height // 2)
    return max(1, tool_panel_height - 2)


def four_pane_right_content_width(viewport_width: int | None) -> int | None:
    if viewport_width is None:
        return None
    return max(20, int(viewport_width * 0.40) - 4)


def split_half_content_width(viewport_width: int | None) -> int | None:
    if viewport_width is None:
        return None
    return max(20, viewport_width // 2 - 4)


def compact_content_width(viewport_width: int | None) -> int | None:
    if viewport_width is None:
        return None
    return max(20, viewport_width - 4)


def side_left_content_width(viewport_width: int | None) -> int | None:
    if viewport_width is None:
        return None
    return max(20, int(viewport_width * 0.40) - 4)


def side_right_content_width(viewport_width: int | None) -> int | None:
    if viewport_width is None:
        return None
    return max(20, int(viewport_width * 0.60) - 4)


def compact_chat_viewport_size(
    viewport_width: int | None,
    viewport_height: int | None,
    *,
    has_pending: bool,
) -> tuple[int | None, int | None]:
    if viewport_width is None or viewport_height is None:
        return None, None
    body_height = viewport_height - (9 if has_pending else 0)
    bottom_height = max(5, body_height // 5)
    tools_height = max(4, body_height // 5)
    chat_height = max(3, body_height - bottom_height - tools_height - 2)
    return max(20, viewport_width - 4), chat_height


def compact_tool_log_viewport_height(
    viewport_height: int | None,
    *,
    has_pending: bool,
) -> int | None:
    if viewport_height is None:
        return None
    body_height = viewport_height - (9 if has_pending else 0)
    tool_panel_height = max(4, body_height // 5)
    return max(1, tool_panel_height - 2)


def side_chat_viewport_size(
    viewport_width: int | None,
    viewport_height: int | None,
    *,
    has_pending: bool,
) -> tuple[int | None, int | None]:
    if viewport_width is None or viewport_height is None:
        return None, None
    body_height = viewport_height - (9 if has_pending else 0)
    chat_width = max(20, int(viewport_width * 0.40) - 4)
    tool_height = max(4, body_height // 4)
    chat_height = max(3, body_height - tool_height - 2)
    return chat_width, chat_height
