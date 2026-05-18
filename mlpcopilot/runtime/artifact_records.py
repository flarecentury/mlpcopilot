"""Project-scoped artifact record helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mlpcopilot.runtime.workspace import load_mlp_run

SECRET_KEY_RE = re.compile(r"(password|passwd|token|secret|api[_-]?key|credential|private[_-]?key)", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(
    r"(?P<prefix>['\"]?(?:password|passwd|token|secret|api[_-]?key)['\"]?\s*[:=]\s*)"
    r"(?P<value>['\"]?[^,'\"}\s]+['\"]?)",
    re.IGNORECASE,
)


def redact_secrets(value: Any) -> Any:
    """Return a copy with common credential fields redacted."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secrets(item)
        return redacted
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(lambda match: match.group("prefix") + "[REDACTED]", value)
    return value


def load_run_artifacts(workspace: Path, project_id: str, run_id: str) -> list[dict[str, Any]]:
    """Load project-scoped run artifact records."""
    workspace = workspace.expanduser()
    load_mlp_run(workspace, project_id, run_id)
    path = workspace / "projects" / project_id / "runs" / run_id / "artifacts.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def find_run_artifact(workspace: Path, project_id: str, run_id: str, selector: str) -> dict[str, Any]:
    """Find an artifact by artifact id, name, path, or relative path."""
    selector = selector.strip()
    if not selector:
        raise ValueError("Artifact selector is empty.")
    for item in load_run_artifacts(workspace, project_id, run_id):
        values = {
            str(item.get("artifact_id") or ""),
            str(item.get("name") or ""),
            str(item.get("path") or ""),
            str(item.get("relative_path") or ""),
            str(item.get("backend_relative_path") or ""),
        }
        if selector in values:
            return item
    raise FileNotFoundError(f"Artifact not found in {project_id}/{run_id}: {selector}")


def artifact_lineage(workspace: Path, project_id: str, run_id: str, selector: str) -> dict[str, Any]:
    """Return parent/child relationships from artifact records."""
    target = find_run_artifact(workspace, project_id, run_id, selector)
    target_id = str(target.get("artifact_id") or "")
    parent_ids = [str(item) for item in target.get("parents") or []]
    artifacts = load_run_artifacts(workspace, project_id, run_id)
    parents = [item for item in artifacts if str(item.get("artifact_id") or "") in parent_ids]
    children = [
        item
        for item in artifacts
        if target_id and target_id in [str(parent) for parent in item.get("parents") or []]
    ]
    return redact_secrets(
        {
        "artifact": target,
        "parents": parents,
        "children": children,
        }
    )


def artifact_attach_context(workspace: Path, project_id: str, run_id: str, selector: str) -> dict[str, Any]:
    """Build a compact context object suitable for adding to chat context."""
    artifact = find_run_artifact(workspace, project_id, run_id, selector)
    path = str(artifact.get("path") or "")
    kind = artifact.get("kind") or artifact.get("type")
    name = str(artifact.get("name") or "")
    may_contain_secrets = kind == "config" and name.startswith("machine")
    context = {
        "artifact_id": artifact.get("artifact_id"),
        "project_id": project_id,
        "run_id": run_id,
        "kind": kind,
        "role": artifact.get("role"),
        "name": name,
        "path": path,
        "relative_path": artifact.get("relative_path"),
        "metrics": artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {},
        "summary": artifact.get("summary") or "",
        "security": {
            "may_contain_secrets": may_contain_secrets,
            "redaction_required": may_contain_secrets or kind in {"config", "dispatcher_log", "error_log", "recover_log", "log"},
        },
        "context_instruction": "Use this artifact by path/id. Do not load large scientific payloads into chat unless explicitly requested. Redact credentials before quoting config or logs.",
    }
    return redact_secrets(context)
