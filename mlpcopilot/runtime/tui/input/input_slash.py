"""Slash menu actions for the TUI input controller."""

from __future__ import annotations

from typing import Any

from mlpcopilot.runtime.tui.input.input_buffer import _set_buffer_text
from mlpcopilot.runtime.tui.overlays.slash_menu import (
    input_text_before_cursor,
    slash_menu_candidates,
    slash_menu_selected_command,
    slash_menu_visible,
)


class TuiSlashMenuActions:
    """Mixin containing slash menu visibility, selection, and acceptance."""

    def slash_menu_is_open(self) -> bool:
        if self.active_overlay_id() is not None:
            return False
        return slash_menu_visible(self.state, self.input_text(), self.config)

    def input_text(self) -> str:
        if self.input_box is None:
            return ""
        return input_text_before_cursor(self.input_box)

    def move_slash_menu_selection(self, delta: int) -> None:
        candidates = slash_menu_candidates(self.input_text(), running=self.state.running, config=self.config)
        if not candidates:
            return
        self.state.slash_menu_selection = (
            self.state.slash_menu_selection + delta
        ) % len(candidates)
        self.invalidate()

    def close_slash_menu(self) -> None:
        self.state.slash_menu_suppressed_text = self.input_text()
        self.invalidate()

    def accept_slash_menu_selection(self, buffer: Any) -> None:
        command = slash_menu_selected_command(self.state, self.input_text(), self.config)
        if command is None:
            self.accept_buffer(buffer)
            return
        replacement = command.name + (" " if command.takes_arg else "")
        _set_buffer_text(buffer, replacement)
        self.state.slash_menu_suppressed_text = replacement
        self.state.slash_menu_selection = 0
        if command.takes_arg:
            self.invalidate()
            return
        if callable(validate := getattr(buffer, "validate_and_handle", None)):
            validate()
        else:
            self.submit(replacement)
            if callable(reset := getattr(buffer, "reset", None)):
                reset()
        self.invalidate()
