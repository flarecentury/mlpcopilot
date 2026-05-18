"""DP-GEN controller process operations."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Any

from ..schemas import result, sha256_file


def get_controller_state(
    backend: str,
    *,
    project_path: str,
    run_id: str | None = None,
    max_log_lines: int = 80,
) -> str:
    from .dpgen_common import (
        _controller_log_artifacts,
        _controller_state_path,
        _json_read,
        _latest_controller_state_path,
        _project,
        _refresh_controller_state,
        _tail,
    )

    project = _project(project_path)
    state_path = _controller_state_path(project, run_id) if run_id else _latest_controller_state_path(project)
    if state_path is None or not state_path.is_file():
        return result(
            status="failed",
            summary="No training controller state file found.",
            metrics={"backend": backend, "project_path": str(project), "run_id": run_id},
            errors=[f"No controller state under {project / 'runs'}"],
        )
    try:
        state = _refresh_controller_state(_json_read(state_path))
    except Exception as exc:
        return result(
            status="failed",
            summary="Failed to read training controller state.",
            metrics={"backend": backend, "state_path": str(state_path)},
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    state["state_path"] = str(state_path)
    logs = {}
    for key in ("stdout_log", "stderr_log"):
        raw = state.get(key)
        if isinstance(raw, str) and Path(raw).is_file():
            logs[key] = _tail(Path(raw), max_lines=max_log_lines)
    return result(
        status="success",
        summary=f"Controller run {state.get('run_id')} is {state.get('status')}.",
        metrics={"backend": backend, "state": state, "log_tails": logs},
        artifacts=_controller_log_artifacts(state),
        warnings=state.get("warnings") or [],
    )


def run_training_controller(
    backend: str,
    *,
    project_path: str,
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
    mode: str = "auto",
) -> str:
    from .dpgen_common import (
        STAGES,
        _controller_log_artifacts,
        _controller_run_dir,
        _controller_state_path,
        _default_machine_path,
        _default_param_path,
        _json_read,
        _json_write,
        _latest_controller_state_path,
        _now_iso,
        _project,
        _read_record,
        _refresh_controller_state,
        _timestamp,
    )
    from .dpgen_manifest import write_controller_manifest

    project = _project(project_path)
    param_file = _default_param_path(project, param_path)
    machine_file = _default_machine_path(project, machine_path)
    normalized_mode = mode.lower().strip()
    if normalized_mode not in {"auto", "fresh", "resume"}:
        normalized_mode = "invalid"
    current_iter, current_stage, record_warnings = _read_record(project)
    run_id = run_id or f"training_controller_{_timestamp()}"
    run_dir = _controller_run_dir(project, run_id)
    log_dir = run_dir / "logs"
    stdout_log = log_dir / "dpgen.stdout.log"
    stderr_log = log_dir / "dpgen.stderr.log"
    errors: list[str] = []
    warnings: list[str] = [*record_warnings]
    if normalized_mode == "invalid":
        errors.append("mode must be 'auto', 'fresh', or 'resume'.")
    if normalized_mode == "fresh" and (project / "record.dpgen").is_file():
        warnings.append("mode=fresh was requested but record.dpgen exists; DP-GEN itself will still continue from record.dpgen.")
    if normalized_mode == "resume" and not (project / "record.dpgen").is_file():
        warnings.append("mode=resume was requested but record.dpgen is missing; DP-GEN will start from the beginning.")
    if not project.is_dir():
        errors.append(f"No such project directory: {project}")
    if not param_file.is_file():
        errors.append(f"Missing param file: {param_file}")
    if not machine_file.is_file():
        errors.append(f"Missing machine file: {machine_file}")
    existing_state = _latest_controller_state_path(project)
    if existing_state is not None:
        try:
            existing = _refresh_controller_state(_json_read(existing_state))
            if existing.get("status") == "running":
                errors.append(f"Another controller run is already marked running: {existing.get('run_id')}")
        except Exception as exc:
            warnings.append(f"Could not inspect latest controller state: {exc}")
    command = [*shlex.split(dpgen_command), "run", str(param_file), str(machine_file)]
    resume_from_record = {
        "iteration": current_iter,
        "stage": current_stage,
        "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
    }
    preview = {
        "run_id": run_id,
        "mode": normalized_mode,
        "cwd": str(project),
        "command": command,
        "resume_from_record": resume_from_record,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    if errors:
        return result(
            status="failed",
            summary="Training run cannot start.",
            metrics={"backend": backend, "preview": preview},
            warnings=warnings,
            errors=errors,
        )
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_handle = stdout_log.open("ab")
    stderr_handle = stderr_log.open("ab")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(project),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
        )
    except Exception as exc:
        stdout_handle.close()
        stderr_handle.close()
        return result(
            status="failed",
            summary="Failed to launch DP-GEN training run.",
            metrics={"backend": backend, "preview": preview},
            warnings=warnings,
            errors=[f"{type(exc).__name__}: {exc}"],
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    state: dict[str, Any] = {
        "schema_version": 1,
        "backend": backend,
        "run_id": run_id,
        "status": "running",
        "mode": normalized_mode,
        "started_at": _now_iso(),
        "finished_at": None,
        "exit_code": None,
        "cwd": str(project),
        "command": command,
        "pid": process.pid,
        "process_group_id": process.pid,
        "param_path": str(param_file),
        "param_sha256": sha256_file(param_file),
        "machine_path": str(machine_file),
        "machine_sha256": sha256_file(machine_file),
        "resume_from_record": resume_from_record,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "warnings": warnings,
    }
    state_path = _controller_state_path(project, run_id)
    state["state_path"] = str(state_path)
    _json_write(state_path, state)
    artifacts_payload = _controller_log_artifacts(state)
    manifest_artifact = write_controller_manifest(
        project,
        backend=backend,
        operation="start_training_run",
        state=state,
        artifacts_payload=artifacts_payload,
        warnings=warnings,
    )
    if manifest_artifact:
        artifacts_payload.append(manifest_artifact)
    return result(
        status="success",
        summary=f"Started DP-GEN training run {run_id}.",
        metrics={"backend": backend, "state": state},
        artifacts=artifacts_payload,
    )


def start_training_run(
    backend: str,
    *,
    project_path: str,
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
) -> str:
    return run_training_controller(
        backend,
        project_path=project_path,
        param_path=param_path,
        machine_path=machine_path,
        run_id=run_id,
        dpgen_command=dpgen_command,
        mode="auto",
    )


def stop_training_run(
    backend: str,
    *,
    project_path: str,
    run_id: str | None = None,
    signal_name: str = "TERM",
) -> str:
    from .dpgen_common import (
        _controller_log_artifacts,
        _controller_state_path,
        _json_read,
        _json_write,
        _latest_controller_state_path,
        _now_iso,
        _project,
        _refresh_controller_state,
    )
    from .dpgen_manifest import write_controller_manifest

    project = _project(project_path)
    state_path = _controller_state_path(project, run_id) if run_id else _latest_controller_state_path(project)
    if state_path is None or not state_path.is_file():
        return result(
            status="failed",
            summary="No controller state found to stop.",
            metrics={"backend": backend, "project_path": str(project), "run_id": run_id},
            errors=[f"No controller state under {project / 'runs'}"],
        )
    state = _refresh_controller_state(_json_read(state_path))
    state["state_path"] = str(state_path)
    pgid = state.get("process_group_id") or state.get("pid")
    sig = signal.SIGTERM if signal_name.upper() == "TERM" else signal.SIGINT
    preview = {"run_id": state.get("run_id"), "process_group_id": pgid, "signal": sig.name}
    if state.get("status") != "running":
        artifacts_payload = _controller_log_artifacts(state)
        manifest_artifact = write_controller_manifest(
            project,
            backend=backend,
            operation="stop_training_run",
            state=state,
            artifacts_payload=artifacts_payload,
            warnings=state.get("warnings") or [],
        )
        if manifest_artifact:
            artifacts_payload.append(manifest_artifact)
        return result(
            status="success",
            summary=f"Controller run {state.get('run_id')} is not running.",
            metrics={"backend": backend, "state": state},
            artifacts=artifacts_payload,
            warnings=state.get("warnings") or [],
        )
    try:
        os.killpg(int(pgid), sig)
        state["status"] = "stop_requested"
        state["stop_requested_at"] = _now_iso()
        state["stop_signal"] = sig.name
        _json_write(state_path, state)
        status = "success"
        summary = f"Sent {sig.name} to controller run {state.get('run_id')}."
        errors: list[str] = []
    except Exception as exc:
        status = "failed"
        summary = "Failed to signal controller run."
        errors = [f"{type(exc).__name__}: {exc}"]
    artifacts_payload = _controller_log_artifacts(state)
    manifest_artifact = write_controller_manifest(
        project,
        backend=backend,
        operation="stop_training_run",
        state=state,
        artifacts_payload=artifacts_payload,
        errors=errors,
    )
    if manifest_artifact:
        artifacts_payload.append(manifest_artifact)
    return result(
        status=status,
        summary=summary,
        metrics={"backend": backend, "state": state, "preview": preview},
        artifacts=artifacts_payload,
        errors=errors,
    )


def resume_training_run(
    backend: str,
    *,
    project_path: str,
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
) -> str:
    payload = json.loads(
        run_training_controller(
            backend,
            project_path=project_path,
            param_path=param_path,
            machine_path=machine_path,
            run_id=run_id,
            dpgen_command=dpgen_command,
            mode="resume",
        )
    )
    payload["summary"] = "Resume " + str(payload.get("summary", "")).removeprefix("Training ")
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
