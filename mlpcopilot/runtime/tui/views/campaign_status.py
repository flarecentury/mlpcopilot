"""Workspace campaign status loading for the TUI Companion pane."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.views.display_document import is_display_document


def load_campaign_status_display(
    workspace: Path,
    status_paths: Sequence[str],
) -> dict[str, Any] | None:
    """Load the first configured campaign status file inside the workspace."""
    workspace = workspace.expanduser().resolve(strict=False)
    for raw_path in status_paths:
        path = _resolve_workspace_status_path(workspace, raw_path)
        if path is None or not path.is_file():
            continue
        display = _load_status_file(workspace, path)
        if display is not None:
            return display
    return None


def _resolve_workspace_status_path(workspace: Path, raw_path: str) -> Path | None:
    if not raw_path.strip():
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve(strict=False)
    if resolved == workspace or workspace in resolved.parents:
        return resolved
    return None


def _load_status_file(workspace: Path, path: Path) -> dict[str, Any] | None:
    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rel_path = _relative_status_path(workspace, path)
    if suffix == ".json":
        return _json_status_display(text, rel_path)
    if suffix == ".md":
        return _text_status_display(text, rel_path, block_type="markdown")
    if suffix == ".txt":
        return _text_status_display(text, rel_path, block_type="log")
    return None


def _json_status_display(text: str, rel_path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if is_display_document(data):
        return data
    return campaign_status_to_display(data, rel_path)


def campaign_status_to_display(status: dict[str, Any], rel_path: str) -> dict[str, Any]:
    """Convert a status JSON object into a generic display document."""
    key_values = _status_key_values(status, rel_path)
    body: list[dict[str, Any]] = []
    if key_values:
        body.append({"type": "key_values", "items": key_values})

    jobs = _status_jobs(status.get("jobs"))
    if jobs:
        body.append({"type": "table", "columns": ["Job", "Kind", "Status"], "rows": jobs})

    blockers = _status_list(status.get("blockers"))
    if blockers:
        body.append({"type": "list", "title": "Blockers", "items": blockers})

    artifacts = _status_list(status.get("artifacts"))
    if artifacts:
        body.append({"type": "list", "title": "Artifacts", "items": artifacts})

    return {
        "kind": "display_document",
        "title": "Campaign",
        "summary": _status_summary(status, rel_path),
        "body": body or [{"type": "markdown", "text": f"Status source: `{rel_path}`"}],
    }


def _status_key_values(status: dict[str, Any], rel_path: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    _append_kv(items, "Campaign", status.get("campaign_id") or status.get("id"))
    _append_kv(items, "State", status.get("state") or status.get("status"))
    _append_kv(items, "Iteration", status.get("iteration"))
    _append_kv(items, "Dataset", _reference_text(status.get("dataset")))
    _append_kv(items, "Checkpoint", _reference_text(status.get("checkpoint")))
    _append_kv(items, "Next", _reference_text(status.get("next_decision")))
    _append_kv(items, "Source", rel_path)
    return items


def _append_kv(items: list[dict[str, str]], key: str, value: Any) -> None:
    if value is None or value == "":
        return
    items.append({"key": key, "value": str(value)})


def _status_summary(status: dict[str, Any], rel_path: str) -> str:
    head = status.get("campaign_id") or status.get("id") or rel_path
    parts = [str(head)]
    state = status.get("state") or status.get("status")
    if state:
        parts.append(str(state))
    iteration = status.get("iteration")
    if iteration is not None:
        parts.append(f"iter {iteration}")
    return " | ".join(parts)


def _status_jobs(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    rows: list[list[str]] = []
    for item in value[:8]:
        if isinstance(item, dict):
            rows.append(
                [
                    str(item.get("job_id") or item.get("id") or "-"),
                    str(item.get("kind") or item.get("type") or "-"),
                    str(item.get("status") or item.get("state") or "-"),
                ]
            )
        else:
            rows.append([_short(str(item), 40), "-", "-"])
    return rows


def _status_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_reference_text(item) for item in value[:12]]


def _reference_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dict):
        preferred = (
            value.get("summary")
            or value.get("message")
            or value.get("label")
            or value.get("path")
            or value.get("uri")
            or value.get("artifact_id")
            or value.get("approval_id")
            or value.get("job_id")
            or value.get("id")
        )
        details = []
        if preferred in {value.get("path"), value.get("uri")} and value.get("artifact_id"):
            details.append(f"artifact={value['artifact_id']}")
        for key in ("status", "state", "kind", "type"):
            if value.get(key):
                details.append(str(value[key]))
        text = str(preferred) if preferred else json.dumps(value, ensure_ascii=False, sort_keys=True)
        if details:
            text = f"{text} ({', '.join(details)})"
        return _short(text, 120)
    if isinstance(value, list):
        return _short(", ".join(_reference_text(item) for item in value[:4]), 120)
    return _short(str(value), 120)


def _text_status_display(text: str, rel_path: str, *, block_type: str) -> dict[str, Any]:
    return {
        "kind": "display_document",
        "title": "Campaign",
        "summary": f"Campaign status: {rel_path}",
        "body": [
            {"type": "key_values", "items": [{"key": "Source", "value": rel_path}]},
            {"type": block_type, "text": text},
        ],
    }


def _relative_status_path(workspace: Path, path: Path) -> str:
    try:
        return path.relative_to(workspace).as_posix()
    except ValueError:
        return path.as_posix()
