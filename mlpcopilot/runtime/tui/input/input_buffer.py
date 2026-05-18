"""Prompt buffer helpers for the interactive TUI input controller."""

from __future__ import annotations

from typing import Any


def _accept_tui_buffer(
    buffer: Any,
    *,
    submit: Any,
    has_pending_approval: Any,
    submit_selected_approval_decision: Any,
) -> bool:
    """Accept input while letting prompt_toolkit append non-empty text to history."""
    complete_state = getattr(buffer, "complete_state", None)
    current_completion = getattr(complete_state, "current_completion", None)
    apply_completion = getattr(buffer, "apply_completion", None)
    if current_completion is not None and callable(apply_completion):
        apply_completion(current_completion)
    text = str(getattr(buffer, "text", ""))
    if has_pending_approval() and not text.strip():
        submit_selected_approval_decision()
    else:
        submit(text)
    return False


def _navigate_input_history(buffer: Any, delta: int) -> None:
    """Move through input history without stealing approval overlay navigation."""
    if getattr(buffer, "complete_state", None):
        complete = getattr(buffer, "complete_previous" if delta < 0 else "complete_next", None)
        if callable(complete):
            complete()
        return

    load_history = getattr(buffer, "load_history_if_not_yet_loaded", None)
    if callable(load_history):
        load_history()
    move = getattr(buffer, "history_backward" if delta < 0 else "history_forward", None)
    if callable(move):
        move()


def _set_buffer_text(buffer: Any, text: str) -> None:
    try:
        buffer.text = text
    except Exception:
        return
    try:
        buffer.cursor_position = len(text)
    except Exception:
        pass
