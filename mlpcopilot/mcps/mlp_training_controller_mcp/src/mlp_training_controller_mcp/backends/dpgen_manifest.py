"""DP-GEN execution evidence manifests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..schemas import artifact


def write_controller_manifest(
    project: Path,
    *,
    backend: str,
    operation: str,
    state: dict[str, Any],
    artifacts_payload: list[dict[str, Any]],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any] | None:
    """Record start/stop controller evidence in project/runs/<run_id>/manifest.json."""
    run_id = str(state.get("run_id") or "").strip()
    if not run_id:
        return None
    param_ref = _file_ref(state.get("param_path"), artifact_type="config", sha256=state.get("param_sha256"))
    machine_ref = _file_ref(
        state.get("machine_path"),
        artifact_type="config",
        sha256=state.get("machine_sha256"),
    )
    state_ref = _file_ref(state.get("state_path"), artifact_type="status")
    log_refs = [
        ref
        for ref in (
            _file_ref(state.get("stdout_log"), artifact_type="log"),
            _file_ref(state.get("stderr_log"), artifact_type="log"),
        )
        if ref is not None
    ]
    inputs = [ref for ref in (param_ref, machine_ref) if ref is not None]
    outputs = [ref for ref in (state_ref, *log_refs) if ref is not None]
    metrics = [
        _metric("controller_status", state.get("status"), state.get("state_path")),
        _metric("process_id", state.get("pid"), state.get("state_path")),
        _metric("exit_code", state.get("exit_code"), state.get("state_path")),
    ]
    lineage = {
        "inputs": inputs,
        "resume_from_record": state.get("resume_from_record") or {},
    }
    metadata = {
        "backend": backend,
        "operation": operation,
        "cwd": state.get("cwd"),
        "command": state.get("command"),
        "mode": state.get("mode"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "warnings": warnings or state.get("warnings") or [],
        "events": [
            {
                "operation": operation,
                "created_at": _now_iso(),
                "status": state.get("status"),
                "state_path": state.get("state_path"),
            }
        ],
    }
    return upsert_manifest(
        project,
        run_id=run_id,
        source=f"mcp:trainingController:{operation}",
        inputs=inputs,
        outputs=outputs,
        artifacts=artifacts_payload,
        metrics=[item for item in metrics if item is not None],
        lineage=lineage,
        metadata=metadata,
        errors=errors or [],
    )


def write_reset_manifest(
    project: Path,
    *,
    backend: str,
    operation: str,
    run_id: str,
    plan: dict[str, Any],
    artifacts_payload: list[dict[str, Any]],
    backups: list[dict[str, Any]],
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Record reset/rewind evidence in project/runs/<run_id>/manifest.json."""
    record_ref = _file_ref(project / "record.dpgen", artifact_type="status")
    inputs = [record_ref] if record_ref else []
    metrics = [
        _metric("target_iteration", plan.get("target_record", {}).get("iteration"), record_ref.get("path") if record_ref else None),
        _metric("target_stage", plan.get("target_record", {}).get("stage"), record_ref.get("path") if record_ref else None),
        _metric("hard_mode_iter_dirs_to_move", len(plan.get("hard_mode_iter_dirs_to_move") or []), None),
        _metric("backups", len(backups), None),
    ]
    metadata = {
        "backend": backend,
        "operation": operation,
        "mode": plan.get("mode"),
        "backup_dir": plan.get("backup_dir"),
        "warnings": warnings or [],
        "events": [
            {
                "operation": operation,
                "created_at": _now_iso(),
                "status": "failed" if errors else "success",
                **(event_metadata or {}),
            }
        ],
    }
    return upsert_manifest(
        project,
        run_id=run_id,
        source=f"mcp:trainingController:{operation}",
        inputs=inputs,
        outputs=artifacts_payload,
        artifacts=artifacts_payload,
        metrics=[item for item in metrics if item is not None],
        lineage={
            "current_record": plan.get("current_record") or {},
            "target_record": plan.get("target_record") or {},
            "backups": backups,
        },
        metadata=metadata,
        errors=errors or [],
    )


def upsert_manifest(
    project: Path,
    *,
    run_id: str,
    source: str,
    inputs: list[Any],
    outputs: list[Any],
    artifacts: list[Any],
    metrics: list[Any],
    lineage: dict[str, Any],
    metadata: dict[str, Any],
    errors: list[Any],
) -> dict[str, Any] | None:
    """Create or update a runtime-compatible manifest and return its artifact ref."""
    manifest_path = project / "runs" / run_id / "manifest.json"
    try:
        from mlpcopilot.runtime.artifacts import ArtifactIndex

        index = ArtifactIndex(project)
        try:
            existing = index.load(run_id)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            existing = None
        if existing is None:
            index.create_run(
                run_id=run_id,
                source=source,
                inputs=inputs,
                outputs=outputs,
                artifacts=artifacts,
                metrics=metrics,
                lineage=lineage,
                errors=errors,
                metadata=metadata,
            )
        else:
            index.update(
                run_id,
                source=existing.source or source,
                inputs=_merge_unique(existing.inputs, inputs),
                outputs=_merge_unique(existing.outputs, outputs),
                artifacts=_merge_unique(existing.artifacts, artifacts),
                metrics=_merge_metrics(existing.metrics, metrics),
                lineage={**existing.lineage, **lineage},
                errors=_merge_unique(existing.errors, errors),
                metadata=_merge_metadata(existing.metadata, metadata),
            )
    except Exception:
        _write_fallback_manifest(
            manifest_path,
            run_id=run_id,
            source=source,
            inputs=inputs,
            outputs=outputs,
            artifacts=artifacts,
            metrics=metrics,
            lineage=lineage,
            metadata=metadata,
            errors=errors,
        )
    return artifact(manifest_path, "manifest") if manifest_path.is_file() else None


def _write_fallback_manifest(
    path: Path,
    *,
    run_id: str,
    source: str,
    inputs: list[Any],
    outputs: list[Any],
    artifacts: list[Any],
    metrics: list[Any],
    lineage: dict[str, Any],
    metadata: dict[str, Any],
    errors: list[Any],
) -> None:
    existing = _read_existing_manifest(path)
    payload = {
        "run_id": run_id,
        "created_at": existing.get("created_at") or _now_iso(),
        "source": existing.get("source") or source,
        "inputs": _merge_unique(_as_list(existing.get("inputs")), inputs),
        "outputs": _merge_unique(_as_list(existing.get("outputs")), outputs),
        "artifacts": _merge_unique(_as_list(existing.get("artifacts")), artifacts),
        "metrics": _merge_metrics(_as_list(existing.get("metrics")), metrics),
        "lineage": {**_as_dict(existing.get("lineage")), **lineage},
        "decisions": _as_list(existing.get("decisions")),
        "approval": existing.get("approval"),
        "errors": _merge_unique(_as_list(existing.get("errors")), errors),
        "metadata": _merge_metadata(_as_dict(existing.get("metadata")), metadata),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _read_existing_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _file_ref(raw_path: Any, *, artifact_type: str, sha256: Any | None = None) -> dict[str, Any] | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    ref: dict[str, Any] = {"type": artifact_type, "path": str(path)}
    if isinstance(sha256, str) and sha256:
        ref["sha256"] = sha256
    elif path.is_file():
        ref["sha256"] = artifact(path, artifact_type)["sha256"]
    return ref


def _metric(name: str, value: Any, source: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    metric: dict[str, Any] = {"name": name, "value": value}
    if source:
        metric["source"] = str(source)
    return metric


def _merge_unique(left: list[Any], right: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for item in [*left, *right]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _merge_metrics(left: list[Any], right: list[Any]) -> list[Any]:
    merged: list[Any] = []
    index: dict[tuple[str, str], int] = {}
    for item in [*left, *right]:
        if isinstance(item, dict) and item.get("name"):
            key = (str(item.get("name")), str(item.get("source") or item.get("source_artifact") or item.get("path") or ""))
            if key in index:
                merged[index[key]] = item
                continue
            index[key] = len(merged)
        elif item in merged:
            continue
        merged.append(item)
    return merged


def _merge_metadata(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key == "events":
            merged[key] = _merge_unique(_as_list(merged.get(key)), _as_list(value))
        elif key == "warnings":
            merged[key] = _merge_unique(_as_list(merged.get(key)), _as_list(value))
        else:
            merged[key] = value
    return merged


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
