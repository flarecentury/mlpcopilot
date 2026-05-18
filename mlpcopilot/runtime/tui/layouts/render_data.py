"""Data snapshot helpers for TUI rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mlpcopilot.runtime.approval import ApprovalRecord
from mlpcopilot.runtime.artifacts import ArtifactIndex, RunManifest
from mlpcopilot.runtime.tui.overlays.approvals import (
    _list_decision_approvals,
    _list_pending_approvals,
)
from mlpcopilot.runtime.tui.views.campaign_status import load_campaign_status_display
from mlpcopilot.runtime.workspace import configured_mcp_servers, discovered_skills
from mlpcopilot.runtime.workstate import format_workstate_summary_display, get_active_project
from mlpcopilot.session.manager import SessionManager

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

_UI_STATE_CACHE: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
_DPGEN_PROJECTION_REFRESH_CACHE: dict[str, tuple[int, int, int, int, int, int]] = {}


@dataclass(frozen=True, slots=True)
class TuiRenderData:
    pending: list[ApprovalRecord]
    decisions: list[ApprovalRecord]
    runs: list[RunManifest]
    recent_files: list[Any]
    mcp_servers: list[Any]
    skills: list[Any]
    artifacts_display: dict[str, Any] | None = None
    companion_display: dict[str, Any] | None = None
    workstate_display: str = ""


def collect_tui_render_data(config: Config, session_id: str | None = None) -> TuiRenderData:
    workspace = config.workspace_path
    session = _load_session(workspace, session_id)
    artifacts_display, companion_display = _load_active_display_docs(workspace, session)
    if companion_display is None:
        companion_display = load_campaign_status_display(workspace, config.tui.campaign_status_paths)
    if artifacts_display:
        runs: list[RunManifest] = []
    else:
        artifacts = ArtifactIndex(workspace)
        runs = artifacts.list_runs()
    return TuiRenderData(
        pending=_list_pending_approvals(config, session_id=session_id),
        decisions=_list_decision_approvals(config, session_id=session_id),
        runs=runs,
        recent_files=[],
        mcp_servers=configured_mcp_servers(config),
        skills=discovered_skills(config, workspace),
        artifacts_display=artifacts_display,
        companion_display=companion_display,
        workstate_display=format_workstate_summary_display(session) if session is not None else "",
    )


def _load_session(workspace: Path, session_id: str | None):
    if not session_id:
        return None
    return SessionManager(workspace).get_or_create(session_id)


def _load_active_display_docs(workspace: Path, session: Any | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    pointer = get_active_project(session) if session is not None else None
    if pointer is not None:
        return _load_project_display_docs(
            workspace,
            pointer.project_id,
            pointer.run_id,
            fallback_to_project_active_run=True,
        )

    project = _active_project(workspace)
    if not project:
        return None, None
    project_id = str(project.get("project_id") or "")
    if not project_id:
        return None, None
    return _load_project_display_docs(
        workspace,
        project_id,
        str(project.get("active_run_id") or ""),
        fallback_to_project_active_run=False,
    )


def _load_project_display_docs(
    workspace: Path,
    project_id: str,
    run_id: str,
    *,
    fallback_to_project_active_run: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    project_dir = workspace / "projects" / project_id
    if not run_id and fallback_to_project_active_run:
        project = _load_json_object(project_dir / "project.json") or {}
        run_id = str(project.get("active_run_id") or "")
    if isinstance(run_id, str) and run_id:
        _maybe_refresh_run_display_docs(workspace, project_id, run_id)
        run_ui_dir = project_dir / "runs" / run_id / "ui"
        artifacts_display = _load_json_object(run_ui_dir / "artifacts.display.json")
        companion_display = _load_json_object(run_ui_dir / "companion.display.json")
        if artifacts_display or companion_display:
            return artifacts_display, companion_display
    project_ui_dir = project_dir / "ui"
    return (
        _load_json_object(project_ui_dir / "artifacts.display.json"),
        _load_json_object(project_ui_dir / "companion.display.json"),
    )


def _maybe_refresh_run_display_docs(workspace: Path, project_id: str, run_id: str) -> None:
    run_dir = workspace / "projects" / project_id / "runs" / run_id
    run = _load_json_object(run_dir / "run.json")
    if not run or run.get("backend") != "dpgen":
        return
    backend_workdir = _run_backend_path(run_dir, run)
    record_path = backend_workdir / "record.dpgen"
    record_stat = _stat_or_none(record_path)
    if record_stat is None:
        return

    display_paths = (
        run_dir / "run_state.json",
        run_dir / "ui" / "artifacts.display.json",
        run_dir / "ui" / "companion.display.json",
    )
    display_stats = [_stat_or_none(path) for path in display_paths]
    signature = (
        record_stat.st_mtime_ns,
        record_stat.st_size,
        display_stats[0].st_mtime_ns if display_stats[0] else -1,
        display_stats[0].st_size if display_stats[0] else -1,
        display_stats[1].st_mtime_ns if display_stats[1] else -1,
        display_stats[2].st_mtime_ns if display_stats[2] else -1,
    )
    cache_key = str(run_dir.resolve(strict=False))
    if _DPGEN_PROJECTION_REFRESH_CACHE.get(cache_key) == signature:
        return
    if all(stat is not None and stat.st_mtime_ns >= record_stat.st_mtime_ns for stat in display_stats):
        _DPGEN_PROJECTION_REFRESH_CACHE[cache_key] = signature
        return

    try:
        from mlpcopilot.plugins.dpgen_adapter.projector import project_dpgen_run

        project_dpgen_run(workspace, project_id, run_id)
    except Exception:
        _DPGEN_PROJECTION_REFRESH_CACHE[cache_key] = signature
        return
    for path in display_paths:
        _UI_STATE_CACHE.pop(str(path), None)
    _UI_STATE_CACHE.pop(str(run_dir / "run.json"), None)


def _run_backend_path(run_dir: Path, run: dict[str, Any]) -> Path:
    raw = str(run.get("backend_workdir") or "backend/dpgen")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    return path


def _stat_or_none(path: Path):
    try:
        return path.stat()
    except OSError:
        return None


def _active_project(workspace: Path) -> dict[str, Any] | None:
    projects_dir = workspace / "projects"
    candidates: list[dict[str, Any]] = []
    for path in sorted(projects_dir.glob("*/project.json")):
        project = _load_json_object(path)
        if project:
            candidates.append(project)
    if not candidates:
        return None
    with_active = [item for item in candidates if item.get("active_run_id")]
    pool = with_active or candidates
    pool.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return pool[0]


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        stat = path.stat()
    except OSError:
        _UI_STATE_CACHE.pop(str(path), None)
        return None
    signature = (stat.st_mtime_ns, stat.st_size)
    cached = _UI_STATE_CACHE.get(str(path))
    if cached and cached[0] == signature:
        return cached[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    _UI_STATE_CACHE[str(path)] = (signature, data)
    return data
