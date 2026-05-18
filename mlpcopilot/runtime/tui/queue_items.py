"""Internal queue item types for the TUI worker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TuiQueuedInput:
    """A queued TUI input, optionally hidden from the visible chat pane."""

    content: str
    show_user_message: bool = True
    source: str = "user"
    metadata: dict[str, Any] = field(default_factory=dict)
