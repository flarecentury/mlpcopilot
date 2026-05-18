"""DP-GEN record reset operations."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..schemas import artifact, result, sha256_file


def _pre_rewind_snapshot(project: Path, backup_dir: Path, plan: dict[str, Any]) -> dict[str, Any]:
    from .dpgen_common import (
        STAGES,
        _controller_state_files,
        _iter_dirs,
        _json_write,
        _now_iso,
        _read_record,
        _status_for_iter,
    )

    current_iter, current_stage, warnings = _read_record(project)
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
    snapshot_path = backup_dir / "state_snapshot_before.json"
    payload = {
        "schema_version": 1,
        "backend": plan.get("backend"),
        "created_at": _now_iso(),
        "project_path": str(project),
        "purpose": "pre_rewind_preservation_snapshot",
        "record": {
            "iteration": current_iter,
            "stage": current_stage,
            "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
        },
        "planned_target_record": plan.get("target_record") or {},
        "preservation_policy": plan.get("preservation_policy") or {},
        "status_source": "record.dpgen + iteration directories + controller state files",
        "iterations": [_status_for_iter(path) for path in _iter_dirs(project)],
        "files": files,
        "controller_states": controller_states,
        "warnings": warnings,
    }
    _json_write(snapshot_path, payload)
    return {"path": str(snapshot_path), "sha256": sha256_file(snapshot_path), "size": snapshot_path.stat().st_size}


def _rewind_target(
    *,
    project_path: str,
    target: str,
    target_iteration: int | None,
    target_stage: int | None,
) -> tuple[int | None, int | None, list[str], list[str]]:
    from .dpgen_common import _project, _read_record

    project = _project(project_path)
    normalized_target = target.lower().strip()
    warnings: list[str] = []
    errors: list[str] = []
    if normalized_target == "explicit":
        if target_iteration is None or target_stage is None:
            errors.append("target_iteration and target_stage are required when target='explicit'.")
            return None, None, warnings, errors
        return target_iteration, target_stage, warnings, errors
    if normalized_target != "previous_stage":
        errors.append("target must be 'previous_stage' or 'explicit'.")
        return None, None, warnings, errors
    current_iter, current_stage, record_warnings = _read_record(project)
    warnings.extend(record_warnings)
    if current_iter is None or current_stage is None:
        errors.append("Cannot infer previous stage because record.dpgen is missing.")
        return None, None, warnings, errors
    next_stage = max(current_stage - 1, -1)
    if next_stage < 0:
        next_iter = max(current_iter - 1, 0)
        next_stage = 8 if current_iter > 0 else 0
    else:
        next_iter = current_iter
    return next_iter, next_stage, warnings, errors


def plan_training_rewind(
    backend: str,
    *,
    project_path: str,
    target: str = "previous_stage",
    target_iteration: int | None = None,
    target_stage: int | None = None,
    mode: str = "soft",
) -> str:
    resolved_iter, resolved_stage, warnings, errors = _rewind_target(
        project_path=project_path,
        target=target,
        target_iteration=target_iteration,
        target_stage=target_stage,
    )
    if errors:
        return result(
            status="failed",
            summary="Could not prepare DP-GEN rewind plan.",
            metrics={
                "backend": backend,
                "project_path": project_path,
                "target": target,
                "target_iteration": target_iteration,
                "target_stage": target_stage,
            },
            warnings=warnings,
            errors=errors,
        )
    payload = json.loads(
        plan_training_reset(
            backend,
            project_path=project_path,
            target_iteration=int(resolved_iter),
            target_stage=int(resolved_stage),
            mode=mode,
        )
    )
    payload.setdefault("metrics", {})["rewind_target"] = target
    payload.setdefault("warnings", []).extend(warnings)
    payload["summary"] = str(payload.get("summary", "")).replace("reset", "rewind")
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def apply_training_rewind(
    backend: str,
    *,
    project_path: str,
    target: str = "previous_stage",
    target_iteration: int | None = None,
    target_stage: int | None = None,
    mode: str = "soft",
) -> str:
    resolved_iter, resolved_stage, warnings, errors = _rewind_target(
        project_path=project_path,
        target=target,
        target_iteration=target_iteration,
        target_stage=target_stage,
    )
    if errors:
        return result(
            status="failed",
            summary="Could not apply DP-GEN rewind.",
            metrics={
                "backend": backend,
                "project_path": project_path,
                "target": target,
                "target_iteration": target_iteration,
                "target_stage": target_stage,
            },
            warnings=warnings,
            errors=errors,
        )
    payload = json.loads(
        reset_training_run(
            backend,
            project_path=project_path,
            target_iteration=int(resolved_iter),
            target_stage=int(resolved_stage),
            mode=mode,
            operation="apply_training_rewind",
            event_metadata={"rewind_target": target},
        )
    )
    payload.setdefault("metrics", {})["rewind_target"] = target
    payload.setdefault("warnings", []).extend(warnings)
    payload["summary"] = str(payload.get("summary", "")).replace("reset", "rewind")
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def plan_training_reset(
    backend: str,
    *,
    project_path: str,
    target_iteration: int,
    target_stage: int,
    mode: str = "soft",
) -> str:
    from .dpgen_common import (
        STAGES,
        _iter_dirs,
        _project,
        _read_record,
        _timestamp,
        _validate_record_target,
    )

    project = _project(project_path)
    errors = [] if project.is_dir() else [f"No such project directory: {project}"]
    errors.extend(_validate_record_target(target_iteration, target_stage))
    mode = mode.lower().strip()
    if mode not in {"soft", "hard"}:
        errors.append("mode must be 'soft' or 'hard'.")
    current_iter, current_stage, warnings = _read_record(project)
    affected_iters = [
        str(path)
        for path in _iter_dirs(project)
        if int(path.name.split(".")[1]) > target_iteration
    ]
    backup_dir = project / ".mlpcopilot" / "backups" / f"reset_{_timestamp()}"
    preservation_policy = {
        "default_mode": "soft",
        "soft": "Only record.dpgen is backed up and rewritten; all iter.?????? directories are preserved in place.",
        "hard": "Later iter.?????? directories are moved into backup_dir/moved_iter_dirs as an archive; directories are not deleted.",
        "requires_user_confirmation": mode == "hard",
    }
    plan: dict[str, Any] = {
        "backend": backend,
        "generated_at": _timestamp(),
        "project_path": str(project),
        "mode": mode,
        "preservation_policy": preservation_policy,
        "current_record": {
            "iteration": current_iter,
            "stage": current_stage,
            "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
        },
        "target_record": {
            "iteration": target_iteration,
            "stage": target_stage,
            "stage_name": STAGES.get(target_stage),
        },
        "record_write": f"{target_iteration} {target_stage}",
        "backup_dir": str(backup_dir),
        "hard_mode_iter_dirs_to_move": affected_iters if mode == "hard" else [],
        "hard_mode_iter_dirs_to_archive": affected_iters if mode == "hard" else [],
        "soft_mode_iter_dirs_preserved": affected_iters if mode == "soft" else [],
    }
    if mode == "soft" and affected_iters:
        warnings.append(
            "Soft mode preserves later iteration directories in place; ask the user before choosing hard/archive cleanup."
        )
    if mode == "hard":
        warnings.append(
            "Hard mode archives later iteration directories under backup_dir/moved_iter_dirs; it does not delete them and should be user-confirmed."
        )
    return result(
        status="failed" if errors else "success",
        summary="Prepared DP-GEN reset plan." if not errors else "Could not prepare DP-GEN reset plan.",
        metrics=plan,
        warnings=warnings,
        errors=errors,
    )


def reset_training_run(
    backend: str,
    *,
    project_path: str,
    target_iteration: int,
    target_stage: int,
    mode: str = "soft",
    run_id: str | None = None,
    operation: str = "reset_training_run",
    event_metadata: dict[str, Any] | None = None,
) -> str:
    from .dpgen_common import _backup_file, _json_write, _project, _write_record
    from .dpgen_manifest import write_reset_manifest
    from .dpgen_projection import refresh_mlpcopilot_projection_for_backend

    plan_payload = json.loads(
        plan_training_reset(
            backend,
            project_path=project_path,
            target_iteration=target_iteration,
            target_stage=target_stage,
            mode=mode,
        )
    )
    if plan_payload.get("status") == "failed":
        return json.dumps(plan_payload, indent=2, ensure_ascii=False, sort_keys=True)
    project = _project(project_path)
    mode = mode.lower().strip()
    backup_dir = Path(plan_payload["metrics"]["backup_dir"])
    manifest_run_id = run_id or backup_dir.name
    artifacts_payload: list[dict[str, Any]] = []
    warnings: list[str] = list(plan_payload.get("warnings") or [])
    errors: list[str] = []
    backups: list[dict[str, Any]] = []
    projection_refresh: dict[str, Any] | None = None
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        snapshot = _pre_rewind_snapshot(project, backup_dir, plan_payload["metrics"])
        artifacts_payload.append(artifact(Path(snapshot["path"]), "status"))
        backups.append({"path": str(project), "backup_path": snapshot["path"], "sha256": snapshot["sha256"], "kind": "pre_rewind_snapshot"})
        backup = _backup_file(project / "record.dpgen", backup_dir)
        if backup:
            backups.append(backup)
        if mode == "hard":
            moved_dir = backup_dir / "moved_iter_dirs"
            moved_dir.mkdir(parents=True, exist_ok=True)
            for raw in plan_payload["metrics"]["hard_mode_iter_dirs_to_move"]:
                src = Path(raw)
                if src.exists():
                    shutil.move(str(src), str(moved_dir / src.name))
                    backups.append({"path": str(src), "backup_path": str(moved_dir / src.name), "kind": "archived_iter_dir"})
        _write_record(project, target_iteration, target_stage)
        artifacts_payload.append(artifact(project / "record.dpgen", "status"))
        if backup_dir.exists():
            manifest = backup_dir / "reset_manifest.json"
            _json_write(
                manifest,
                {
                    "schema_version": 1,
                    "created_at": plan_payload.get("generated_at"),
                    "plan": plan_payload["metrics"],
                    "backups": backups,
                },
            )
            artifacts_payload.append(artifact(manifest, "manifest"))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    if not errors:
        projection_refresh = refresh_mlpcopilot_projection_for_backend(
            project,
            original_project_path=project_path,
        )
        if projection_refresh and projection_refresh.get("status") in {"failed", "partial", "skipped"}:
            warnings.append(
                "DP-GEN state was rewound, but MLP Copilot UI projection refresh did not fully complete."
            )
    manifest_artifact = write_reset_manifest(
        project,
        backend=backend,
        operation=operation,
        run_id=manifest_run_id,
        plan=plan_payload["metrics"],
        artifacts_payload=artifacts_payload,
        backups=backups,
        warnings=warnings,
        errors=errors,
        event_metadata=event_metadata,
    )
    if manifest_artifact:
        artifacts_payload.append(manifest_artifact)
    metrics = {**plan_payload["metrics"], "backups": backups}
    if projection_refresh:
        metrics["mlpcopilot_projection_refresh"] = projection_refresh
    return result(
        status="failed" if errors else "success",
        summary="Applied DP-GEN reset." if not errors else "Failed to apply DP-GEN reset.",
        metrics=metrics,
        artifacts=artifacts_payload,
        warnings=warnings,
        errors=errors,
    )


def rerun_failed_stage(
    backend: str,
    *,
    project_path: str,
    mode: str = "soft",
) -> str:
    return apply_training_rewind(
        backend,
        project_path=project_path,
        target="previous_stage",
        mode=mode,
    )
