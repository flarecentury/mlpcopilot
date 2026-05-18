"""DP-GEN input and runtime validation operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from ..schemas import artifact, result
from ..template_assets import collect_dpgen_template_checks, resolve_asset


def _latest_machine_stage(
    machine_data: dict[str, Any],
    section: str,
    errors: list[str],
) -> dict[str, Any] | None:
    """Return a latest-schema DP-GEN machine stage or add migration errors."""
    payload = machine_data.get(section)
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        errors.append(
            f"machine.{section} uses a list. MLP Copilot supports only the current "
            "DP-GEN machine schema, where each stage is a single object. Migration: "
            f"replace \"{section}\": [{{...}}] with \"{section}\": {{...}} and keep "
            "command, machine, resources, user_forward_files, and user_backward_files "
            "inside that object."
        )
        return None
    legacy_keys = [
        key
        for key in (
            f"{section}_machine",
            f"{section}_resources",
            f"{section}_command",
            f"{section}_group_size",
        )
        if key in machine_data
    ]
    if legacy_keys:
        errors.append(
            f"machine.json uses legacy DPDispatcher keys for {section}: {legacy_keys}. "
            "MLP Copilot supports only current DP-GEN machine.json. Migration: create "
            f"a top-level \"{section}\" object containing command, machine, and resources."
        )
        return None
    if section not in machine_data:
        errors.append(
            f"machine.json missing current DP-GEN section: {section}. Expected a top-level "
            f"\"{section}\" object with command, machine, and resources."
        )
        return None
    errors.append(
        f"machine.{section} must be an object in the current DP-GEN machine schema; "
        f"got {type(payload).__name__}."
    )
    return None


def validate_training_inputs(
    backend: str,
    *,
    param_path: str,
    machine_path: str,
    project_path: str | None = None,
) -> str:
    from .dpgen_common import (
        _default_machine_path,
        _default_param_path,
        _dpgen_schema_warnings,
        _load_config,
        _machine_secret_warnings,
        _project,
        _wrapper_script_from_command,
    )

    project = _project(project_path) if project_path else _project(param_path).parent
    param_file = _default_param_path(project, param_path)
    machine_file = _default_machine_path(project, machine_path)
    warnings: list[str] = []
    errors: list[str] = []
    artifacts: list[dict[str, Any]] = []

    param_data, param_errors = _load_config(param_file)
    machine_data, machine_errors = _load_config(machine_file)
    errors.extend(param_errors)
    errors.extend(machine_errors)
    for path in (param_file, machine_file):
        if path.is_file():
            artifacts.append(artifact(path, "config"))
        else:
            errors.append(f"Missing config file: {path}")

    if not isinstance(param_data, dict) or not isinstance(machine_data, dict):
        return result(
            status="failed",
            summary="Training input validation failed before structural checks.",
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )

    warnings.extend(_dpgen_schema_warnings(param_data, machine_data))
    warnings.extend(_machine_secret_warnings(machine_data))

    type_map = param_data.get("type_map") or (param_data.get("default_training_param") or {}).get("model", {}).get("type_map")
    mass_map = param_data.get("mass_map")
    if isinstance(type_map, list) and isinstance(mass_map, list) and len(type_map) != len(mass_map):
        errors.append("type_map and mass_map lengths differ.")

    init_data = param_data.get("init_data_sys")
    init_batch = param_data.get("init_batch_size")
    if isinstance(init_data, list) and isinstance(init_batch, list) and len(init_data) != len(init_batch):
        warnings.append("init_batch_size length does not match init_data_sys length.")
    if isinstance(init_data, list):
        prefix = resolve_asset(param_file.parent, param_data.get("init_data_prefix") or ".") or param_file.parent
        for raw in init_data:
            resolved = resolve_asset(prefix, raw)
            if resolved is not None and not resolved.exists():
                warnings.append(f"init_data_sys path does not exist: {resolved}")

    sys_configs = param_data.get("sys_configs")
    sys_batch = param_data.get("sys_batch_size")
    if isinstance(sys_configs, list) and isinstance(sys_batch, list) and len(sys_configs) != len(sys_batch):
        warnings.append("sys_batch_size length does not match sys_configs length.")
    sys_configs_count = len(sys_configs) if isinstance(sys_configs, list) else 0
    if isinstance(sys_configs, list):
        prefix = resolve_asset(param_file.parent, param_data.get("sys_configs_prefix") or ".") or param_file.parent
        for group_idx, group in enumerate(sys_configs):
            if not isinstance(group, list):
                errors.append(f"sys_configs[{group_idx}] is not a list.")
                continue
            for raw in group:
                resolved = resolve_asset(prefix, raw)
                if resolved is not None and not resolved.exists():
                    warnings.append(f"sys_configs path does not exist: {resolved}")

    for idx, job in enumerate(param_data.get("model_devi_jobs") or []):
        if not isinstance(job, dict):
            errors.append(f"model_devi_jobs[{idx}] is not an object.")
            continue
        for sys_idx in job.get("sys_idx") or []:
            if isinstance(sys_idx, int) and sys_configs_count and sys_idx >= sys_configs_count:
                errors.append(f"model_devi_jobs[{idx}].sys_idx contains out-of-range index {sys_idx}.")

    template_checks = collect_dpgen_template_checks(
        project_path=project,
        param_path=param_file,
        param_data=param_data,
    )
    for check in template_checks:
        if not check.exists:
            warnings.append(f"Referenced template/asset does not exist: {check.role}: {check.resolved_path}")
        for variable in check.missing_variables:
            warnings.append(f"Template variable may be missing for {check.role}: {variable} in {check.resolved_path}")
        if check.exists and check.resolved_path.is_file():
            artifacts.append(artifact(check.resolved_path, "config"))

    for section in ("train", "model_devi", "fp"):
        payload = _latest_machine_stage(machine_data, section, errors)
        if payload is None:
            continue
        command = payload.get("command")
        if not command:
            warnings.append(f"machine.{section}.command is empty.")
        script = _wrapper_script_from_command(command)
        if script is not None:
            if script.exists() and script.is_file():
                artifacts.append(artifact(script, "config"))
            elif script.is_absolute():
                warnings.append(f"machine.{section}.command wrapper script does not exist locally: {script}")
        remote_root = ((payload.get("machine") or {}) if isinstance(payload.get("machine"), dict) else {}).get("remote_root")
        if not remote_root:
            warnings.append(f"machine.{section}.machine.remote_root is empty.")

    return result(
        status="failed" if errors else "success",
        summary="Training input validation completed." if not errors else "Training input validation found blocking errors.",
        metrics={
            "backend": backend,
            "param_path": str(param_file),
            "machine_path": str(machine_file),
            "template_checks": [check.to_dict() for check in template_checks],
            "warnings_count": len(warnings),
            "errors_count": len(errors),
        },
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )


def validate_machine_runtime(
    backend: str,
    *,
    machine_path: str,
    project_path: str | None = None,
    stages: str = "train,model_devi,fp",
    timeout_seconds: int = 60,
    max_log_chars: int = 4000,
    exact: bool = False,
    probe_args_json: str | None = None,
    output_path: str | None = None,
) -> str:
    from .dpgen_common import (
        _load_config,
        _load_probe_args,
        _parse_stage_list,
        _project,
        _run_machine_probe,
    )

    machine_file = _project(machine_path)
    cwd = _project(project_path) if project_path else machine_file.parent
    warnings: list[str] = []
    errors: list[str] = []
    artifacts_payload: list[dict[str, Any]] = []

    if timeout_seconds <= 0:
        warnings.append("timeout_seconds must be positive; using 60.")
        timeout_seconds = 60
    if timeout_seconds > 300:
        warnings.append("timeout_seconds capped at 300 seconds.")
        timeout_seconds = 300
    if max_log_chars < 100:
        warnings.append("max_log_chars raised to 100.")
        max_log_chars = 100

    machine_data, load_errors = _load_config(machine_file)
    errors.extend(load_errors)
    if machine_file.is_file():
        artifacts_payload.append(artifact(machine_file, "config"))
    else:
        errors.append(f"Missing machine file: {machine_file}")
    if not cwd.is_dir():
        errors.append(f"Project/cwd path does not exist: {cwd}")
    if not isinstance(machine_data, dict):
        return result(
            status="failed",
            summary="Machine runtime validation failed before command probes.",
            metrics={"backend": backend, "machine_path": str(machine_file), "cwd": str(cwd)},
            artifacts=artifacts_payload,
            warnings=warnings,
            errors=errors,
        )

    selected_stages = _parse_stage_list(stages)
    if not selected_stages:
        errors.append(f"No valid stages selected: {stages}")
    probe_args = _load_probe_args(probe_args_json, warnings)
    if exact:
        warnings.append("exact=true runs machine.json commands as written; this may start expensive calculations.")

    probes: list[dict[str, Any]] = []
    if not errors:
        for stage in selected_stages:
            section = _latest_machine_stage(machine_data, stage, errors)
            if section is None:
                probes.append(
                    {
                        "stage": stage,
                        "status": "skipped",
                        "error": f"machine.{stage} is not in the current DP-GEN machine schema.",
                    }
                )
                continue
            command = section.get("command")
            if not isinstance(command, str) or not command.strip():
                probes.append({"stage": stage, "status": "skipped", "error": f"machine.{stage}.command is empty."})
                errors.append(f"machine.{stage}.command is empty.")
                continue
            probes.append(
                _run_machine_probe(
                    command=command,
                    stage=stage,
                    cwd=cwd,
                    exact=exact,
                    probe_args=probe_args.get(stage, []),
                    timeout_seconds=timeout_seconds,
                    max_log_chars=max_log_chars,
                )
            )

    failures = [
        item
        for item in probes
        if item.get("timed_out") or (isinstance(item.get("returncode"), int) and item.get("returncode") != 0)
    ]
    report_path = _project(output_path) if output_path else machine_file.with_name("machine_runtime_validation.json")
    report_payload = {
        "schema_version": 1,
        "backend": backend,
        "machine_path": str(machine_file),
        "cwd": str(cwd),
        "stages": selected_stages,
        "mode": "exact" if exact else "probe",
        "timeout_seconds": timeout_seconds,
        "max_log_chars": max_log_chars,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "probes": probes,
        "warnings": warnings,
        "errors": errors,
    }
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        artifacts_payload.append(artifact(report_path, "status"))
    except OSError as exc:
        errors.append(f"Failed to write machine runtime validation report: {report_path}: {exc}")

    status = "failed" if errors or failures else "success"
    summary = (
        f"Machine runtime probes completed: {len(probes) - len(failures)}/{len(probes)} passed."
        if not errors
        else "Machine runtime validation found blocking errors."
    )
    return result(
        status=status,
        summary=summary,
        metrics={
            "backend": backend,
            "machine_path": str(machine_file),
            "cwd": str(cwd),
            "mode": "exact" if exact else "probe",
            "stages": selected_stages,
            "probes_run": len(probes),
            "failures": len(failures),
            "report_path": str(report_path),
        },
        artifacts=artifacts_payload,
        warnings=warnings,
        errors=errors,
    )
