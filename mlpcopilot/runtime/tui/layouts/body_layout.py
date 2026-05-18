"""Rich body layout dispatcher for the MLP Copilot TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.layout import Layout

from mlpcopilot.runtime.tui.layouts.layout_compact import render_compact_body
from mlpcopilot.runtime.tui.layouts.layout_focus import (
    render_approval_focus_body,
    render_campaign_focus_body,
)
from mlpcopilot.runtime.tui.layouts.layout_four_pane import render_four_pane_body
from mlpcopilot.runtime.tui.layouts.layout_registry import normalize_tui_layout_name
from mlpcopilot.runtime.tui.layouts.render_data import TuiRenderData
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

_BODY_RENDERERS = {
    "four_pane": render_four_pane_body,
    "compact": render_compact_body,
    "campaign_focus": render_campaign_focus_body,
    "approval_focus": render_approval_focus_body,
}


def render_tui_body(
    config: Config,
    state: RuntimeTuiState | None = None,
    *,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
    data: TuiRenderData | None = None,
) -> Layout:
    state = state or RuntimeTuiState()
    layout_name = normalize_tui_layout_name(state.layout_name)
    renderer = _BODY_RENDERERS.get(layout_name, render_four_pane_body)
    return renderer(
        config,
        state,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        data=data,
    )
