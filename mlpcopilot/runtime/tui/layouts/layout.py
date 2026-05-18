"""Prompt-toolkit layout assembly for the interactive TUI shell."""

from __future__ import annotations

from typing import Any

from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.layout import HSplit
from prompt_toolkit.layout import Layout as PromptLayout
from prompt_toolkit.layout.containers import ConditionalContainer, Float, FloatContainer, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.widgets import Frame

from mlpcopilot.runtime.tui.layouts.layout_input import (  # noqa: F401
    rounded_input_frame,
    tui_style_dict,
)
from mlpcopilot.runtime.tui.layouts.layout_overlays import (
    _active_overlay_filter,
    _render_job_picker_for_terminal,
    _render_layout_picker_for_terminal,
    _render_model_picker_for_terminal,
    _render_slash_menu_for_terminal,
    _render_tool_log_pager_for_terminal,
    _slash_menu_filter,
)
from mlpcopilot.runtime.tui.layouts.render import _render_body_ansi, _render_status_ansi
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.views.chat import _render_pager_ansi


def build_tui_prompt_layout(
    *,
    config: Any,
    state: RuntimeTuiState,
    input_box: Any,
) -> PromptLayout:
    """Build the prompt-toolkit root layout for the default TUI shell."""
    body = Window(
        FormattedTextControl(lambda: ANSI(_render_body_ansi(config, state))),
        wrap_lines=False,
        always_hide_cursor=True,
    )
    pager = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_pager_ansi(state))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Message Pager",
    )
    tool_log_pager = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_tool_log_pager_for_terminal(state))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Tool Log Pager",
    )
    slash_menu = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_slash_menu_for_terminal(config, state, input_box))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Slash Commands",
    )
    job_picker = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_job_picker_for_terminal(config, state))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Jobs",
    )
    layout_picker = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_layout_picker_for_terminal(state))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Layouts",
    )
    model_picker = Frame(
        Window(
            FormattedTextControl(lambda: ANSI(_render_model_picker_for_terminal(config, state))),
            wrap_lines=False,
            always_hide_cursor=True,
        ),
        title="Models",
    )
    status = Window(
        FormattedTextControl(lambda: ANSI(_render_status_ansi(config, state))),
        height=1,
        wrap_lines=False,
        always_hide_cursor=True,
    )
    root = FloatContainer(
        content=HSplit([body, rounded_input_frame(input_box), status]),
        floats=[
            Float(
                xcursor=True,
                ycursor=True,
                content=CompletionsMenu(max_height=8, scroll_offset=1),
            ),
            Float(
                top=1,
                left=2,
                right=2,
                bottom=4,
                content=ConditionalContainer(
                    pager,
                    filter=_active_overlay_filter(config, state, "pager"),
                ),
                z_index=10,
            ),
            Float(
                top=1,
                left=2,
                right=2,
                bottom=4,
                content=ConditionalContainer(
                    tool_log_pager,
                    filter=_active_overlay_filter(config, state, "tool_log_pager"),
                ),
                z_index=10,
            ),
            Float(
                left=2,
                right=2,
                bottom=4,
                height=10,
                content=ConditionalContainer(
                    slash_menu,
                    filter=_slash_menu_filter(config, state, input_box),
                ),
                z_index=20,
            ),
            Float(
                top=1,
                left=2,
                right=2,
                bottom=4,
                content=ConditionalContainer(
                    job_picker,
                    filter=_active_overlay_filter(config, state, "job_picker"),
                ),
                z_index=10,
            ),
            Float(
                top=1,
                left=2,
                right=2,
                bottom=4,
                content=ConditionalContainer(
                    layout_picker,
                    filter=_active_overlay_filter(config, state, "layout_picker"),
                ),
                z_index=10,
            ),
            Float(
                top=1,
                left=2,
                right=2,
                bottom=4,
                content=ConditionalContainer(
                    model_picker,
                    filter=_active_overlay_filter(config, state, "model_picker"),
                ),
                z_index=10,
            ),
        ],
    )
    return PromptLayout(root, focused_element=input_box)
