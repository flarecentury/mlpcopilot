"""DP-GEN DPDispatcher job inspection operations."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..schemas import artifact, result, sha256_file
from ..secret_redactor import redact_mapping


def list_dispatcher_jobs(
    backend: str,
    *,
    project_path: str,
    max_results: int = 200,
) -> str:
    from .dpgen_common import (
        _candidate_job_logs,
        _iteration_from_path,
        _job_id,
        _project,
        _stage_from_path,
    )

    project = _project(project_path)
    job_paths = sorted(path for path in project.glob("iter.*/**/job.json") if path.is_file())
    jobs = []
    for path in job_paths[:max_results]:
        logs = _candidate_job_logs(path)
        jobs.append(
            {
                "id": _job_id(project, path),
                "job_json": str(path),
                "task_dir": str(path.parent),
                "iteration": _iteration_from_path(path),
                "stage": _stage_from_path(path),
                "log_paths": [str(log) for log in logs[:10]],
            }
        )
    return result(
        status="success" if project.is_dir() else "failed",
        summary=f"Found {len(job_paths)} DPDispatcher job.json files.",
        metrics={"backend": backend, "project_path": str(project), "jobs": jobs, "total_jobs": len(job_paths)},
        artifacts=[artifact(path, "status") for path in job_paths[:max_results]],
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def inspect_dispatcher_job(
    backend: str,
    *,
    project_path: str,
    job_ref: str,
    max_log_lines: int = 120,
) -> str:
    from .dpgen_common import (
        _candidate_job_logs,
        _iteration_from_path,
        _job_id,
        _load_json_object,
        _project,
        _stage_from_path,
        _tail,
    )

    project = _project(project_path)
    candidate = Path(job_ref).expanduser()
    if not candidate.is_absolute():
        candidate = project / candidate
    if not candidate.is_file():
        for path in project.glob("iter.*/**/job.json"):
            if _job_id(project, path) == job_ref:
                candidate = path
                break
    if not candidate.is_file():
        return result(
            status="failed",
            summary=f"Dispatcher job not found: {job_ref}",
            metrics={"backend": backend, "project_path": str(project), "job_ref": job_ref},
            errors=[f"No such job.json or job id: {job_ref}"],
        )
    errors: list[str] = []
    job_data = _load_json_object(candidate, errors)
    logs = [
        {"path": str(path), "sha256": sha256_file(path), "tail": _tail(path, max_lines=max_log_lines)}
        for path in _candidate_job_logs(candidate)[:20]
    ]
    artifacts_payload = [artifact(candidate, "status")]
    artifacts_payload.extend(artifact(Path(item["path"]), "log") for item in logs)
    return result(
        status="failed" if errors else "success",
        summary=f"Inspected dispatcher job {_job_id(project, candidate)}.",
        metrics={
            "backend": backend,
            "id": _job_id(project, candidate),
            "job_json": str(candidate),
            "task_dir": str(candidate.parent),
            "iteration": _iteration_from_path(candidate),
            "stage": _stage_from_path(candidate),
            "job": redact_mapping(job_data or {})[0],
            "logs": logs,
        },
        artifacts=artifacts_payload,
        errors=errors,
    )


def cancel_remote_jobs(
    backend: str,
    *,
    project_path: str,
    scheduler: str = "slurm",
    job_ids_json: str | None = None,
) -> str:
    from .dpgen_common import _project, _truncate_text

    project = _project(project_path)
    errors: list[str] = []
    try:
        job_ids = json.loads(job_ids_json) if job_ids_json else []
    except json.JSONDecodeError as exc:
        job_ids = []
        errors.append(f"job_ids_json is invalid JSON: {exc}")
    if not isinstance(job_ids, list) or not all(isinstance(item, str) for item in job_ids):
        errors.append("job_ids_json must be a JSON list of scheduler job id strings.")
        job_ids = []
    scheduler = scheduler.lower().strip()
    if scheduler == "slurm":
        command = ["scancel", *job_ids]
    elif scheduler in {"pbs", "torque"}:
        command = ["qdel", *job_ids]
    else:
        errors.append("scheduler must be 'slurm', 'pbs', or 'torque'.")
        command = []
    if not job_ids:
        errors.append("No scheduler job ids were provided. Use inspect_dispatcher_job/list scheduler output first.")
    if errors:
        return result(
            status="failed",
            summary="Remote job cancel plan is invalid.",
            metrics={"backend": backend, "project_path": str(project), "scheduler": scheduler, "command": command},
            errors=errors,
        )
    completed = subprocess.run(command, cwd=str(project), text=True, capture_output=True, check=False)
    return result(
        status="success" if completed.returncode == 0 else "failed",
        summary="Submitted remote job cancellation command.",
        metrics={
            "backend": backend,
            "scheduler": scheduler,
            "command": command,
            "returncode": completed.returncode,
            "stdout": _truncate_text(completed.stdout or "", 4000),
            "stderr": _truncate_text(completed.stderr or "", 4000),
        },
        errors=[] if completed.returncode == 0 else ["Scheduler cancellation command failed."],
    )


def cancel_scheduler_jobs(
    backend: str,
    *,
    project_path: str,
    scheduler: str = "slurm",
    job_ids_json: str | None = None,
) -> str:
    return cancel_remote_jobs(
        backend,
        project_path=project_path,
        scheduler=scheduler,
        job_ids_json=job_ids_json,
    )
