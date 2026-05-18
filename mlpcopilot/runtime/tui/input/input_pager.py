"""Pager and chat scroll actions for the TUI input controller."""

from __future__ import annotations

import shutil

from mlpcopilot.runtime.tui.overlays import is_tui_overlay_esc_closable
from mlpcopilot.runtime.tui.views.chat import (
    _chat_scroll_metrics,
    _open_pager_for_latest_message,
)


class TuiPagerActions:
    """Mixin containing chat and pager navigation actions."""

    def chat_scroll_metrics(self) -> tuple[int, int]:
        columns, rows = shutil.get_terminal_size(fallback=(120, 30))
        return _chat_scroll_metrics(
            self.state,
            terminal_width=columns,
            terminal_height=rows,
            has_pending=self.has_pending_approval(),
        )

    def move_chat_page(self, direction: int) -> None:
        page, max_scroll = self.chat_scroll_metrics()
        self.state.chat_scroll = min(
            max(0, self.state.chat_scroll + (direction * page)),
            max_scroll,
        )
        self.invalidate()

    def move_pager_scroll(self, delta: int) -> None:
        if self.overlay_is("tool_log_pager"):
            self.state.tool_log_pager_scroll = max(0, self.state.tool_log_pager_scroll + delta)
        else:
            self.state.pager_scroll = max(0, self.state.pager_scroll + delta)
        self.invalidate()

    def page_size(self) -> int:
        _columns, rows = shutil.get_terminal_size(fallback=(120, 30))
        return max(4, rows - 10)

    def toggle_pager(self) -> None:
        if self.state.is_overlay_open("pager"):
            self.state.close_overlay("pager")
        elif _open_pager_for_latest_message(self.state):
            self.state.open_overlay("pager")
        else:
            self.state.add_chat("system", "No message is available for the pager.")
        self.invalidate()

    def close_pager(self) -> None:
        self.state.close_overlay("pager")
        self.invalidate()

    def toggle_tool_log_pager(self) -> None:
        if self.state.is_overlay_open("tool_log_pager"):
            self.state.close_overlay("tool_log_pager")
        elif self.state.tool_log:
            self.state.tool_log_pager_scroll = 0
            self.state.open_overlay("tool_log_pager")
        else:
            self.state.add_chat("system", "No tool log entries are available.")
        self.invalidate()

    def close_active_pager(self) -> None:
        overlay_id = self.active_overlay_id()
        if is_tui_overlay_esc_closable(overlay_id):
            self.state.close_overlay(overlay_id)
        self.invalidate()

    def pager_home(self) -> None:
        if self.overlay_is("tool_log_pager"):
            self.state.tool_log_pager_scroll = 0
        else:
            self.state.pager_scroll = 0
        self.invalidate()

    def pager_end(self) -> None:
        if self.overlay_is("tool_log_pager"):
            self.state.tool_log_pager_scroll = 10**9
        else:
            self.state.pager_scroll = 10**9
        self.invalidate()
