"""Slash command menu rendering and selection helpers."""

from __future__ import annotations

from typing import Any

from mlpcopilot.command.registry import list_commands
from mlpcopilot.runtime.tui.commands.command_registry import TuiSlashCommand
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.state import RuntimeTuiState


def slash_menu_candidates(text: str, *, running: bool = False, config: object | None = None) -> list[TuiSlashCommand]:
    """Return command candidates for the current input text."""
    query = text
    if not query.startswith("/") or any(char.isspace() for char in query):
        return []
    partial = query.lower()
    return [
        command for command in list_commands(surface="tui", config=config)
        if command.name.startswith(partial)
        and (not running or command.available_during_task)
    ]


def slash_menu_visible(state: RuntimeTuiState, text: str, config: object | None = None) -> bool:
    """Return whether the transient slash menu should be shown."""
    query = text
    if state.slash_menu_suppressed_text == query:
        return False
    return bool(slash_menu_candidates(query, running=state.running, config=config))


def slash_menu_selected_command(
    state: RuntimeTuiState,
    text: str,
    config: object | None = None,
) -> TuiSlashCommand | None:
    candidates = slash_menu_candidates(text, running=state.running, config=config)
    if not candidates:
        return None
    state.slash_menu_selection %= len(candidates)
    return candidates[state.slash_menu_selection]


def _render_slash_menu_ansi(
    state: RuntimeTuiState,
    text: str,
    *,
    width: int,
    height: int,
    config: object | None = None,
) -> str:
    candidates = slash_menu_candidates(text, running=state.running, config=config)
    if not candidates:
        return ""
    state.slash_menu_selection %= len(candidates)
    rows = max(1, height - 3)
    selected = state.slash_menu_selection
    start = min(max(0, selected - rows + 1), max(0, len(candidates) - rows))
    visible = candidates[start:start + rows]
    header = "slash commands | Up/Down select | Enter confirm | Esc close"
    divider = "-" * min(width, max(8, len(header)))
    lines = [header, divider]
    for index, command in enumerate(visible, start=start):
        marker = ">" if index == selected else " "
        suffix = " <arg>" if command.takes_arg else ""
        name = f"{command.name}{suffix}"
        lines.append(
            f"{marker} {name.ljust(18)} {_short(command.description, max(20, width - 24))}"
        )
    lines.append(divider)
    return "\n".join(lines)


def input_text_before_cursor(input_box: Any) -> str:
    """Extract prompt text before cursor from a prompt_toolkit TextArea-like object."""
    buffer = getattr(input_box, "buffer", input_box)
    document = getattr(buffer, "document", None)
    before_cursor = getattr(document, "text_before_cursor", None)
    if before_cursor is not None:
        return str(before_cursor)
    return str(getattr(buffer, "text", ""))
