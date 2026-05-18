"""DeePMD-kit v3 ``dp test`` execution helpers."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import artifact, sha256_file

DEEPMD_V3_MODEL_FORMATS: dict[str, dict[str, Any]] = {
    ".pb": {"format": "tensorflow_frozen_model", "backend_hint": "tensorflow"},
    ".pth": {"format": "pytorch_checkpoint", "backend_hint": "pytorch"},
    ".pt": {"format": "pytorch_or_pytorch_exportable_checkpoint", "backend_hint": "auto"},
    ".pte": {"format": "pytorch_exportable_model", "backend_hint": "pytorch-exportable"},
    ".pt2": {"format": "pytorch_exportable_model", "backend_hint": "pytorch-exportable"},
    ".json": {"format": "paddle_model_or_metrics", "backend_hint": "paddle"},
    ".pd": {"format": "paddle_model", "backend_hint": "paddle"},
    ".hlo": {"format": "jax_model", "backend_hint": "jax"},
    ".jax": {"format": "jax_model", "backend_hint": "jax"},
    ".savedmodel": {"format": "jax_savedmodel", "backend_hint": "jax"},
    ".dp": {"format": "dpmodel_model", "backend_hint": "dpmodel"},
    ".yaml": {"format": "dpmodel_model_or_config", "backend_hint": "dpmodel"},
    ".yml": {"format": "dpmodel_model_or_config", "backend_hint": "dpmodel"},
}

DETAIL_SUFFIXES = (".e.out", ".f.out", ".v.out", ".ae.out", ".h.out")

_METRIC_LINE_RE = re.compile(
    r"^\s*(?P<label>[A-Za-z][A-Za-z0-9/ _-]*?)\s*:\s*"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?:\s*(?P<unit>\S.*?))?\s*$"
)

_LABEL_TO_KEY = {
    "Energy MAE": "energy_mae",
    "Energy RMSE": "energy_rmse",
    "Energy MAE/Natoms": "energy_mae_per_atom",
    "Energy RMSE/Natoms": "energy_rmse_per_atom",
    "Force MAE": "force_mae",
    "Force RMSE": "force_rmse",
    "Force weighted MAE": "force_weighted_mae",
    "Force weighted RMSE": "force_weighted_rmse",
    "Force atom MAE": "force_atom_mae",
    "Force atom RMSE": "force_atom_rmse",
    "Force spin MAE": "force_spin_mae",
    "Force spin RMSE": "force_spin_rmse",
    "Virial MAE": "virial_mae",
    "Virial RMSE": "virial_rmse",
    "Virial MAE/Natoms": "virial_mae_per_atom",
    "Virial RMSE/Natoms": "virial_rmse_per_atom",
    "Atomic ener MAE": "atomic_energy_mae",
    "Atomic ener RMSE": "atomic_energy_rmse",
    "Hessian MAE": "hessian_mae",
    "Hessian RMSE": "hessian_rmse",
}


def deepmd_v3_model_format(path: Path) -> dict[str, Any]:
    """Return a DeePMD-kit v3 model format hint from suffix."""
    suffix = _deepmd_suffix(path)
    data = DEEPMD_V3_MODEL_FORMATS.get(suffix)
    if data:
        return {"suffix": suffix, **data}
    if path.name.lower() == "saved_model.pb":
        return {
            "suffix": ".pb",
            "format": "tensorflow_saved_model_marker",
            "backend_hint": "tensorflow",
        }
    return {"suffix": suffix or None, "format": "unknown", "backend_hint": "auto"}


def run_deepmd_test_command(
    *,
    checkpoint_path: Path,
    dataset_path: Path,
    data_source: str = "system",
    dp_command: str = "dp",
    backend: str | None = None,
    numb_test: int = 0,
    rand_seed: int | None = None,
    shuffle_test: bool = False,
    atomic: bool = False,
    head: str | None = None,
    output_dir: Path | None = None,
    timeout_seconds: int = 60,
    detail_prefix: str | None = None,
) -> dict[str, Any]:
    """Execute DeePMD-kit v3 ``dp test`` and return normalized evidence."""
    if not checkpoint_path.exists():
        return {
            "status": "failed",
            "summary": "Checkpoint path does not exist.",
            "errors": [f"No such checkpoint path: {checkpoint_path}"],
        }
    if not dataset_path.exists():
        return {
            "status": "failed",
            "summary": "Dataset path does not exist.",
            "errors": [f"No such dataset path: {dataset_path}"],
        }
    if data_source not in {"system", "datafile", "train-data", "valid-data"}:
        return {
            "status": "failed",
            "summary": "Unsupported dp test data source.",
            "errors": [f"Unsupported data_source: {data_source}"],
        }
    if timeout_seconds <= 0:
        return {
            "status": "failed",
            "summary": "Invalid timeout.",
            "errors": ["timeout_seconds must be positive."],
        }

    run_dir = output_dir or _default_output_dir(checkpoint_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    detail_path = run_dir / (detail_prefix or "dp_test_detail")
    log_path = run_dir / "dp_test.log"
    metrics_path = run_dir / "dp_test_metrics.json"
    command = _build_dp_test_command(
        checkpoint_path=checkpoint_path,
        dataset_path=dataset_path,
        data_source=data_source,
        dp_command=dp_command,
        backend=backend,
        numb_test=numb_test,
        rand_seed=rand_seed,
        shuffle_test=shuffle_test,
        atomic=atomic,
        head=head,
        detail_path=detail_path,
    )

    started_at = datetime.now(UTC)
    errors: list[str] = []
    warnings: list[str] = []
    timed_out = False
    returncode: int | None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command,
            cwd=str(run_dir),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        if returncode != 0:
            errors.append(f"dp test exited with status {returncode}.")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = _decode_process_text(exc.stdout)
        stderr = _decode_process_text(exc.stderr)
        errors.append(f"dp test timed out after {timeout_seconds} seconds.")
    except OSError as exc:
        returncode = None
        errors.append(f"{type(exc).__name__}: {exc}")

    combined_output = "\n".join(part for part in (stdout, stderr) if part)
    metrics, units = parse_dp_test_metrics(combined_output)
    _write_log(
        log_path=log_path,
        command=command,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        timeout_seconds=timeout_seconds,
        timed_out=timed_out,
    )
    detail_artifacts = _collect_detail_artifacts(detail_path)
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": started_at.isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": sha256_file(checkpoint_path) if checkpoint_path.is_file() else None,
        "dataset_path": str(dataset_path),
        "data_source": data_source,
        "deepmd_command": command,
        "deepmd_reference": "DeepMD-kit v3 dp test",
        "model_format": deepmd_v3_model_format(checkpoint_path),
        "returncode": returncode,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "inference_executed": returncode == 0 and not timed_out,
        "metrics": metrics,
        "metric_units": units,
        "detail_prefix": str(detail_path),
        "log_path": str(log_path),
    }
    metrics_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    artifacts = [
        artifact(log_path, "log"),
        artifact(metrics_path, "metrics"),
        *detail_artifacts,
    ]
    if returncode == 0 and not metrics:
        warnings.append("dp test finished, but no known metric lines were parsed from output.")
    if errors:
        status = "failed"
        summary = "DeepMD-kit dp test failed."
    elif not metrics:
        status = "blocked"
        summary = "DeepMD-kit dp test completed without parseable benchmark metrics."
    else:
        status = "success"
        summary = "DeepMD-kit dp test completed and metrics were parsed."
    return {
        "status": status,
        "summary": summary,
        "metrics": payload,
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": errors,
    }


def parse_dp_test_metrics(output: str) -> tuple[dict[str, float], dict[str, str]]:
    """Parse metric lines emitted by DeePMD-kit v3 ``dp test``."""
    metrics: dict[str, float] = {}
    units: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        match = _METRIC_LINE_RE.match(line)
        if not match:
            continue
        label = _normalize_metric_label(match.group("label"))
        key = _LABEL_TO_KEY.get(label)
        if not key:
            continue
        metrics[key] = float(match.group("value"))
        unit = (match.group("unit") or "").strip()
        if unit:
            units[key] = unit
    return metrics, units


def _build_dp_test_command(
    *,
    checkpoint_path: Path,
    dataset_path: Path,
    data_source: str,
    dp_command: str,
    backend: str | None,
    numb_test: int,
    rand_seed: int | None,
    shuffle_test: bool,
    atomic: bool,
    head: str | None,
    detail_path: Path,
) -> list[str]:
    command = shlex.split(dp_command)
    if not command:
        command = ["dp"]
    if backend:
        command.extend(["--backend", backend])
    command.extend(["test", "--model", str(checkpoint_path)])
    if data_source == "system":
        command.extend(["--system", str(dataset_path)])
    elif data_source == "datafile":
        command.extend(["--datafile", str(dataset_path)])
    elif data_source == "train-data":
        command.extend(["--train-data", str(dataset_path)])
    elif data_source == "valid-data":
        command.extend(["--valid-data", str(dataset_path)])
    command.extend(["--numb-test", str(numb_test)])
    if rand_seed is not None:
        command.extend(["--rand-seed", str(rand_seed)])
    if shuffle_test:
        command.append("--shuffle-test")
    command.extend(["--detail-file", str(detail_path)])
    if atomic:
        command.append("--atomic")
    if head:
        command.extend(["--head", head])
    return command


def _collect_detail_artifacts(detail_path: Path) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for suffix in DETAIL_SUFFIXES:
        path = detail_path.with_suffix(suffix)
        if path.is_file():
            artifacts.append(artifact(path, "metrics"))
    return artifacts


def _decode_process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _default_output_dir(checkpoint_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path.cwd().resolve() / "model_eval_artifacts" / f"{checkpoint_path.stem}-{stamp}"


def _deepmd_suffix(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".savedmodel"):
        return ".savedmodel"
    return path.suffix.lower()


def _normalize_metric_label(label: str) -> str:
    return " ".join(label.replace("  ", " ").split())


def _write_log(
    *,
    log_path: Path,
    command: list[str],
    stdout: str,
    stderr: str,
    returncode: int | None,
    timeout_seconds: int,
    timed_out: bool,
) -> None:
    log_payload = {
        "command": command,
        "returncode": returncode,
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
    }
    log_path.write_text(json.dumps(log_payload, indent=2, sort_keys=True), encoding="utf-8")
