"""Read-only local slash command formatters for the TUI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mlpcopilot.runtime.artifacts import ArtifactIndex
from mlpcopilot.runtime.jobs import JobRecord, JobStore
from mlpcopilot.runtime.tui.commands.command_approvals import _approval_tool_detail
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.input.keymap import tui_action_key_label
from mlpcopilot.runtime.tui.overlays.approvals import _list_pending_approvals
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry
from mlpcopilot.runtime.tui.views.logs import format_tool_log_text, load_persisted_tool_log

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def _format_tui_runs(config: Config) -> str:
    runs = ArtifactIndex(config.workspace_path).list_runs()
    if not runs:
        return "Runs: none."
    lines = ["Recent runs:"]
    for manifest in runs[:20]:
        source = f" source={manifest.source}" if manifest.source else ""
        evidence = _format_run_evidence_counts(manifest)
        lines.append(f"- {manifest.run_id} {manifest.created_at}{source}{evidence}")
    return "\n".join(lines)


def _format_tui_jobs(config: Config) -> str:
    jobs = JobStore(config.workspace_path).list_jobs(limit=20)
    if not jobs:
        return "Jobs: none."
    lines = ["Recent jobs:"]
    for job in jobs:
        lines.append(_format_tui_job(job))
    return "\n".join(lines)


def _format_tui_tool_log(config: Config, state: RuntimeTuiState | None = None) -> str:
    entries = state.tool_log if state is not None and state.tool_log else []
    if not entries:
        entries = load_persisted_tool_log(
            config.workspace_path,
            limit=20,
            session_id=state.active_session_id if state is not None else None,
            fallback_to_global=state is None,
        )
    return format_tool_log_text(
        entries,
        limit=20,
        session_id=state.active_session_id if state is not None else None,
    )


def _format_tui_raw_tool_result(
    config: Config,
    state: RuntimeTuiState | None = None,
    selector: str = "",
    *,
    limit: int = 8000,
) -> str:
    entries = state.tool_log if state is not None and state.tool_log else []
    if not entries:
        entries = load_persisted_tool_log(
            config.workspace_path,
            limit=200,
            session_id=state.active_session_id if state is not None else None,
            fallback_to_global=state is None,
        )
    entry = _select_raw_tool_entry(entries, selector)
    if entry is None:
        return "Raw tool result: none. Run an MCP tool or a large-output tool first."
    path = _resolve_raw_tool_path(config.workspace_path, entry.raw_path)
    if path is None or not path.exists():
        return f"Raw tool result missing: {entry.raw_path}"
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > limit
    if truncated:
        text = text[:limit].rstrip() + "\n\n... (raw result truncated; open the path for full output)"
    call_id = f" call_id={entry.call_id}" if entry.call_id else ""
    return (
        f"Raw tool result for {entry.name}{call_id}\n"
        f"Path: {entry.raw_path}\n\n"
        f"{text}"
    )


def _format_tui_history(
    state: RuntimeTuiState | None,
    count_text: str = "",
    *,
    config: Any | None = None,
) -> str:
    if state is None or not state.chat:
        return "History: none."
    limit = _history_limit(count_text)
    recent = state.chat[-limit:]
    lines = [f"Recent history ({len(recent)}/{len(state.chat)}):"]
    for index, message in enumerate(recent, start=len(state.chat) - len(recent) + 1):
        content = " ".join(message.content.split())
        lines.append(f"{index}. {message.role}: {_short(content, 120)}")
    lines.append(f"Open the latest full message with {tui_action_key_label(config, 'pager')}.")
    return "\n".join(lines)


def _history_limit(count_text: str, *, default: int = 10, maximum: int = 50) -> int:
    if not count_text.strip():
        return default
    try:
        value = int(count_text.strip())
    except ValueError:
        return default
    return min(max(1, value), maximum)


def _select_raw_tool_entry(
    entries: list[ToolLogEntry],
    selector: str = "",
) -> ToolLogEntry | None:
    wanted = selector.strip()
    candidates = [entry for entry in entries if entry.raw_path]
    if not candidates:
        return None
    if not wanted or wanted == "last":
        return candidates[-1]
    for entry in reversed(candidates):
        if entry.call_id == wanted or (entry.call_id and entry.call_id.startswith(wanted)):
            return entry
        raw_name = Path(entry.raw_path).name
        raw_stem = Path(entry.raw_path).stem
        if wanted in {entry.raw_path, raw_name, raw_stem}:
            return entry
    return None


def _resolve_raw_tool_path(workspace: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    workspace = workspace.expanduser().resolve()
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved == workspace or workspace in resolved.parents:
        return resolved
    return None


def _format_tui_job(job: JobRecord) -> str:
    pid = f" pid={job.pid}" if job.pid is not None else ""
    log = f" log={job.log_path}" if job.log_path else ""
    return f"- {job.job_id} {job.status} {job.kind} {_short_job_command(job.command)}{pid}{log}"


def _short_job_command(command: str, limit: int = 80) -> str:
    command = command.strip()
    if len(command) <= limit:
        return command
    return command[: limit - 1].rstrip() + "…"


def _format_tui_artifacts(config: Config, run_id: str) -> str:
    run_id = run_id.strip()
    if not run_id:
        return "Usage: /artifacts <run_id>"
    try:
        manifest = ArtifactIndex(config.workspace_path).load(run_id)
    except (FileNotFoundError, ValueError) as exc:
        return str(exc)

    lines = [f"Artifacts for {manifest.run_id}:"]
    if manifest.artifacts:
        for item in manifest.artifacts:
            lines.append(f"- {_format_artifact_item(item)}")
    else:
        lines.append("- none")
    if manifest.metrics:
        lines.append("Metrics:")
        for item in manifest.metrics:
            lines.append(f"- {_format_metric_item(item)}")
    lines.extend(_format_lineage_lines(manifest.lineage))
    if manifest.decisions:
        lines.append("Decisions:")
        for item in manifest.decisions:
            lines.append(f"- {_format_decision_item(item)}")
    elif manifest.approval:
        lines.append("Decisions:")
        lines.append(f"- {_format_decision_item(manifest.approval)}")
    if manifest.outputs:
        lines.append("Outputs:")
        for item in manifest.outputs:
            lines.append(f"- {_format_evidence_value(item)}")
    return "\n".join(lines)


def _format_run_evidence_counts(manifest: Any) -> str:
    parts: list[str] = []
    if manifest.artifacts:
        parts.append(f"artifacts={len(manifest.artifacts)}")
    if manifest.metrics:
        parts.append(f"metrics={len(manifest.metrics)}")
    if manifest.decisions:
        parts.append(f"decisions={len(manifest.decisions)}")
    approval = _format_approval_summary(manifest.approval)
    if approval:
        parts.append(f"approval={approval}")
    if manifest.errors:
        parts.append(f"errors={len(manifest.errors)}")
    return f" {' '.join(parts)}" if parts else ""


def _format_approval_summary(approval: Any) -> str:
    if not approval:
        return ""
    if isinstance(approval, dict):
        status = approval.get("status")
        approval_id = approval.get("approval_id") or approval.get("id")
        if status:
            return str(status)
        if approval_id:
            return str(approval_id)
    return _short(str(approval), 40)


def _format_artifact_item(item: Any) -> str:
    if not isinstance(item, dict):
        return _format_evidence_value(item)
    parts: list[str] = []
    identity = _evidence_identity(item)
    if identity:
        parts.append(identity)
    artifact_type = item.get("type") or item.get("kind")
    if artifact_type and str(artifact_type) not in parts:
        parts.append(str(artifact_type))
    path = item.get("path") or item.get("uri")
    if path and str(path) not in parts:
        parts.append(str(path))
    digest = item.get("sha256") or item.get("hash") or item.get("checksum")
    if digest:
        parts.append(f"sha256={_short_digest(str(digest))}")
    producer = item.get("produced_by") or item.get("producer") or item.get("source")
    if producer:
        parts.append(f"producer={producer}")
    return " ".join(parts) if parts else _format_evidence_value(item)


def _format_metric_item(item: Any) -> str:
    if not isinstance(item, dict):
        return _format_evidence_value(item)
    name = item.get("name") or item.get("metric") or item.get("key")
    value = item.get("value")
    parts: list[str] = []
    if name and value is not None:
        head = f"{name}={value}"
        if item.get("unit"):
            head = f"{head} {item['unit']}"
        parts.append(head)
    elif name:
        parts.append(str(name))
    source = item.get("source_artifact") or item.get("artifact_id") or item.get("source") or item.get("path")
    if source:
        parts.append(f"source={source}")
    return " ".join(parts) if parts else _format_evidence_value(item)


def _format_decision_item(item: Any) -> str:
    if not isinstance(item, dict):
        return _format_evidence_value(item)
    approval_id = item.get("approval_id") or item.get("id")
    status = item.get("status")
    action = item.get("action_type") or item.get("title")
    parts = [str(value) for value in (approval_id, status, action) if value]
    return " ".join(parts) if parts else _format_evidence_value(item)


def _format_lineage_lines(lineage: dict[str, Any]) -> list[str]:
    if not lineage:
        return []
    lines = ["Lineage:"]
    preferred = ["parents", "parent_runs", "inputs", "source_artifacts", "derived_from"]
    seen: set[str] = set()
    for key in preferred:
        if key in lineage:
            lines.append(f"- {key}={_format_lineage_value(lineage[key])}")
            seen.add(key)
    for key in sorted(set(lineage) - seen):
        lines.append(f"- {key}={_format_lineage_value(lineage[key])}")
    return lines


def _format_lineage_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "0"
        if all(not isinstance(item, dict | list) for item in value):
            return _short(", ".join(str(item) for item in value[:4]), 100)
        identity = _evidence_identity(value[0]) if isinstance(value[0], dict) else ""
        return f"{len(value)} first={identity}" if identity else str(len(value))
    if isinstance(value, dict):
        identity = _evidence_identity(value)
        return identity or _format_evidence_value(value)
    return _format_evidence_value(value)


def _evidence_identity(item: dict[str, Any]) -> str:
    for key in ("artifact_id", "id", "run_id", "path", "uri", "name"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _short_digest(value: str) -> str:
    return value[:12] if len(value) > 12 else value


def _format_evidence_value(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _format_tui_approvals(config: Config, state: RuntimeTuiState | None = None) -> str:
    pending = _list_pending_approvals(
        config,
        session_id=state.active_session_id if state is not None else None,
    )
    if not pending:
        return "Pending approvals: none."
    lines = ["Pending approvals:"]
    for record in pending[:20]:
        target = _approval_tool_detail(record) or record.title
        lines.append(f"- {record.approval_id} {record.action_type} {target}")
    return "\n".join(lines)
