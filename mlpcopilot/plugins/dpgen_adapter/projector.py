"""Read-only DP-GEN workspace projector.

This runtime-only adapter projects DP-GEN's backend-native workdir into MLP
Copilot project/run/artifact records and generic display documents. It does
not start, stop, reset, or modify DP-GEN execution state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mlpcopilot.runtime.workspace import load_mlp_project, load_mlp_run

from .artifacts import _collect_artifacts
from .constants import LEGACY_PRODUCERS, PRODUCER
from .display import (
    _artifact_display_iteration_id,
    _artifact_display_rows,
    _artifacts_display_document,
    _compact_health_status,
    _companion_display_document,
    _workload_from_artifacts,
)
from .health import _build_health, _suggested_next
from .io import _atomic_write_json, _atomic_write_jsonl, _next_revision, _now, _read_jsonl, _rel
from .metrics import _backend_log_summary
from .record import _last_completed, _next_expected, _read_record


def project_dpgen_run(workspace: Path, project_id: str, run_id: str) -> dict[str, Any]:
    """Project one project-scoped DP-GEN run into normalized runtime/UI state files."""
    workspace = workspace.expanduser()
    project = load_mlp_project(workspace, project_id)
    run = load_mlp_run(workspace, project_id, run_id)
    if run.get("backend") != "dpgen":
        raise ValueError(f"Run backend is not dpgen: {run.get('backend')}")

    run_dir = workspace / "projects" / project_id / "runs" / run_id
    backend_workdir = run_dir / str(run.get("backend_workdir") or "backend/dpgen")
    now = _now()
    diagnostics: list[str] = []
    if not backend_workdir.exists():
        diagnostics.append(f"backend workdir not found: {backend_workdir}")
    log_summary = _backend_log_summary(backend_workdir) if backend_workdir.exists() else {}

    records, record_warnings = _read_record(backend_workdir / "record.dpgen")
    diagnostics.extend(record_warnings)
    last = _last_completed(records)
    expected = _next_expected(last)
    iter_dirs = sorted(path for path in backend_workdir.glob("iter.[0-9][0-9][0-9][0-9][0-9][0-9]") if path.is_dir())
    status = "not_started" if last is None else "projected"
    stage = "not_started" if last is None else last["phase"]

    run_state_path = run_dir / "run_state.json"
    run_state_revision = _next_revision(run_state_path)
    run_state = {
        "schema_version": 1,
        "project_id": project_id,
        "run_id": run_id,
        "revision": run_state_revision,
        "backend": "dpgen",
        "backend_workdir": _rel(backend_workdir, run_dir),
        "stage": stage,
        "phase": expected["phase"] if expected else None,
        "iteration_id": expected["iteration_id"] if expected else None,
        "status": status,
        "blocking_reason": None,
        "last_completed": last,
        "next_expected": expected,
        "observed_progress": log_summary.get("progress") or None,
        "log_summary": log_summary,
        "record_entries": len(records),
        "detected_iterations": [path.name for path in iter_dirs],
        "diagnostics": diagnostics,
        "updated_at": now,
    }
    _atomic_write_json(run_state_path, run_state)

    projected_artifacts = _collect_artifacts(workspace, project_id, run_id, backend_workdir)
    artifacts_path = run_dir / "artifacts.jsonl"
    existing_artifacts = [
        row
        for row in _read_jsonl(artifacts_path)
        if row.get("producer") not in {PRODUCER, *LEGACY_PRODUCERS}
    ]
    all_artifacts = existing_artifacts + projected_artifacts
    _atomic_write_jsonl(artifacts_path, all_artifacts)

    focus_iteration_id = expected.get("iteration_id") if isinstance(expected, dict) else None
    fallback_iteration_id = last.get("iteration_id") if isinstance(last, dict) else None
    display_iteration_id = _artifact_display_iteration_id(
        all_artifacts,
        focus_iteration_id=focus_iteration_id,
        fallback_iteration_id=fallback_iteration_id,
    )
    artifact_revision = len(all_artifacts)
    artifacts_display_path = run_dir / "ui" / "artifacts.display.json"
    artifact_model = {
        "schema_version": 1,
        "project_id": project_id,
        "run_id": run_id,
        "revision": _next_revision(artifacts_display_path),
        "updated_at": now,
        "source": {
            "artifact_index_revision": artifact_revision,
            "run_state_revision": run_state_revision,
            "approval_revision": 0,
            "backend_record_entries": len(records),
        },
        "focus_iteration_id": focus_iteration_id,
        "fallback_iteration_id": fallback_iteration_id,
        "display_iteration_id": display_iteration_id,
        "rows": _artifact_display_rows(
            all_artifacts,
            workspace,
            display_iteration_id=display_iteration_id,
        ),
    }

    health = _build_health(
        diagnostics=diagnostics,
        iter_dirs=iter_dirs,
        records=records,
        log_summary=log_summary,
    )
    suggested_next = _suggested_next(expected, run_id)
    workload = _workload_from_artifacts(all_artifacts, last.get("iteration_id") if isinstance(last, dict) else None)
    progress = {
        "last": f"{last['iter_index']}:{last['task_index']}" if isinstance(last, dict) else "-",
        "next": f"{expected['iter_index']}:{expected['task_index']}" if isinstance(expected, dict) else "-",
        "last_phase": last.get("phase") if isinstance(last, dict) else None,
        "next_phase": expected.get("phase") if isinstance(expected, dict) else None,
    }
    stage_display = {
        "iteration": (
            last.get("backend_iteration")
            if isinstance(last, dict)
            else expected.get("backend_iteration")
            if isinstance(expected, dict)
            else None
        ),
        "phase": (
            last.get("phase")
            if isinstance(last, dict)
            else expected.get("phase")
            if isinstance(expected, dict)
            else None
        ),
        "status": status,
    }
    companion_display_path = run_dir / "ui" / "companion.display.json"
    companion_model = {
        "schema_version": 1,
        "project_id": project_id,
        "run_id": run_id,
        "revision": _next_revision(companion_display_path),
        "updated_at": now,
        "source": {
            "project_revision": 1,
            "run_state_revision": run_state_revision,
            "artifact_index_revision": artifact_revision,
            "approval_revision": 0,
            "backend_record_entries": len(records),
        },
        "project": {
            "name": project.get("name") or project_id,
            "goal": project.get("target_use_case") or "",
        },
        "stage": {
            "iteration_id": expected["iteration_id"] if expected else None,
            "phase": expected["phase"] if expected else None,
            "status": status,
            "last_completed": last,
            "display": stage_display,
        },
        "progress": progress,
        "workload": workload,
        "health_status": _compact_health_status(health),
        "blocking_items": [],
        "health": health,
        "suggested_next": suggested_next,
    }

    artifacts_display = _artifacts_display_document(
        project_id=project_id,
        run_id=run_id,
        artifact_model=artifact_model,
        all_artifacts=all_artifacts,
        updated_at=now,
    )
    _atomic_write_json(artifacts_display_path, artifacts_display)

    companion_display = _companion_display_document(
        project=project,
        project_id=project_id,
        run_id=run_id,
        run_state=run_state,
        companion_model=companion_model,
        health=health,
        iter_dirs=iter_dirs,
        records=records,
        diagnostics=diagnostics,
        updated_at=now,
    )
    _atomic_write_json(companion_display_path, companion_display)

    return {
        "project_id": project_id,
        "run_id": run_id,
        "backend_workdir": str(backend_workdir),
        "record_entries": len(records),
        "detected_iterations": len(iter_dirs),
        "artifacts": len(all_artifacts),
        "projected_artifacts": len(projected_artifacts),
        "last_completed": last,
        "next_expected": expected,
        "diagnostics": diagnostics,
        "written": {
            "run_state": str(run_state_path),
            "artifacts": str(artifacts_path),
            "artifacts_display": str(artifacts_display_path),
            "companion_display": str(companion_display_path),
        },
    }
