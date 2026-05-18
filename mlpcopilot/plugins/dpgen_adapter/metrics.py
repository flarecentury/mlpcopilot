"""DP-GEN artifact and log metric extraction helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
def _read_last_table_row(path: Path) -> tuple[list[str], list[str]]:
    header: list[str] = []
    last: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return header, last
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            candidate = stripped.lstrip("#").strip().split()
            if candidate and any(name.lower() == "step" for name in candidate):
                header = candidate
            continue
        last = stripped.split()
    return header, last
def _table_last_metrics(path: Path, fallback_header: list[str]) -> dict[str, Any]:
    header, values = _read_last_table_row(path)
    if not values:
        return {}
    names = header if len(header) == len(values) else fallback_header
    metrics: dict[str, Any] = {}
    for index, value in enumerate(values[: len(names)]):
        number = _to_float(value)
        if number is None:
            continue
        name = names[index]
        if name == "step":
            metrics[name] = int(number)
        else:
            metrics[name] = number
    return metrics
def _lcurve_metrics(path: Path) -> dict[str, Any]:
    return _table_last_metrics(
        path,
        ["step", "rmse_trn", "rmse_e_trn", "rmse_f_trn", "rmse_v_trn", "lr"],
    )
def _model_devi_metrics(path: Path) -> dict[str, Any]:
    metrics = _table_last_metrics(
        path,
        ["step", "max_devi_v", "min_devi_v", "avg_devi_v", "max_devi_f", "min_devi_f", "avg_devi_f"],
    )
    max_devi_f: float | None = None
    max_devi_v: float | None = None
    rows = 0
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return metrics
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 5:
            continue
        rows += 1
        devi_v = _to_float(parts[1])
        devi_f = _to_float(parts[4])
        if devi_v is not None:
            max_devi_v = devi_v if max_devi_v is None else max(max_devi_v, devi_v)
        if devi_f is not None:
            max_devi_f = devi_f if max_devi_f is None else max(max_devi_f, devi_f)
    metrics["frames"] = rows
    if max_devi_v is not None:
        metrics["max_seen_devi_v"] = max_devi_v
    if max_devi_f is not None:
        metrics["max_seen_devi_f"] = max_devi_f
    return metrics
def _count_nonempty_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0
def _selection_metrics(path: Path) -> dict[str, Any]:
    name = path.name
    metrics: dict[str, Any] = {"frames": _count_nonempty_lines(path)}
    match = re.search(r"\.(\d+)\.out$", name)
    if match:
        metrics["system"] = int(match.group(1))
    if name.startswith("candidate"):
        metrics["selection"] = "candidate"
    elif name.startswith("rest_accurate"):
        metrics["selection"] = "accurate"
    elif name.startswith("rest_failed"):
        metrics["selection"] = "failed"
    return metrics
def _dataset_metrics(path: Path) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    energy = path / "energy.raw"
    coord = path / "coord.raw"
    if energy.exists():
        metrics["frames"] = _count_nonempty_lines(energy)
    elif coord.exists():
        metrics["frames"] = _count_nonempty_lines(coord)
    metrics["raw_files"] = len(list(path.glob("*.raw"))) if path.is_dir() else 0
    metrics["npy_sets"] = len(list(path.glob("set.*"))) if path.is_dir() else 0
    return metrics
def _stage_metrics(kind: str, path: Path) -> dict[str, Any]:
    if kind == "training_stage":
        return {
            "models": len([item for item in path.glob("[0-9][0-9][0-9]") if item.is_dir()]),
            "curves": len(list(path.glob("*/lcurve.out"))),
            "logs": len(list(path.glob("*/train.log"))),
            "model_outputs": len(list(path.glob("*/frozen_model.*"))) + len(list(path.glob("graph.*"))),
        }
    if kind == "model_deviation_stage":
        return {
            "tasks": len([item for item in path.glob("task.*") if item.is_dir()]),
            "outputs": len(list(path.glob("task.*/model_devi.out"))),
            "logs": len(list(path.glob("task.*/model_devi.log"))),
            "job_specs": len(list(path.glob("task.*/job.json"))),
            "confs": len(list((path / "confs").glob("*"))) if (path / "confs").exists() else 0,
        }
    if kind == "fp_stage":
        selection = {"candidate": 0, "accurate": 0, "failed": 0}
        for item in path.glob("candidate*.out"):
            selection["candidate"] += _count_nonempty_lines(item)
        for item in path.glob("rest_accurate*.out"):
            selection["accurate"] += _count_nonempty_lines(item)
        for item in path.glob("rest_failed*.out"):
            selection["failed"] += _count_nonempty_lines(item)
        return {
            "tasks": len([item for item in path.glob("task.*") if item.is_dir()]),
            "datasets": len([item for item in path.glob("data.*") if item.is_dir()]),
            "outputs": len(list(path.glob("task.*/output"))) + len(list(path.glob("task.*/OUTCAR"))),
            "job_specs": len(list(path.glob("task.*/job.json"))),
            "selection_reports": len(list(path.glob("candidate*.out")))
            + len(list(path.glob("rest_accurate*.out")))
            + len(list(path.glob("rest_failed*.out"))),
            **selection,
        }
    return {}
def _artifact_metrics(kind: str, path: Path) -> dict[str, Any]:
    if kind == "training_curve":
        return _lcurve_metrics(path)
    if kind == "model_deviation_output":
        return _model_devi_metrics(path)
    if kind == "fp_selection_report":
        return _selection_metrics(path)
    if kind == "label_dataset":
        return _dataset_metrics(path)
    if kind.endswith("_log") or kind == "log":
        return _log_metrics(path)
    return {}
def _root_log_kind(path: Path) -> str:
    name = path.name.lower()
    if "dpdispatcher" in name:
        return "dispatcher_log"
    if "dpgen" in name and "error" in name:
        return "error_log"
    if name == "error.log" or name.endswith("_error.log"):
        return "error_log"
    if "cp2kdata" in name or "recover" in name:
        return "recover_log"
    if "dpgen" in name:
        return "dpgen_log"
    return "log"
def _log_metrics(path: Path) -> dict[str, Any]:
    metrics = {
        "lines": 0,
        "errors": 0,
        "warnings": 0,
        "keyboard_interrupt": False,
        "traceback": False,
    }
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                metrics["lines"] += 1
                lowered = line.lower()
                if "error" in lowered or "traceback" in lowered:
                    metrics["errors"] += 1
                if "warning" in lowered:
                    metrics["warnings"] += 1
                if "keyboardinterrupt" in lowered:
                    metrics["keyboard_interrupt"] = True
                if "traceback" in lowered:
                    metrics["traceback"] = True
    except OSError:
        return {}
    return metrics
def _backend_log_summary(backend_workdir: Path) -> dict[str, Any]:
    progress: dict[str, Any] = {}
    selection_by_system: dict[str, dict[str, int]] = {}
    dispatcher = {"submitted": 0, "finished": 0, "recovered": 0, "errors": 0}
    error_flags = {"keyboard_interrupt": False, "traceback": False, "cp2kdata_warning": False}

    dpgen_logs = sorted(path for path in backend_workdir.glob("*.log") if _root_log_kind(path) == "dpgen_log")
    for path in dpgen_logs:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            task_match = re.search(r"iter\.(\d{6}).*task\s+(\d{2})", line)
            if task_match:
                progress = {"iteration": int(task_match.group(1)), "task": int(task_match.group(2))}
                if int(task_match.group(2)) == 6:
                    selection_by_system = {}
            selection_match = re.search(r"system\s+(\d+)\s+(candidate|failed|accurate)\s+:\s+(\d+)", line)
            if selection_match:
                system = selection_match.group(1)
                kind = selection_match.group(2)
                selection_by_system.setdefault(system, {})[kind] = int(selection_match.group(3))

    for path in backend_workdir.glob("*.log"):
        kind = _root_log_kind(path)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            lowered = line.lower()
            if kind == "dispatcher_log":
                if " submit" in lowered:
                    dispatcher["submitted"] += 1
                if " finished" in lowered:
                    dispatcher["finished"] += 1
                if "recover submission" in lowered:
                    dispatcher["recovered"] += 1
                if "error" in lowered or "traceback" in lowered:
                    dispatcher["errors"] += 1
            if "keyboardinterrupt" in lowered:
                error_flags["keyboard_interrupt"] = True
            if "traceback" in lowered:
                error_flags["traceback"] = True
            if "cp2kdata" in lowered or "virial parsing" in lowered:
                error_flags["cp2kdata_warning"] = True

    selection_totals = {"candidate": 0, "failed": 0, "accurate": 0}
    for item in selection_by_system.values():
        for key in selection_totals:
            selection_totals[key] += item.get(key, 0)
    return {
        "progress": progress,
        "selection": selection_totals,
        "dispatcher": dispatcher,
        "errors": error_flags,
    }
