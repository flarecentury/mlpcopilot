"""Prompt-toolkit input frame styling for the TUI."""

from __future__ import annotations

from typing import Any

from prompt_toolkit.layout import HSplit, VSplit
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl


def rounded_input_frame(body: Any) -> Any:
    """Wrap the input widget in the current rounded input frame."""
    border_style = "class:input-frame.border"
    label_style = "class:input-frame.label"
    title = " Input "
    return HSplit(
        [
            VSplit(
                [
                    Window(char="╭", width=1, height=1, style=border_style),
                    Window(char="─", height=1, style=border_style),
                    Window(
                        FormattedTextControl(title),
                        width=len(title),
                        height=1,
                        style=label_style,
                    ),
                    Window(char="─", height=1, style=border_style),
                    Window(char="╮", width=1, height=1, style=border_style),
                ],
                height=1,
            ),
            VSplit(
                [
                    Window(char="│", width=1, style=border_style),
                    body,
                    Window(char="│", width=1, style=border_style),
                ]
            ),
            VSplit(
                [
                    Window(char="╰", width=1, height=1, style=border_style),
                    Window(char="─", height=1, style=border_style),
                    Window(char="╯", width=1, height=1, style=border_style),
                ],
                height=1,
            ),
        ],
        style="class:input-frame",
    )


def tui_style_dict() -> dict[str, str]:
    return {
        "input-frame": "fg:#38bdf8",
        "input-frame.border": "fg:#38bdf8",
        "input-frame.label": "fg:#e0f2fe bold",
    }
