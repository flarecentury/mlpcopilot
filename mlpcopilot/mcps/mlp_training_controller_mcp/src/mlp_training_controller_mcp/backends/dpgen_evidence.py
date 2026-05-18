"""DP-GEN evidence and snapshot operations."""

from __future__ import annotations

from ..schemas import artifact, result, sha256_file


def snapshot_training_state(
    backend: str,
    *,
    project_path: str,
    output_path: str | None = None,
) -> str:
    from .dpgen_common import (
        STAGES,
        _controller_state_files,
        _iter_dirs,
        _json_write,
        _next_stage,
        _now_iso,
        _project,
        _read_record,
        _status_for_iter,
        _timestamp,
    )

    project = _project(project_path)
    snapshot_path = _project(output_path) if output_path else project / "reports" / f"training_state_snapshot_{_timestamp()}.json"
    iter_dirs = _iter_dirs(project)
    current_iter, current_stage, warnings = _read_record(project)
    next_iter, next_stage, next_stage_name = _next_stage(current_iter, current_stage)
    files = []
    for raw in ("param.json", "machine.json", "record.dpgen", "dpgen.log"):
        path = project / raw
        if path.is_file():
            files.append({"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size})
    controller_states = [
        {"path": str(path), "sha256": sha256_file(path)}
        for path in _controller_state_files(project)
        if path.is_file()
    ]
    payload = {
        "schema_version": 1,
        "backend": backend,
        "created_at": _now_iso(),
        "project_path": str(project),
        "record": {
            "iteration": current_iter,
            "stage": current_stage,
            "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
        },
        "next_record": {
            "iteration": next_iter,
            "stage": next_stage,
            "stage_name": next_stage_name,
        },
        "status_source": "record.dpgen + iteration directories + controller state files",
        "iterations": [_status_for_iter(path) for path in iter_dirs],
        "files": files,
        "controller_states": controller_states,
    }
    errors: list[str] = []
    artifacts_payload: list[dict[str, str]] = []
    try:
        _json_write(snapshot_path, payload)
        artifacts_payload.append(artifact(snapshot_path, "status"))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return result(
        status="failed" if errors or not project.is_dir() else "success",
        summary=f"Wrote DP-GEN training state snapshot: {snapshot_path}" if not errors else "Failed to write training state snapshot.",
        metrics={"backend": backend, "snapshot_path": str(snapshot_path), "iterations_found": len(iter_dirs), "record": payload["record"]},
        artifacts=artifacts_payload,
        warnings=warnings,
        errors=errors + ([] if project.is_dir() else [f"No such project directory: {project}"]),
    )


def collect_iteration_evidence(
    backend: str,
    *,
    project_path: str,
    iteration: int,
    output_path: str | None = None,
) -> str:
    from .dpgen_common import _json_write, _project, _status_for_iter, _timestamp

    project = _project(project_path)
    iter_path = project / f"iter.{iteration:06d}"
    evidence_path = _project(output_path) if output_path else project / "reports" / f"iteration_{iteration:06d}_evidence_{_timestamp()}.json"
    if not iter_path.is_dir():
        return result(
            status="failed",
            summary=f"Iteration not found: iter.{iteration:06d}",
            metrics={"backend": backend, "project_path": str(project), "iteration": iteration},
            errors=[f"No such iteration directory: {iter_path}"],
        )
    log_paths = [
        path
        for pattern in ("00.train/*/train.log", "01.model_devi/task.*/model_devi.*", "02.fp/task.*/*", "02.fp/*.out")
        for path in iter_path.glob(pattern)
        if path.is_file()
    ]
    payload = {
        "schema_version": 1,
        "backend": backend,
        "created_at": _timestamp(),
        "project_path": str(project),
        "iteration": iteration,
        "status": _status_for_iter(iter_path),
        "artifacts": [
            {"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size}
            for path in sorted(set(log_paths))[:500]
        ],
    }
    errors: list[str] = []
    artifacts_payload: list[dict[str, str]] = []
    try:
        _json_write(evidence_path, payload)
        artifacts_payload.append(artifact(evidence_path, "status"))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return result(
        status="failed" if errors else "success",
        summary=f"Collected evidence for iter.{iteration:06d}.",
        metrics={"backend": backend, "evidence_path": str(evidence_path), "artifact_count": len(payload["artifacts"])},
        artifacts=artifacts_payload,
        errors=errors,
    )
