"""Shared DP-GEN backend helpers for the training controller MCP."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..schemas import artifact, load_json_or_yaml, sha256_file
from ..secret_redactor import redact_mapping, redact_text

STAGES = {
    0: "make_train",
    1: "run_train",
    2: "post_train",
    3: "make_model_devi",
    4: "run_model_devi",
    5: "post_model_devi",
    6: "make_fp",
    7: "run_fp",
    8: "post_fp",
}

LOG_CANDIDATES = (
    "dpgen.log",
    "record.dpgen",
    "iter.*/00.train/*/train.log",
    "iter.*/01.model_devi/task.*/model_devi.out",
    "iter.*/02.fp/task.*/OUTCAR",
    "iter.*/02.fp/task.*/vasprun.xml",
    "iter.*/02.fp/task.*/err",
    "iter.*/02.fp/task.*/log",
    "iter.*/02.fp/task.*/*.err",
    "iter.*/02.fp/task.*/*.log",
)

FAILURE_PATTERNS: tuple[tuple[str, re.Pattern[str], str, list[str]], ...] = (
    (
        "command_not_found",
        re.compile(r"(?i)(command not found|not found:|No such file or directory)"),
        "Executable or required file was not found.",
        [
            "Check machine command paths and wrapper scripts.",
            "Verify source_list activates the expected environment.",
            "Check whether the remote image or container contains the required binary.",
        ],
    ),
    (
        "json_decode_error",
        re.compile(r"JSONDecodeError|Expecting .* delimiter|Extra data"),
        "JSON syntax appears invalid.",
        ["Validate param/machine JSON syntax and remove trailing commas or malformed strings."],
    ),
    (
        "argument_key_error",
        re.compile(r"ArgumentKeyError|undefined key .* not allowed"),
        "DP-GEN schema rejected an unknown or old-format key.",
        ["Compare the config with current DP-GEN examples and remove obsolete keys."],
    ),
    (
        "argument_type_error",
        re.compile(r"ArgumentTypeError|gets wrong value type"),
        "A config key has the wrong value type.",
        ["Inspect the reported key and correct string/list/dict/number types."],
    ),
    (
        "missing_model_graph",
        re.compile(r"FileNotFoundError.*graph\..*\.(pb|pth|savedmodel)|graph\..*No such file"),
        "Training did not produce an expected model artifact.",
        ["Inspect 00.train task logs and validate initial data systems."],
    ),
    (
        "invalid_data_system",
        re.compile(r"cannot find valid.*data system|does not contain any systems"),
        "A configured training data path does not contain a valid DeepMD data system.",
        ["Check init_data_sys paths and ensure each system contains type.raw or valid HDF5 data."],
    ),
    (
        "dpdispatcher_job_failed",
        re.compile(r"job:?.*failed 3 times|Meet errors.*unexpected submission state"),
        "DPDispatcher reported repeated remote job failure.",
        [
            "Check remote_root and generated submission scripts on the remote host.",
            "Inspect train/model_devi/fp logs under the remote task directory.",
            "Verify resource settings and wrapper command environment.",
        ],
    ),
    (
        "too_many_failed_jobs",
        re.compile(r"too many unsuccessfully terminated jobs|ratio of failed jobs"),
        "The failed-job ratio exceeded the configured tolerance.",
        ["Inspect failing FP tasks and only raise ratio_failure after confirming inputs are valid."],
    ),
    (
        "fp_not_converged",
        re.compile(r"not convergence|SCF.*not converged|convergence NOT achieved", re.I),
        "First-principles task appears unconverged.",
        ["Inspect FP input settings, SCF parameters, structure sanity, and resource limits."],
    ),
    (
        "batch_size_or_numb_test",
        re.compile(r"batch_size|numb_test|not enough.*frames", re.I),
        "A data system may have too few frames for training/test split settings.",
        ["Increase fp_task_min, reduce numb_test/batch size, or add more initial data."],
    ),
)


def _project(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _default_param_path(project_path: Path, raw: str | None = None) -> Path:
    if not raw:
        return project_path / "param.json"
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = project_path / candidate
    return candidate.resolve(strict=False)


def _default_machine_path(project_path: Path, raw: str | None = None) -> Path:
    if not raw:
        return project_path / "machine.json"
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = project_path / candidate
    return candidate.resolve(strict=False)


def _iter_dirs(project_path: Path) -> list[Path]:
    if not project_path.exists():
        return []
    return sorted(
        path
        for path in project_path.iterdir()
        if path.is_dir() and re.fullmatch(r"iter\.\d{6}", path.name)
    )


def _read_record(project_path: Path) -> tuple[int | None, int | None, list[str]]:
    record = project_path / "record.dpgen"
    warnings: list[str] = []
    if not record.is_file():
        return None, None, warnings
    last: tuple[int, int] | None = None
    for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        if len(parts) < 2:
            warnings.append(f"Malformed record.dpgen line: {line.strip()}")
            continue
        try:
            last = (int(parts[0]), int(parts[1]))
        except ValueError:
            warnings.append(f"Non-integer record.dpgen line: {line.strip()}")
    if last is None:
        return None, None, warnings
    return last[0], last[1], warnings


def _next_stage(iteration: int | None, stage: int | None) -> tuple[int | None, int | None, str | None]:
    """Return the next DP-GEN stage after the record.dpgen position."""
    if iteration is None or stage is None:
        return None, None, None
    if stage not in STAGES:
        return iteration, None, None
    next_iteration = iteration + 1 if stage >= max(STAGES) else iteration
    next_stage = 0 if stage >= max(STAGES) else stage + 1
    return next_iteration, next_stage, STAGES.get(next_stage)


def _write_record(project_path: Path, iteration: int, stage: int) -> None:
    (project_path / "record.dpgen").write_text(f"{iteration} {stage}\n", encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _timestamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")


def _json_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _controller_run_dir(project: Path, run_id: str) -> Path:
    return project / "runs" / run_id


def _controller_state_path(project: Path, run_id: str) -> Path:
    return _controller_run_dir(project, run_id) / "training_controller_state.json"


def _controller_state_files(project: Path) -> list[Path]:
    return sorted(project.glob("runs/*/training_controller_state.json"))


def _latest_controller_state_path(project: Path) -> Path | None:
    states = _controller_state_files(project)
    return states[-1] if states else None


def _pid_running(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _refresh_controller_state(state: dict[str, Any]) -> dict[str, Any]:
    refreshed = dict(state)
    if refreshed.get("status") == "running" and not _pid_running(refreshed.get("pid")):
        refreshed["status"] = "unknown"
        refreshed["warnings"] = [
            *(refreshed.get("warnings") or []),
            "Recorded PID is no longer running; process exit code is unknown.",
        ]
    return refreshed


def _controller_log_artifacts(state: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts_payload: list[dict[str, Any]] = []
    for key in ("stdout_log", "stderr_log"):
        raw = state.get(key)
        if not isinstance(raw, str):
            continue
        path = Path(raw)
        if path.is_file():
            artifacts_payload.append(artifact(path, "log"))
    state_path = state.get("state_path")
    if isinstance(state_path, str) and Path(state_path).is_file():
        artifacts_payload.append(artifact(Path(state_path), "status"))
    return artifacts_payload


def _backup_file(path: Path, backup_dir: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / path.name
    shutil.copy2(path, target)
    return {"path": str(path), "backup_path": str(target), "sha256": sha256_file(path)}


def _validate_record_target(iteration: int, stage: int) -> list[str]:
    errors: list[str] = []
    if iteration < 0:
        errors.append("target_iteration must be >= 0.")
    if stage not in STAGES:
        errors.append("target_stage must be between 0 and 8.")
    return errors


def _job_id(project: Path, path: Path) -> str:
    try:
        rel = path.resolve(strict=False).relative_to(project.resolve(strict=False))
    except ValueError:
        rel = path
    return hashlib.sha1(str(rel).encode("utf-8")).hexdigest()[:12]


def _stage_from_path(path: Path) -> str | None:
    parts = set(path.parts)
    if "00.train" in parts:
        return "train"
    if "01.model_devi" in parts:
        return "model_devi"
    if "02.fp" in parts:
        return "fp"
    return None


def _iteration_from_path(path: Path) -> int | None:
    for part in path.parts:
        match = re.fullmatch(r"iter\.(\d{6})", part)
        if match:
            return int(match.group(1))
    return None


def _candidate_job_logs(job_json: Path) -> list[Path]:
    task_dir = job_json.parent
    patterns = ("*.log", "*.out", "*.err", "OUTCAR", "vasprun.xml", "output", "fp.log", "train.log", "model_devi.log", "model_devi.out")
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(path for path in task_dir.glob(pattern) if path.is_file())
    return sorted(set(paths))


def _load_json_object(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = load_json_or_yaml(path)
    except Exception as exc:
        errors.append(f"{path}: {type(exc).__name__}: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{path}: expected a JSON/YAML object.")
        return None
    return payload


def _deep_merge(base: Any, patch: Any) -> Any:
    if isinstance(base, dict) and isinstance(patch, dict):
        merged = dict(base)
        for key, value in patch.items():
            merged[key] = _deep_merge(merged.get(key), value)
        return merged
    return patch


def _json_diff(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        ops: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after)):
            child = f"{path}/{key}" if path else f"/{key}"
            if key not in before:
                ops.append({"op": "add", "path": child, "after": after[key]})
            elif key not in after:
                ops.append({"op": "remove", "path": child, "before": before[key]})
            else:
                ops.extend(_json_diff(before[key], after[key], child))
        return ops
    if before != after:
        return [{"op": "replace", "path": path or "/", "before": before, "after": after}]
    return []


def _config_update_plan(
    *,
    config_path: Path,
    updates_json: str | None,
    replacement_path: str | None,
    errors: list[str],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    before = _load_json_object(config_path, errors)
    if before is None:
        return None, None, []
    if replacement_path:
        after = _load_json_object(_project(replacement_path), errors)
    else:
        if not updates_json:
            errors.append("Either updates_json or replacement_path is required.")
            return before, None, []
        try:
            patch = json.loads(updates_json)
        except json.JSONDecodeError as exc:
            errors.append(f"updates_json is invalid JSON: {exc}")
            return before, None, []
        if not isinstance(patch, dict):
            errors.append("updates_json must be a JSON object.")
            return before, None, []
        after = _deep_merge(before, patch)
    if after is None:
        return before, None, []
    return before, after, _json_diff(before, after)


def _line_count(path: Path) -> int:
    try:
        return sum(1 for _ in path.open("r", encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _tail(path: Path, *, max_lines: int = 80) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [redact_text(line) for line in lines[-max_lines:]]


def _truncate_text(text: str, max_chars: int) -> str:
    text = redact_text(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n...[truncated]...\n" + text[-half:]


def _load_config(path: Path) -> tuple[Any | None, list[str]]:
    try:
        return load_json_or_yaml(path), []
    except Exception as exc:
        return None, [f"{path}: {type(exc).__name__}: {exc}"]


def _parse_stage_list(raw: str | None) -> list[str]:
    allowed = ("train", "model_devi", "fp")
    if not raw or raw.strip().lower() in {"all", "*"}:
        return list(allowed)
    stages = [item.strip() for item in raw.split(",") if item.strip()]
    return [stage for stage in stages if stage in allowed]


def _probe_base_command(command: str) -> str:
    parts = shlex.split(command)
    if not parts:
        return command
    if Path(parts[0]).name in {"bash", "sh", "zsh"} and len(parts) >= 2:
        return shlex.join(parts[:2])
    return shlex.join(parts[:1])


def _load_probe_args(raw: str | None, warnings: list[str]) -> dict[str, list[str]]:
    defaults = {
        "train": ["--help"],
        "model_devi": ["-h"],
        "fp": ["--version"],
    }
    if not raw:
        return defaults
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        warnings.append(f"Invalid probe_args_json; using defaults: {exc}")
        return defaults
    if not isinstance(payload, dict):
        warnings.append("probe_args_json is not an object; using defaults.")
        return defaults
    merged = dict(defaults)
    for stage, value in payload.items():
        if stage not in defaults:
            warnings.append(f"Ignoring unknown probe_args_json stage: {stage}")
            continue
        if isinstance(value, str):
            merged[stage] = shlex.split(value)
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            merged[stage] = list(value)
        else:
            warnings.append(f"Ignoring invalid probe_args_json value for stage: {stage}")
    return merged


def _run_machine_probe(
    *,
    command: str,
    stage: str,
    cwd: Path,
    exact: bool,
    probe_args: list[str],
    timeout_seconds: int,
    max_log_chars: int,
) -> dict[str, Any]:
    if exact:
        runnable = command
    else:
        base = _probe_base_command(command)
        runnable = " ".join([base, *(shlex.quote(arg) for arg in probe_args)]).strip()
    started = datetime.now(tz=UTC)
    try:
        completed = subprocess.run(
            runnable,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        ended = datetime.now(tz=UTC)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return {
            "stage": stage,
            "mode": "exact" if exact else "probe",
            "command": runnable,
            "cwd": str(cwd),
            "timeout_seconds": timeout_seconds,
            "returncode": completed.returncode,
            "timed_out": False,
            "duration_seconds": round((ended - started).total_seconds(), 3),
            "stdout": _truncate_text(stdout, max_log_chars),
            "stderr": _truncate_text(stderr, max_log_chars),
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", errors="replace")
        return {
            "stage": stage,
            "mode": "exact" if exact else "probe",
            "command": runnable,
            "cwd": str(cwd),
            "timeout_seconds": timeout_seconds,
            "returncode": None,
            "timed_out": True,
            "duration_seconds": timeout_seconds,
            "stdout": _truncate_text(stdout, max_log_chars),
            "stderr": _truncate_text(stderr, max_log_chars),
            "stdout_chars": len(stdout),
            "stderr_chars": len(stderr),
        }


def _status_for_iter(iter_path: Path) -> dict[str, Any]:
    fp_path = iter_path / "02.fp"
    candidate_frames = sum(_line_count(path) for path in fp_path.glob("candidate*.out"))
    failed_frames = sum(_line_count(path) for path in fp_path.glob("rest_failed*.out"))
    accurate_frames = sum(_line_count(path) for path in fp_path.glob("rest_accurate*.out"))
    fp_tasks = len([path for path in fp_path.glob("task.*") if path.is_dir()])
    data_dirs = len([path for path in fp_path.glob("data.*") if path.is_dir()])
    return {
        "iteration": iter_path.name,
        "has_train": (iter_path / "00.train").is_dir(),
        "has_model_devi": (iter_path / "01.model_devi").is_dir(),
        "has_fp": fp_path.is_dir(),
        "candidate_frames": candidate_frames,
        "failed_frames": failed_frames,
        "accurate_frames": accurate_frames,
        "fp_tasks": fp_tasks,
        "data_dirs": data_dirs,
    }


def _machine_secret_warnings(machine_data: Any) -> list[str]:
    _, findings = redact_mapping(machine_data)
    return [f"machine config contains secret-like field: {path}" for path in findings]


def _dpgen_schema_warnings(param_data: Any, machine_data: Any) -> list[str]:
    warnings: list[str] = []
    try:
        from dpgen.generator.arginfo import run_jdata_arginfo, run_mdata_arginfo
        from dpgen.util import normalize
    except Exception:
        return ["DP-GEN Python package is not importable; skipped dargs schema validation."]
    try:
        normalize(run_jdata_arginfo(), param_data, strict_check=False)
    except Exception as exc:
        warnings.append(f"DP-GEN param schema warning: {type(exc).__name__}: {exc}")
    try:
        normalize(run_mdata_arginfo(), machine_data, strict_check=False)
    except Exception as exc:
        warnings.append(f"DP-GEN machine schema warning: {type(exc).__name__}: {exc}")
    return warnings


def _dpgen_param_schema_warnings(param_data: Any) -> list[str]:
    try:
        from dpgen.generator.arginfo import run_jdata_arginfo
        from dpgen.util import normalize
    except Exception:
        return ["DP-GEN Python package is not importable; skipped param dargs schema validation."]
    try:
        normalize(run_jdata_arginfo(), param_data, strict_check=False)
    except Exception as exc:
        return [f"DP-GEN param schema warning: {type(exc).__name__}: {exc}"]
    return []


def _dpgen_machine_schema_warnings(machine_data: Any) -> list[str]:
    try:
        from dpgen.generator.arginfo import run_mdata_arginfo
        from dpgen.util import normalize
    except Exception:
        return ["DP-GEN Python package is not importable; skipped machine dargs schema validation."]
    try:
        normalize(run_mdata_arginfo(), machine_data, strict_check=False)
    except Exception as exc:
        return [f"DP-GEN machine schema warning: {type(exc).__name__}: {exc}"]
    return []


def _wrapper_script_from_command(command: Any) -> Path | None:
    if not isinstance(command, str) or not command.strip():
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts:
        return None
    candidates = parts[1:] if Path(parts[0]).name in {"bash", "sh", "zsh"} else parts[:1]
    for item in candidates:
        if item.startswith("-"):
            continue
        path = Path(item).expanduser()
        if path.suffix in {".sh", ".bash", ".zsh", ".py"} or "/" in item:
            return path.resolve(strict=False)
    return None


def _write_manifest(
    project: Path,
    *,
    source: str,
    inputs: list[Any],
    outputs: list[Any],
    artifacts_payload: list[dict[str, Any]],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any] | None:
    try:
        run_id = f"training_controller_{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}"
        try:
            from mlpcopilot.runtime.artifacts import ArtifactIndex

            manifest = ArtifactIndex(project).create_run(
                run_id=run_id,
                source=source,
                inputs=inputs,
                outputs=outputs,
                artifacts=artifacts_payload,
                errors=errors,
                metadata={
                    "backend": "dpgen",
                    "warnings": warnings,
                },
            )
            manifest_path = project / "runs" / manifest.run_id / "manifest.json"
        except Exception:
            manifest_dir = project / "runs" / run_id
            manifest_dir.mkdir(parents=True, exist_ok=True)
            manifest_payload = {
                "run_id": run_id,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "source": source,
                "inputs": inputs,
                "outputs": outputs,
                "artifacts": artifacts_payload,
                "approval": None,
                "errors": errors,
                "metadata": {
                    "backend": "dpgen",
                    "warnings": warnings,
                },
            }
            manifest_path = manifest_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return artifact(manifest_path, "manifest")
    except OSError:
        return None


def _sync_project_run_config(output: Path, config_name: str, artifacts_payload: list[dict[str, Any]], warnings: list[str]) -> None:
    run_dir = next((parent for parent in (output.parent, *output.parents) if (parent / "run.json").is_file()), None)
    if run_dir is None or not output.is_file():
        return
    targets = [
        run_dir / "controller" / "rendered_inputs" / config_name,
        run_dir / "backend" / "dpgen" / config_name,
    ]
    source_bytes = output.read_bytes()
    for target in targets:
        try:
            if target.resolve(strict=False) == output.resolve(strict=False):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_bytes)
            artifacts_payload.append(artifact(target, "config"))
        except OSError as exc:
            warnings.append(f"Failed to sync {config_name} into project run schema: {target}: {exc}")
