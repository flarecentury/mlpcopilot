"""Workspace-local persisted TUI preferences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mlpcopilot.runtime.tui.layouts.layout_registry import normalize_tui_layout_name
from mlpcopilot.runtime.tui.state import RuntimeTuiState

_TUI_STATE_PATH = Path("sessions") / "tui-state.json"


def load_tui_state(workspace: Path) -> dict[str, Any]:
    path = workspace.expanduser() / _TUI_STATE_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_persisted_tui_state(
    state: RuntimeTuiState,
    workspace: Path,
    *,
    root_session_id: str | None = None,
) -> None:
    data = load_tui_state(workspace)
    state.layout_name = normalize_tui_layout_name(str(data.get("layout_name") or state.layout_name))
    root = root_session_id or state.root_session_id
    active_sessions = data.get("active_sessions")
    if isinstance(active_sessions, dict):
        active = active_sessions.get(root)
        if isinstance(active, str) and active.strip():
            state.active_session_id = active
            return
    active = data.get("active_session_id")
    if isinstance(active, str) and active.strip():
        state.active_session_id = active


def save_tui_state(workspace: Path, state: RuntimeTuiState) -> None:
    path = workspace.expanduser() / _TUI_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_tui_state(workspace)
    active_sessions = existing.get("active_sessions")
    if not isinstance(active_sessions, dict):
        active_sessions = {}
    active_sessions[state.root_session_id] = state.active_session_id
    payload = {
        "active_session_id": state.active_session_id,
        "active_sessions": active_sessions,
        "layout_name": normalize_tui_layout_name(state.layout_name),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def tui_state_path(workspace: Path) -> Path:
    return workspace.expanduser() / _TUI_STATE_PATH
