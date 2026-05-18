"""DP-GEN config generation operations."""

from __future__ import annotations

from typing import Any

from ..config_builder import build_dpgen_machine, build_dpgen_param
from ..schemas import result, sha256_file


def generate_training_param(
    backend: str,
    *,
    system_profile_path: str,
    strategy_config_path: str,
    output_path: str,
) -> str:
    from .dpgen_common import (
        _dpgen_param_schema_warnings,
        _project,
        _sync_project_run_config,
        _write_manifest,
    )

    system_profile = _project(system_profile_path)
    strategy_config = _project(strategy_config_path)
    output = _project(output_path)
    warnings: list[str] = []
    errors: list[str] = []
    artifacts: list[dict[str, Any]] = []
    try:
        payload, artifacts, warnings = build_dpgen_param(
            system_profile_path=system_profile,
            strategy_config_path=strategy_config,
            output_path=output,
        )
        _sync_project_run_config(output, "param.json", artifacts, warnings)
        warnings.extend(_dpgen_param_schema_warnings(payload))
        manifest_artifact = _write_manifest(
            output.parent,
            source="generate_training_param",
            inputs=[
                {"path": str(system_profile), "sha256": sha256_file(system_profile) if system_profile.is_file() else None},
                {"path": str(strategy_config), "sha256": sha256_file(strategy_config) if strategy_config.is_file() else None},
            ],
            outputs=[{"path": str(output), "sha256": sha256_file(output) if output.is_file() else None}],
            artifacts_payload=artifacts,
            warnings=warnings,
            errors=errors,
        )
        if manifest_artifact is not None:
            artifacts.append(manifest_artifact)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        payload = {}
    return result(
        status="failed" if errors else "success",
        summary="Generated DP-GEN backend training param." if not errors else "Failed to generate DP-GEN backend training param.",
        metrics={
            "backend": backend,
            "system_profile_path": str(system_profile),
            "strategy_config_path": str(strategy_config),
            "output_path": str(output),
            "output_sha256": sha256_file(output) if output.is_file() else None,
            "keys": sorted(payload) if isinstance(payload, dict) else [],
        },
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )


def generate_training_machine(
    backend: str,
    *,
    machine_profile_path: str,
    output_path: str,
) -> str:
    from .dpgen_common import (
        _dpgen_machine_schema_warnings,
        _project,
        _sync_project_run_config,
        _write_manifest,
    )

    machine_profile = _project(machine_profile_path)
    output = _project(output_path)
    warnings: list[str] = []
    errors: list[str] = []
    artifacts: list[dict[str, Any]] = []
    redacted: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    try:
        payload, redacted, artifacts, warnings = build_dpgen_machine(
            machine_profile_path=machine_profile,
            output_path=output,
        )
        _sync_project_run_config(output, "machine.json", artifacts, warnings)
        warnings.extend(_dpgen_machine_schema_warnings(payload))
        manifest_artifact = _write_manifest(
            output.parent,
            source="generate_training_machine",
            inputs=[{"path": str(machine_profile), "sha256": sha256_file(machine_profile) if machine_profile.is_file() else None}],
            outputs=[{"path": str(output), "sha256": sha256_file(output) if output.is_file() else None}],
            artifacts_payload=artifacts,
            warnings=warnings,
            errors=errors,
        )
        if manifest_artifact is not None:
            artifacts.append(manifest_artifact)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return result(
        status="failed" if errors else "success",
        summary="Generated DP-GEN backend training machine config." if not errors else "Failed to generate DP-GEN backend training machine config.",
        metrics={
            "backend": backend,
            "machine_profile_path": str(machine_profile),
            "output_path": str(output),
            "output_sha256": sha256_file(output) if output.is_file() else None,
            "redacted_preview": redacted,
            "sections": sorted(key for key in payload if key in {"train", "model_devi", "fp"}),
        },
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
    )
