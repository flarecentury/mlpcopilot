"""Session-to-TUI state loading helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mlpcopilot.runtime.tui.state import _CHAT_HISTORY_LIMIT, RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.session.manager import Session


def _load_session_chat(
    state: RuntimeTuiState,
    session: Session,
    limit: int = _CHAT_HISTORY_LIMIT,
) -> None:
    state.chat.clear()
    for message in session.messages[-limit:]:
        role = str(message.get("role") or "")
        if role not in {"user", "assistant", "system"}:
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            state.add_chat(role, content)
