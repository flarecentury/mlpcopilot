"""Checkpoint metadata and precomputed metrics artifact handling."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .ase_predict import (
    batch_predict_with_ase,
    predict_structure_with_ase,
)
from .deepmd_test import (
    deepmd_v3_model_format,
    run_deepmd_test_command,
)
from .plots import build_benchmark_plot_artifacts
from .schemas import artifact, load_json_or_yaml, result, sha256_file

CHECKPOINT_NAME_HINTS = (
    "checkpoint",
    "saved_model.pb",
    "frozen_model.pb",
    "graph.pb",
    "model.ckpt",
    "model.pte",
    "frozen_model.pte",
)


class ModelEvalBackend:
    """File-based checkpoint inspection and metrics artifact backend."""

    def inspect_checkpoint(self, checkpoint_path: str, max_files: int = 100) -> str:
        path = _resolve(checkpoint_path)
        if not path.exists():
            return result(
                status="failed",
                summary="Checkpoint path does not exist.",
                metrics={"checkpoint_path": str(path)},
                errors=[f"No such path: {path}"],
            )
        try:
            payload = inspect_checkpoint_path(path, max_files=max_files)
        except OSError as exc:
            return result(
                status="failed",
                summary="Failed to inspect checkpoint.",
                metrics={"checkpoint_path": str(path)},
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        return result(
            status="success",
            summary=f"Inspected checkpoint path: {path}",
            metrics=payload,
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
        )

    def validate_checkpoint_on_dataset(
        self,
        checkpoint_path: str,
        dataset_path: str,
        metric_config_path: str | None = None,
        run_if_metrics_missing: bool = False,
        dp_command: str = "dp",
        backend: str | None = None,
        data_source: str = "system",
        numb_test: int = 0,
        rand_seed: int | None = None,
        shuffle_test: bool = False,
        atomic: bool = False,
        head: str | None = None,
        output_dir: str | None = None,
        timeout_seconds: int = 60,
    ) -> str:
        checkpoint = _resolve(checkpoint_path)
        dataset = _resolve(dataset_path)
        errors: list[str] = []
        warnings: list[str] = []
        artifacts: list[dict[str, Any]] = []
        if not checkpoint.exists():
            errors.append(f"No such checkpoint path: {checkpoint}")
        elif checkpoint.is_file():
            artifacts.append(artifact(checkpoint, "checkpoint"))
        if not dataset.exists():
            errors.append(f"No such dataset path: {dataset}")
        metrics_payload: dict[str, Any] = {}
        metrics_artifacts: list[dict[str, Any]] = []
        if metric_config_path:
            loaded, loaded_artifacts, loaded_errors = _load_metrics_bundle(metric_config_path)
            metrics_payload = loaded
            metrics_artifacts = loaded_artifacts
            errors.extend(loaded_errors)
        elif run_if_metrics_missing:
            warnings.append("No metric_config_path was provided; running DeePMD-kit dp test.")
        else:
            warnings.append("No metric_config_path was provided; no benchmark metrics were checked.")
        if not errors and not metrics_payload and run_if_metrics_missing:
            run_payload = self.run_deepmd_test(
                checkpoint_path=str(checkpoint),
                dataset_path=str(dataset),
                data_source=data_source,
                dp_command=dp_command,
                backend=backend,
                numb_test=numb_test,
                rand_seed=rand_seed,
                shuffle_test=shuffle_test,
                atomic=atomic,
                head=head,
                output_dir=output_dir,
                timeout_seconds=timeout_seconds,
            )
            loaded_run = json.loads(run_payload)
            artifacts.extend(loaded_run.get("artifacts") or [])
            warnings.extend(loaded_run.get("warnings") or [])
            errors.extend(loaded_run.get("errors") or [])
            run_metrics = loaded_run.get("metrics")
            if isinstance(run_metrics, dict):
                metrics_payload = {"metrics": run_metrics.get("metrics") or {}}
        artifacts.extend(metrics_artifacts)
        metrics = _extract_metrics(metrics_payload)
        criteria = _extract_acceptance_criteria(metrics_payload)
        acceptance = _evaluate_acceptance(metrics, criteria)
        if errors:
            status = "failed"
            summary = "Checkpoint validation inputs are invalid."
        elif not metrics:
            status = "blocked"
            summary = (
                "No precomputed metrics were available. This first-pass MCP does not run "
                "checkpoint inference."
            )
        elif acceptance["failures"]:
            status = "failed"
            summary = "Checkpoint metrics failed acceptance criteria."
        elif not criteria:
            status = "success"
            summary = "Checkpoint metrics were collected; no acceptance criteria were supplied."
        else:
            status = "success"
            summary = "Checkpoint metrics passed the available acceptance checks."
        return result(
            status=status,
            summary=summary,
            metrics={
                "checkpoint_path": str(checkpoint),
                "dataset_path": str(dataset),
                "checked_metrics": metrics,
                "acceptance_criteria": criteria,
                "acceptance": acceptance,
                "inference_executed": bool(run_if_metrics_missing and metrics),
            },
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )

    def run_deepmd_test(
        self,
        checkpoint_path: str,
        dataset_path: str,
        data_source: str = "system",
        dp_command: str = "dp",
        backend: str | None = None,
        numb_test: int = 0,
        rand_seed: int | None = None,
        shuffle_test: bool = False,
        atomic: bool = False,
        head: str | None = None,
        output_dir: str | None = None,
        timeout_seconds: int = 60,
    ) -> str:
        """Run DeePMD-kit v3 ``dp test`` and capture benchmark evidence."""
        payload = run_deepmd_test_command(
            checkpoint_path=_resolve(checkpoint_path),
            dataset_path=_resolve(dataset_path),
            data_source=data_source,
            dp_command=dp_command,
            backend=backend,
            numb_test=numb_test,
            rand_seed=rand_seed,
            shuffle_test=shuffle_test,
            atomic=atomic,
            head=head,
            output_dir=_resolve(output_dir) if output_dir else None,
            timeout_seconds=timeout_seconds,
        )
        return result(
            status=payload["status"],
            summary=payload["summary"],
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
            errors=payload.get("errors") if isinstance(payload.get("errors"), list) else [],
        )

    def predict_energy_force(
        self,
        structure_path: str,
        checkpoint_path: str,
        structure_format: str | None = None,
        frame_index: int = 0,
        output_path: str | None = None,
        extxyz_path: str | None = None,
        head: str | None = None,
        max_inline_atoms: int = 64,
    ) -> str:
        """Predict energy and forces for one ASE-readable structure."""
        payload = predict_structure_with_ase(
            structure_path=_resolve(structure_path),
            checkpoint_path=_resolve(checkpoint_path),
            structure_format=structure_format,
            frame_index=frame_index,
            output_path=_resolve(output_path) if output_path else None,
            extxyz_path=_resolve(extxyz_path) if extxyz_path else None,
            head=head,
            max_inline_atoms=max_inline_atoms,
        )
        return result(
            status=payload["status"],
            summary=payload["summary"],
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
            errors=payload.get("errors") if isinstance(payload.get("errors"), list) else [],
        )

    def batch_predict(
        self,
        structure_dir: str,
        checkpoint_path: str,
        structure_glob: str = "*",
        recursive: bool = True,
        structure_format: str | None = None,
        output_dir: str | None = None,
        head: str | None = None,
        max_structures: int = 200,
        write_extxyz: bool = True,
    ) -> str:
        """Predict energy and forces for ASE-readable structure files."""
        payload = batch_predict_with_ase(
            structure_dir=_resolve(structure_dir),
            checkpoint_path=_resolve(checkpoint_path),
            structure_glob=structure_glob,
            recursive=recursive,
            structure_format=structure_format,
            output_dir=_resolve(output_dir) if output_dir else None,
            head=head,
            max_structures=max_structures,
            write_extxyz=write_extxyz,
        )
        return result(
            status=payload["status"],
            summary=payload["summary"],
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
            errors=payload.get("errors") if isinstance(payload.get("errors"), list) else [],
        )

    def compare_checkpoints(
        self,
        checkpoint_a: str,
        checkpoint_b: str,
        dataset_path: str | None = None,
        metric_config_path: str | None = None,
    ) -> str:
        path_a = _resolve(checkpoint_a)
        path_b = _resolve(checkpoint_b)
        errors: list[str] = []
        warnings: list[str] = []
        artifacts: list[dict[str, Any]] = []
        for label, path in (("checkpoint_a", path_a), ("checkpoint_b", path_b)):
            if not path.exists():
                errors.append(f"No such {label}: {path}")
            elif path.is_file():
                artifacts.append(artifact(path, "checkpoint"))
        if dataset_path and not _resolve(dataset_path).exists():
            errors.append(f"No such dataset path: {_resolve(dataset_path)}")
        metrics_payload: dict[str, Any] = {}
        if metric_config_path:
            metrics_payload, loaded_artifacts, loaded_errors = _load_metrics_bundle(metric_config_path)
            artifacts.extend(loaded_artifacts)
            errors.extend(loaded_errors)
        else:
            warnings.append("No metric_config_path was provided; compared checkpoint metadata only.")
        comparison = _compare_metrics(metrics_payload, path_a, path_b)
        return result(
            status="failed" if errors else "success",
            summary="Compared checkpoint metadata and available metrics.",
            metrics={
                "checkpoint_a": _checkpoint_summary_if_exists(path_a),
                "checkpoint_b": _checkpoint_summary_if_exists(path_b),
                "dataset_path": str(_resolve(dataset_path)) if dataset_path else None,
                "comparison": comparison,
                "inference_executed": False,
            },
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )

    def build_checkpoint_metrics(
        self,
        metrics_path: str,
        checkpoint_path: str | None = None,
        dataset_path: str | None = None,
        output_path: str | None = None,
    ) -> str:
        metrics_file = _resolve(metrics_path)
        if not metrics_file.is_file():
            return result(
                status="failed",
                summary="Metrics artifact does not exist.",
                metrics={"metrics_path": str(metrics_file)},
                errors=[f"No such metrics artifact: {metrics_file}"],
            )
        try:
            payload = load_json_or_yaml(metrics_file)
        except Exception as exc:
            return result(
                status="failed",
                summary="Failed to read metrics artifact.",
                metrics={"metrics_path": str(metrics_file)},
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        normalized = {
            "created_at": datetime.now(UTC).isoformat(),
            "checkpoint_path": str(_resolve(checkpoint_path)) if checkpoint_path else None,
            "dataset_path": str(_resolve(dataset_path)) if dataset_path else None,
            "source_metrics_path": str(metrics_file),
            "source_metrics_sha256": sha256_file(metrics_file),
            "metrics": _extract_metrics(payload if isinstance(payload, dict) else {}),
            "acceptance_criteria": _extract_acceptance_criteria(payload)
            if isinstance(payload, dict)
            else {},
        }
        target = _resolve(output_path) if output_path else metrics_file.with_suffix(".normalized.json")
        errors: list[str] = []
        artifacts = [artifact(metrics_file, "metrics")]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
            artifacts.append(artifact(target, "metrics"))
        except OSError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        return result(
            status="failed" if errors else "success",
            summary=f"Wrote normalized checkpoint metrics: {target}"
            if not errors
            else "Failed to write normalized checkpoint metrics.",
            metrics=normalized,
            artifacts=artifacts,
            errors=errors,
        )

    def build_checkpoint_benchmark_report(
        self,
        metrics_path: str,
        checkpoint_path: str | None = None,
        dataset_path: str | None = None,
        output_path: str | None = None,
        plot_paths: list[str] | None = None,
        title: str = "Checkpoint Benchmark Report",
        max_hash_files: int = 500,
    ) -> str:
        """Build a human-readable benchmark report from existing metrics artifacts."""
        metrics_file = _resolve(metrics_path)
        if not metrics_file.is_file():
            return result(
                status="failed",
                summary="Metrics artifact does not exist.",
                metrics={"metrics_path": str(metrics_file)},
                errors=[f"No such metrics artifact: {metrics_file}"],
            )
        try:
            payload = load_json_or_yaml(metrics_file)
        except Exception as exc:
            return result(
                status="failed",
                summary="Failed to read metrics artifact.",
                metrics={"metrics_path": str(metrics_file)},
                errors=[f"{type(exc).__name__}: {exc}"],
            )
        if not isinstance(payload, dict):
            return result(
                status="failed",
                summary="Metrics artifact must be a JSON/YAML object.",
                metrics={"metrics_path": str(metrics_file)},
                artifacts=[artifact(metrics_file, "metrics")],
                errors=["Metrics artifact must be a JSON/YAML object."],
            )

        errors: list[str] = []
        warnings: list[str] = []
        metrics = _extract_metrics(payload)
        criteria = _extract_acceptance_criteria(payload)
        acceptance = _evaluate_acceptance(metrics, criteria)
        if not metrics:
            warnings.append("No numeric benchmark metrics were found in the source artifact.")
        resolved_plot_paths, plot_warnings = _resolve_plot_paths(
            payload,
            metrics_file.parent,
            plot_paths or [],
        )
        warnings.extend(plot_warnings)

        checkpoint_evidence = None
        if checkpoint_path:
            checkpoint = _resolve(checkpoint_path)
            if checkpoint.exists():
                checkpoint_evidence = _path_evidence(checkpoint, max_hash_files=max_hash_files)
                if checkpoint_evidence.get("digest_truncated"):
                    warnings.append("Checkpoint directory digest was truncated by max_hash_files.")
            else:
                errors.append(f"No such checkpoint path: {checkpoint}")

        dataset_evidence = None
        if dataset_path:
            dataset = _resolve(dataset_path)
            if dataset.exists():
                dataset_evidence = _path_evidence(dataset, max_hash_files=max_hash_files)
                if dataset_evidence.get("digest_truncated"):
                    warnings.append("Dataset directory digest was truncated by max_hash_files.")
            else:
                errors.append(f"No such dataset path: {dataset}")

        target = _resolve(output_path) if output_path else metrics_file.with_suffix(".benchmark.md")
        artifacts = [artifact(metrics_file, "metrics")]
        artifacts.extend(artifact(path, "plot") for path in resolved_plot_paths if path.is_file())
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                _checkpoint_benchmark_report_markdown(
                    title=title,
                    metrics_path=metrics_file,
                    metrics_sha256=sha256_file(metrics_file),
                    metrics=metrics,
                    criteria=criteria,
                    acceptance=acceptance,
                    checkpoint_evidence=checkpoint_evidence,
                    dataset_evidence=dataset_evidence,
                    plot_paths=resolved_plot_paths,
                    source_payload=payload,
                    warnings=warnings,
                    errors=errors,
                ),
                encoding="utf-8",
            )
            artifacts.append(artifact(target, "report"))
        except OSError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        status = "failed" if errors else "blocked" if not metrics else "success"
        summary = (
            f"Wrote checkpoint benchmark report: {target}"
            if status == "success"
            else "Checkpoint benchmark report was generated with blocking issues."
            if target.is_file()
            else "Failed to write checkpoint benchmark report."
        )
        return result(
            status=status,
            summary=summary,
            metrics={
                "report_path": str(target),
                "source_metrics_path": str(metrics_file),
                "source_metrics_sha256": sha256_file(metrics_file),
                "metric_count": len(metrics),
                "metrics": metrics,
                "acceptance_criteria": criteria,
                "acceptance": acceptance,
                "checkpoint": checkpoint_evidence,
                "dataset": dataset_evidence,
                "plot_paths": [str(path) for path in resolved_plot_paths],
            },
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )

    def build_benchmark_plots(
        self,
        metrics_path: str,
        output_dir: str | None = None,
        detail_prefix: str | None = None,
        energy_detail_path: str | None = None,
        force_detail_path: str | None = None,
        max_points: int = 10000,
    ) -> str:
        """Build parity and error-distribution plots from existing benchmark artifacts."""
        payload = build_benchmark_plot_artifacts(
            metrics_path=_resolve(metrics_path),
            output_dir=_resolve(output_dir) if output_dir else None,
            detail_prefix=_resolve(detail_prefix) if detail_prefix else None,
            energy_detail_path=_resolve(energy_detail_path) if energy_detail_path else None,
            force_detail_path=_resolve(force_detail_path) if force_detail_path else None,
            max_points=max_points,
        )
        return result(
            status=payload["status"],
            summary=payload["summary"],
            metrics=payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            artifacts=payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else [],
            warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
            errors=payload.get("errors") if isinstance(payload.get("errors"), list) else [],
        )


def inspect_checkpoint_path(path: Path, *, max_files: int = 100) -> dict[str, Any]:
    if path.is_file():
        return {
            "checkpoint_path": str(path),
            "kind": "file",
            "format": _checkpoint_file_format(path),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "warnings": [],
        }
    files = [item for item in sorted(path.rglob("*")) if item.is_file()]
    sampled = files[:max_files]
    recognized = [item for item in sampled if _looks_like_checkpoint_file(item)]
    return {
        "checkpoint_path": str(path),
        "kind": "directory",
        "format": "checkpoint_directory" if recognized else "directory",
        "file_count": len(files),
        "sampled_file_count": len(sampled),
        "total_sampled_size_bytes": sum(item.stat().st_size for item in sampled),
        "recognized_checkpoint_files": [str(item) for item in recognized],
        "sample_files": [
            {
                "path": str(item),
                "size_bytes": item.stat().st_size,
                "sha256": sha256_file(item),
            }
            for item in sampled
        ],
        "warnings": ["File inventory truncated by max_files."] if len(files) > max_files else [],
    }


def _resolve(path: str | None) -> Path:
    if not path:
        return Path.cwd().resolve()
    return Path(path).expanduser().resolve()


def _checkpoint_summary_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return inspect_checkpoint_path(path, max_files=50)


def _checkpoint_file_format(path: Path) -> str:
    name = path.name.lower()
    suffix = path.suffix.lower()
    deepmd_format = deepmd_v3_model_format(path)
    if deepmd_format["format"] != "unknown":
        return str(deepmd_format["format"])
    if name == "saved_model.pb":
        return "tensorflow_saved_model"
    if name.endswith(".pb"):
        return "tensorflow_graph_or_deepmd_frozen_model"
    if suffix in {".pt", ".pth"}:
        return "pytorch_checkpoint"
    if suffix in {".ckpt", ".index", ".meta"} or "ckpt" in name:
        return "tensorflow_checkpoint_file"
    if suffix in {".json", ".yaml", ".yml"}:
        return "metadata_or_metrics"
    return "file"


def _looks_like_checkpoint_file(path: Path) -> bool:
    name = path.name.lower()
    return any(hint in name for hint in CHECKPOINT_NAME_HINTS) or _checkpoint_file_format(path) != "file"


def _path_evidence(path: Path, *, max_hash_files: int = 500) -> dict[str, Any]:
    if path.is_file():
        return {
            "path": str(path),
            "kind": "file",
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    files = [item for item in sorted(path.rglob("*")) if item.is_file()]
    sampled = files[:max_hash_files]
    digest = hashlib.sha256()
    total_size = 0
    for item in sampled:
        relative = item.relative_to(path).as_posix()
        total_size += item.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        digest.update(b"\n")
    return {
        "path": str(path),
        "kind": "directory",
        "sha256": digest.hexdigest(),
        "file_count": len(files),
        "sampled_file_count": len(sampled),
        "sampled_size_bytes": total_size,
        "digest_truncated": len(files) > len(sampled),
    }


def _load_metrics_bundle(path_text: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    path = _resolve(path_text)
    errors: list[str] = []
    artifacts: list[dict[str, Any]] = []
    if not path.is_file():
        return {}, [], [f"No such metrics/config file: {path}"]
    try:
        loaded = load_json_or_yaml(path)
        artifacts.append(artifact(path, "metrics"))
    except Exception as exc:
        return {}, [], [f"{type(exc).__name__}: {exc}"]
    if not isinstance(loaded, dict):
        errors.append("Metrics/config artifact must be a JSON/YAML object.")
        return {}, artifacts, errors
    metrics_path = loaded.get("metrics_path")
    if isinstance(metrics_path, str):
        raw_nested_path = Path(metrics_path).expanduser()
        nested_path = (
            raw_nested_path if raw_nested_path.is_absolute() else path.parent / raw_nested_path
        ).resolve()
        if nested_path.is_file():
            try:
                nested = load_json_or_yaml(nested_path)
                artifacts.append(artifact(nested_path, "metrics"))
                if isinstance(nested, dict):
                    loaded = {**loaded, "metrics": _extract_metrics(nested)}
                else:
                    errors.append("Nested metrics artifact must be a JSON/YAML object.")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        else:
            errors.append(f"No such nested metrics artifact: {nested_path}")
    return loaded, artifacts, errors


def _resolve_plot_paths(
    payload: dict[str, Any],
    base_dir: Path,
    explicit_paths: list[str],
) -> tuple[list[Path], list[str]]:
    warnings: list[str] = []
    resolved: list[Path] = []
    seen: set[str] = set()
    candidates: list[Any] = [*explicit_paths]
    plot_paths = payload.get("plot_paths")
    if isinstance(plot_paths, list):
        candidates.extend(plot_paths)
    elif isinstance(plot_paths, str):
        candidates.append(plot_paths)
    plots = payload.get("plots")
    if isinstance(plots, list):
        for item in plots:
            if isinstance(item, dict):
                candidates.append(item.get("path"))
            else:
                candidates.append(item)
    for item in candidates:
        if not isinstance(item, str) or not item.strip():
            continue
        raw = Path(item).expanduser()
        path = raw if raw.is_absolute() else base_dir / raw
        path = path.resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            resolved.append(path)
        else:
            warnings.append(f"Plot artifact does not exist: {path}")
    return resolved, warnings


def _extract_metrics(payload: dict[str, Any]) -> dict[str, float]:
    source = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else payload
    if not isinstance(source, dict):
        return {}
    metrics: dict[str, float] = {}
    _collect_numeric_metrics(source, metrics)
    return metrics


def _collect_numeric_metrics(
    payload: dict[str, Any],
    metrics: dict[str, float],
    prefix: str = "",
) -> None:
    ignored = {"acceptance_criteria", "criteria", "thresholds", "checkpoints"}
    for key, value in payload.items():
        if key in ignored:
            continue
        metric_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            metrics[metric_key] = float(value)
        elif isinstance(value, dict):
            _collect_numeric_metrics(value, metrics, metric_key)


def _extract_acceptance_criteria(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("acceptance_criteria", "criteria", "thresholds"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _evaluate_acceptance(metrics: dict[str, float], criteria: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []
    for key, rule in criteria.items():
        if key not in metrics:
            checks.append({"metric": key, "status": "missing", "rule": rule})
            failures.append(f"Missing required metric: {key}")
            continue
        value = metrics[key]
        status = "passed"
        if isinstance(rule, int | float):
            passed = value <= float(rule)
            details = {"max": float(rule)}
        elif isinstance(rule, dict):
            details = rule
            passed = True
            if "max" in rule and value > float(rule["max"]):
                passed = False
            if "min" in rule and value < float(rule["min"]):
                passed = False
        else:
            checks.append({"metric": key, "status": "unsupported_rule", "value": value})
            continue
        if not passed:
            status = "failed"
            failures.append(f"{key}={value} violates {details}")
        checks.append({"metric": key, "status": status, "value": value, "rule": details})
    return {"checks": checks, "failures": failures}


def _compare_metrics(
    payload: dict[str, Any],
    checkpoint_a: Path,
    checkpoint_b: Path,
) -> dict[str, Any]:
    checkpoints = payload.get("checkpoints") if isinstance(payload.get("checkpoints"), dict) else {}
    entry_a = _find_checkpoint_metrics(checkpoints, checkpoint_a, ("a", "checkpoint_a"))
    entry_b = _find_checkpoint_metrics(checkpoints, checkpoint_b, ("b", "checkpoint_b"))
    metrics_a = _extract_metrics(entry_a) if entry_a else {}
    metrics_b = _extract_metrics(entry_b) if entry_b else {}
    primary = payload.get("primary_metric")
    delta: dict[str, float] = {}
    for key in sorted(set(metrics_a) & set(metrics_b)):
        delta[key] = metrics_b[key] - metrics_a[key]
    best = None
    if isinstance(primary, str) and primary in metrics_a and primary in metrics_b:
        best = "checkpoint_a" if metrics_a[primary] <= metrics_b[primary] else "checkpoint_b"
    return {
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "delta_b_minus_a": delta,
        "primary_metric": primary if isinstance(primary, str) else None,
        "lower_is_better_best": best,
    }


def _checkpoint_benchmark_report_markdown(
    *,
    title: str,
    metrics_path: Path,
    metrics_sha256: str,
    metrics: dict[str, float],
    criteria: dict[str, Any],
    acceptance: dict[str, Any],
    checkpoint_evidence: dict[str, Any] | None,
    dataset_evidence: dict[str, Any] | None,
    plot_paths: list[Path],
    source_payload: dict[str, Any],
    warnings: list[str],
    errors: list[str],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        f"- Source metrics: `{metrics_path}`",
        f"- Source metrics sha256: `{metrics_sha256}`",
        "",
        "This report summarizes existing benchmark artifacts only. It does not declare the checkpoint production-ready.",
        "",
    ]
    if checkpoint_evidence:
        lines.extend(["## Checkpoint", "", *_evidence_lines(checkpoint_evidence), ""])
    if dataset_evidence:
        lines.extend(["## Dataset", "", *_evidence_lines(dataset_evidence), ""])
    if plot_paths:
        lines.extend(["## Plots", ""])
        for path in plot_paths:
            lines.append(f"- `{path}`")
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
                lines.append(f"  ![]({path.as_posix()})")
        lines.append("")

    lines.extend(["## Metrics", ""])
    if metrics:
        rows = [[name, _format_metric(value)] for name, value in sorted(metrics.items())]
        lines.extend(_markdown_table(["Metric", "Value"], rows))
    else:
        lines.append("No numeric benchmark metrics were found.")
    lines.append("")

    lines.extend(["## Acceptance Checks", ""])
    checks = acceptance.get("checks") if isinstance(acceptance.get("checks"), list) else []
    if checks:
        rows = [
            [
                str(check.get("metric") or ""),
                str(check.get("status") or ""),
                _format_metric(check.get("value")),
                json.dumps(check.get("rule"), ensure_ascii=False, sort_keys=True),
            ]
            for check in checks
            if isinstance(check, dict)
        ]
        lines.extend(_markdown_table(["Metric", "Status", "Value", "Rule"], rows))
    elif criteria:
        lines.append("Acceptance criteria were present, but no checks could be evaluated.")
    else:
        lines.append("No acceptance criteria were supplied.")
    failures = acceptance.get("failures") if isinstance(acceptance.get("failures"), list) else []
    if failures:
        lines.extend(["", "Failures:"])
        lines.extend(f"- {item}" for item in failures)
    lines.append("")

    command = source_payload.get("command")
    if isinstance(command, list):
        lines.extend(["## Command", "", "```text", " ".join(str(item) for item in command), "```", ""])
    if warnings:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
        lines.append("")
    if errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in errors)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _evidence_lines(evidence: dict[str, Any]) -> list[str]:
    keys = ("path", "kind", "sha256", "size_bytes", "file_count", "sampled_file_count")
    return [f"- {key}: `{evidence[key]}`" for key in keys if evidence.get(key) is not None]


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    normalized_rows = [[_escape_table_cell(cell) for cell in row] for row in rows]
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in normalized_rows),
    ]


def _escape_table_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.12g}"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return ""
    return str(value)


def _find_checkpoint_metrics(
    checkpoints: dict[str, Any],
    checkpoint: Path,
    aliases: tuple[str, ...],
) -> dict[str, Any] | None:
    for alias in aliases:
        value = checkpoints.get(alias)
        if isinstance(value, dict):
            return value
    checkpoint_text = str(checkpoint)
    for value in checkpoints.values():
        if not isinstance(value, dict):
            continue
        path = value.get("path")
        if isinstance(path, str) and str(_resolve(path)) == checkpoint_text:
            return value
    return None
