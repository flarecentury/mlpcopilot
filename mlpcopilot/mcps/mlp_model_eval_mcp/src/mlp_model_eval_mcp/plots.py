"""Benchmark plot artifacts for MLP checkpoint evaluation."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import artifact, load_json_or_yaml

ENERGY_REF_KEYS = (
    "energy_reference",
    "energy_true",
    "reference_energy",
    "reference_energies",
    "dft_energy",
    "dft_energies",
    "training_energies",
    "data_e",
)
ENERGY_PRED_KEYS = (
    "energy_prediction",
    "energy_pred",
    "predicted_energy",
    "predicted_energies",
    "mlp_energy",
    "mlp_energies",
    "pred_e",
)
FORCE_REF_KEYS = (
    "force_reference",
    "forces_reference",
    "force_true",
    "forces_true",
    "reference_forces",
    "dft_forces",
    "training_forces",
    "data_f",
)
FORCE_PRED_KEYS = (
    "force_prediction",
    "forces_prediction",
    "force_pred",
    "forces_pred",
    "predicted_forces",
    "mlp_forces",
    "pred_f",
)


def build_benchmark_plot_artifacts(
    *,
    metrics_path: Path,
    output_dir: Path | None = None,
    detail_prefix: Path | None = None,
    energy_detail_path: Path | None = None,
    force_detail_path: Path | None = None,
    max_points: int = 10000,
) -> dict[str, Any]:
    """Create parity and error-distribution PNG plots from existing benchmark data."""
    if max_points <= 0:
        return _failed("max_points must be positive.")
    if not metrics_path.is_file():
        return _failed(f"No such metrics artifact: {metrics_path}")
    try:
        payload = load_json_or_yaml(metrics_path)
    except Exception as exc:
        return _failed(f"{type(exc).__name__}: {exc}")
    if not isinstance(payload, dict):
        return _failed("Metrics artifact must be a JSON/YAML object.")

    run_dir = output_dir or metrics_path.parent / "plots"
    run_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    errors: list[str] = []
    plot_paths: list[Path] = []
    metrics: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_metrics_path": str(metrics_path),
    }

    energy_ref, energy_pred = _energy_pair(payload, metrics_path.parent, detail_prefix, energy_detail_path)
    force_ref, force_pred = _force_pair(payload, metrics_path.parent, detail_prefix, force_detail_path)

    if energy_ref is not None and energy_pred is not None:
        try:
            result = _plot_energy(energy_ref, energy_pred, run_dir=run_dir, max_points=max_points)
            plot_paths.extend(result.pop("plot_paths"))
            metrics.update(result)
        except Exception as exc:
            errors.append(f"Failed to plot energy data: {type(exc).__name__}: {exc}")
    else:
        warnings.append("No energy reference/prediction pair was found.")

    if force_ref is not None and force_pred is not None:
        try:
            result = _plot_forces(force_ref, force_pred, run_dir=run_dir, max_points=max_points)
            plot_paths.extend(result.pop("plot_paths"))
            metrics.update(result)
        except Exception as exc:
            errors.append(f"Failed to plot force data: {type(exc).__name__}: {exc}")
    else:
        warnings.append("No force reference/prediction pair was found.")

    if not plot_paths:
        errors.append("No benchmark plots were generated.")
    metrics["plot_paths"] = [str(path) for path in plot_paths]
    metrics["plot_count"] = len(plot_paths)
    artifacts = [artifact(path, "plot") for path in plot_paths]
    return {
        "status": "failed" if errors else "success",
        "summary": f"Wrote {len(plot_paths)} benchmark plot artifact(s)."
        if plot_paths
        else "No benchmark plots were generated.",
        "metrics": metrics,
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": errors,
    }


def _energy_pair(
    payload: dict[str, Any],
    base_dir: Path,
    detail_prefix: Path | None,
    energy_detail_path: Path | None,
) -> tuple[Any | None, Any | None]:
    explicit = _pair_from_payload(payload, ENERGY_REF_KEYS, ENERGY_PRED_KEYS)
    if explicit != (None, None):
        return explicit
    detail = energy_detail_path or _detail_path(payload, base_dir, detail_prefix, ".e.out")
    if detail and detail.is_file():
        return _parse_detail_pair(detail)
    return None, None


def _force_pair(
    payload: dict[str, Any],
    base_dir: Path,
    detail_prefix: Path | None,
    force_detail_path: Path | None,
) -> tuple[Any | None, Any | None]:
    explicit = _pair_from_payload(payload, FORCE_REF_KEYS, FORCE_PRED_KEYS)
    if explicit != (None, None):
        return explicit
    detail = force_detail_path or _detail_path(payload, base_dir, detail_prefix, ".f.out")
    if detail and detail.is_file():
        return _parse_detail_pair(detail)
    return None, None


def _pair_from_payload(
    payload: dict[str, Any],
    reference_keys: tuple[str, ...],
    prediction_keys: tuple[str, ...],
) -> tuple[Any | None, Any | None]:
    reference = _find_value(payload, reference_keys)
    prediction = _find_value(payload, prediction_keys)
    return reference, prediction


def _find_value(value: Any, keys: tuple[str, ...]) -> Any | None:
    if isinstance(value, dict):
        for key in keys:
            if key in value:
                return value[key]
        for child in value.values():
            found = _find_value(child, keys)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found is not None:
                return found
    return None


def _detail_path(
    payload: dict[str, Any],
    base_dir: Path,
    explicit_prefix: Path | None,
    suffix: str,
) -> Path | None:
    prefix: Path | None = explicit_prefix
    if prefix is None and isinstance(payload.get("detail_prefix"), str):
        raw = Path(str(payload["detail_prefix"])).expanduser()
        prefix = raw if raw.is_absolute() else base_dir / raw
    if prefix is None:
        return None
    return prefix.with_suffix(suffix)


def _parse_detail_pair(path: Path) -> tuple[list[Any], list[Any]]:
    headers: list[str] | None = None
    rows: list[list[float]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            line = line.lstrip("#").strip()
            if not line:
                continue
        tokens = line.split()
        try:
            rows.append([float(token) for token in tokens])
        except ValueError:
            headers = tokens
    if not rows:
        return [], []
    width = min(len(row) for row in rows)
    values = [row[:width] for row in rows if len(row) >= width]
    if headers and len(headers) >= width:
        ref_idx = [
            index
            for index, token in enumerate(headers[:width])
            if _is_reference_header(token)
        ]
        pred_idx = [
            index
            for index, token in enumerate(headers[:width])
            if _is_prediction_header(token)
        ]
        if ref_idx and len(ref_idx) == len(pred_idx):
            return _select_columns(values, ref_idx), _select_columns(values, pred_idx)
    if width == 2:
        return [row[0] for row in values], [row[1] for row in values]
    if width >= 6 and width % 2 == 0:
        half = width // 2
        return [row[:half] for row in values], [row[half:width] for row in values]
    return [], []


def _is_reference_header(token: str) -> bool:
    lowered = token.lower()
    return lowered.startswith(("data", "dft", "ref", "true"))


def _is_prediction_header(token: str) -> bool:
    lowered = token.lower()
    return lowered.startswith(("pred", "mlp"))


def _select_columns(rows: list[list[float]], indices: list[int]) -> list[Any]:
    if len(indices) == 1:
        index = indices[0]
        return [row[index] for row in rows]
    return [[row[index] for index in indices] for row in rows]


def _plot_energy(reference: Any, prediction: Any, *, run_dir: Path, max_points: int) -> dict[str, Any]:
    import numpy as np

    ref = np.asarray(reference, dtype=float).reshape(-1)
    pred = np.asarray(prediction, dtype=float).reshape(-1)
    ref, pred = _matched_arrays(ref, pred)
    errors = pred - ref
    parity_path = run_dir / "energy_parity.png"
    hist_path = run_dir / "energy_error_histogram.png"
    _parity_plot(
        ref,
        pred,
        parity_path,
        title="Energy Parity",
        xlabel="Reference energy",
        ylabel="Predicted energy",
        max_points=max_points,
    )
    _histogram_plot(
        errors,
        hist_path,
        title="Energy Error Distribution",
        xlabel="Predicted - reference energy",
    )
    return {
        "energy_point_count": int(ref.size),
        "energy_mae_from_points": _mae(errors),
        "energy_rmse_from_points": _rmse(errors),
        "energy_r2_from_points": _r2(ref, pred),
        "plot_paths": [parity_path, hist_path],
    }


def _plot_forces(reference: Any, prediction: Any, *, run_dir: Path, max_points: int) -> dict[str, Any]:
    import numpy as np

    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(prediction, dtype=float)
    ref, pred = _matched_arrays(ref, pred)
    ref_components = ref.reshape(-1, 3) if ref.size % 3 == 0 else ref.reshape(-1, 1)
    pred_components = pred.reshape(-1, ref_components.shape[1])
    ref_flat = ref_components.reshape(-1)
    pred_flat = pred_components.reshape(-1)
    errors = pred_flat - ref_flat
    parity_path = run_dir / "force_parity.png"
    hist_path = run_dir / "force_error_histogram.png"
    component_path = run_dir / "force_components.png"
    _parity_plot(
        ref_flat,
        pred_flat,
        parity_path,
        title="Force Parity",
        xlabel="Reference force",
        ylabel="Predicted force",
        max_points=max_points,
    )
    _histogram_plot(
        errors,
        hist_path,
        title="Force Error Distribution",
        xlabel="Predicted - reference force",
    )
    plot_paths = [parity_path, hist_path]
    if ref_components.shape[1] == 3:
        _component_plot(ref_components, pred_components, component_path, max_points=max_points)
        plot_paths.append(component_path)
    return {
        "force_component_count": int(ref_flat.size),
        "force_mae_from_points": _mae(errors),
        "force_rmse_from_points": _rmse(errors),
        "force_r2_from_points": _r2(ref_flat, pred_flat),
        "plot_paths": plot_paths,
    }


def _matched_arrays(reference: Any, prediction: Any) -> tuple[Any, Any]:
    import numpy as np

    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(prediction, dtype=float)
    count = min(ref.size, pred.size)
    if count == 0:
        raise ValueError("reference and prediction arrays must not be empty")
    return ref.reshape(-1)[:count], pred.reshape(-1)[:count]


def _parity_plot(
    reference: Any,
    prediction: Any,
    path: Path,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    max_points: int,
) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    ref, pred = _sample(reference, prediction, max_points=max_points)
    fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
    ax.scatter(ref, pred, s=10, alpha=0.55)
    lower = float(min(np.min(ref), np.min(pred)))
    upper = float(max(np.max(ref), np.max(pred)))
    if math.isclose(lower, upper):
        lower -= 1.0
        upper += 1.0
    ax.plot([lower, upper], [lower, upper], "k--", linewidth=1)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _histogram_plot(values: Any, path: Path, *, title: str, xlabel: str) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    values = np.asarray(values, dtype=float).reshape(-1)
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    ax.hist(values, bins=min(50, max(10, int(math.sqrt(values.size)))), alpha=0.8)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Count")
    ax.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _component_plot(reference: Any, prediction: Any, path: Path, *, max_points: int) -> None:
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np

    ref = np.asarray(reference, dtype=float).reshape(-1, 3)
    pred = np.asarray(prediction, dtype=float).reshape(-1, 3)
    fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
    for index, label in enumerate(("Fx", "Fy", "Fz")):
        x, y = _sample(ref[:, index], pred[:, index], max_points=max_points)
        ax.scatter(x, y, s=10, alpha=0.45, label=label)
    lower = float(min(np.min(ref), np.min(pred)))
    upper = float(max(np.max(ref), np.max(pred)))
    if math.isclose(lower, upper):
        lower -= 1.0
        upper += 1.0
    ax.plot([lower, upper], [lower, upper], "k--", linewidth=1)
    ax.set_title("Force Components")
    ax.set_xlabel("Reference force")
    ax.set_ylabel("Predicted force")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.35)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _sample(reference: Any, prediction: Any, *, max_points: int) -> tuple[Any, Any]:
    import numpy as np

    ref = np.asarray(reference, dtype=float).reshape(-1)
    pred = np.asarray(prediction, dtype=float).reshape(-1)
    ref, pred = _matched_arrays(ref, pred)
    if ref.size <= max_points:
        return ref, pred
    indices = np.linspace(0, ref.size - 1, num=max_points, dtype=int)
    return ref[indices], pred[indices]


def _mae(errors: Any) -> float:
    import numpy as np

    values = np.asarray(errors, dtype=float)
    return float(np.mean(np.abs(values)))


def _rmse(errors: Any) -> float:
    import numpy as np

    values = np.asarray(errors, dtype=float)
    return float(np.sqrt(np.mean(values * values)))


def _r2(reference: Any, prediction: Any) -> float:
    import numpy as np

    ref = np.asarray(reference, dtype=float)
    pred = np.asarray(prediction, dtype=float)
    ss_tot = float(np.sum((ref - np.mean(ref)) ** 2))
    ss_res = float(np.sum((ref - pred) ** 2))
    return 0.0 if ss_tot <= 0 else 1.0 - ss_res / ss_tot


def _failed(message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "summary": message,
        "metrics": {},
        "artifacts": [],
        "warnings": [],
        "errors": [message],
    }
