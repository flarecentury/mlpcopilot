"""DP-GEN param/machine config update operations."""

from __future__ import annotations

import json

from ..schemas import artifact, result, sha256_file
from ..secret_redactor import redact_mapping


def plan_config_update(
    backend: str,
    *,
    config_kind: str,
    config_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    normalized_kind = config_kind.lower().strip()
    if normalized_kind not in {"machine", "param"}:
        return result(
            status="failed",
            summary="Could not prepare config update plan.",
            metrics={"backend": backend, "config_kind": config_kind, "config_path": config_path},
            errors=["config_kind must be 'machine' or 'param'."],
        )
    return _plan_config_update(backend, normalized_kind, config_path, updates_json, replacement_path)


def apply_config_update(
    backend: str,
    *,
    config_kind: str,
    config_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    normalized_kind = config_kind.lower().strip()
    if normalized_kind not in {"machine", "param"}:
        return result(
            status="failed",
            summary="Could not apply config update.",
            metrics={"backend": backend, "config_kind": config_kind, "config_path": config_path},
            errors=["config_kind must be 'machine' or 'param'."],
        )
    return _apply_config_update(
        backend,
        normalized_kind,
        config_path,
        updates_json,
        replacement_path,
    )


def plan_machine_update(
    backend: str,
    *,
    machine_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    return _plan_config_update(backend, "machine", machine_path, updates_json, replacement_path)


def apply_machine_update(
    backend: str,
    *,
    machine_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    return _apply_config_update(
        backend,
        "machine",
        machine_path,
        updates_json,
        replacement_path,
    )


def plan_param_update(
    backend: str,
    *,
    param_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    return _plan_config_update(backend, "param", param_path, updates_json, replacement_path)


def apply_param_update(
    backend: str,
    *,
    param_path: str,
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    return _apply_config_update(
        backend,
        "param",
        param_path,
        updates_json,
        replacement_path,
    )


def _plan_config_update(
    backend: str,
    config_kind: str,
    config_path: str,
    updates_json: str | None,
    replacement_path: str | None,
) -> str:
    from .dpgen_common import (
        _config_update_plan,
        _dpgen_machine_schema_warnings,
        _dpgen_param_schema_warnings,
        _project,
    )

    path = _project(config_path)
    errors: list[str] = []
    _, after, diff = _config_update_plan(
        config_path=path,
        updates_json=updates_json,
        replacement_path=replacement_path,
        errors=errors,
    )
    warnings: list[str] = []
    if after is not None:
        warnings.extend(_dpgen_machine_schema_warnings(after) if config_kind == "machine" else _dpgen_param_schema_warnings(after))
    if config_kind == "machine":
        after_preview = redact_mapping(after)[0] if after is not None else after
        diff_preview = redact_mapping({"diff": diff})[0]["diff"]
    else:
        after_preview = after
        diff_preview = diff
    return result(
        status="failed" if errors else "success",
        summary=f"Prepared {config_kind}.json update plan." if not errors else f"Could not prepare {config_kind}.json update plan.",
        metrics={
            "backend": backend,
            "config_kind": config_kind,
            "config_path": str(path),
            "replacement_path": replacement_path,
            "diff": diff_preview,
            "changes": len(diff),
            "before_sha256": sha256_file(path) if path.is_file() else None,
            "after_preview": after_preview,
        },
        artifacts=[artifact(path, "config")] if path.is_file() else [],
        warnings=warnings,
        errors=errors,
    )


def _apply_config_update(
    backend: str,
    config_kind: str,
    config_path: str,
    updates_json: str | None,
    replacement_path: str | None,
) -> str:
    from .dpgen_common import _backup_file, _config_update_plan, _json_write, _now_iso, _project

    plan = json.loads(_plan_config_update(backend, config_kind, config_path, updates_json, replacement_path))
    if plan.get("status") == "failed":
        return json.dumps(plan, indent=2, ensure_ascii=False, sort_keys=True)
    path = _project(config_path)
    errors: list[str] = []
    _, after, _ = _config_update_plan(
        config_path=path,
        updates_json=updates_json,
        replacement_path=replacement_path,
        errors=errors,
    )
    if after is None:
        return result(
            status="failed",
            summary=f"Failed to rebuild {config_kind}.json update payload.",
            metrics={"backend": backend, "config_path": str(path)},
            errors=errors,
        )
    backup_dir = path.parent / ".mlpcopilot" / "backups" / f"{config_kind}_update_{_now_iso().replace(':', '').replace('+', 'Z')}"
    artifacts_payload: list[dict[str, str]] = []
    backup: dict[str, str] | None = None
    try:
        backup = _backup_file(path, backup_dir)
        _json_write(path, after)
        artifacts_payload.append(artifact(path, "config"))
        if backup:
            manifest = backup_dir / "update_manifest.json"
            _json_write(manifest, {"schema_version": 1, "created_at": _now_iso(), "plan": plan["metrics"], "backup": backup})
            artifacts_payload.append(artifact(manifest, "manifest"))
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    return result(
        status="failed" if errors else "success",
        summary=f"Applied {config_kind}.json update." if not errors else f"Failed to apply {config_kind}.json update.",
        metrics={**plan["metrics"], "backup": backup, "after_sha256": sha256_file(path) if path.is_file() else None},
        artifacts=artifacts_payload,
        warnings=plan.get("warnings") or [],
        errors=errors,
    )
