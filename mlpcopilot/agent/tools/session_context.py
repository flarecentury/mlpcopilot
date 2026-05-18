"""Async task-local agent session context."""

from __future__ import annotations

from contextvars import ContextVar, Token


_current_session_key: ContextVar[str | None] = ContextVar(
    "mlpcopilot_session_key",
    default=None,
)


def current_session_key(default: str | None = None) -> str | None:
    """Return the active agent session key for the current async task."""
    return _current_session_key.get() or default


def bind_session_key(session_key: str | None) -> Token[str | None]:
    """Bind an agent session key for tools running in the current async task."""
    return _current_session_key.set(session_key)


def reset_session_key(token: Token[str | None]) -> None:
    """Reset the active agent session key binding."""
    _current_session_key.reset(token)
