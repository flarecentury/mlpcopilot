"""record.dpgen parsing and stage progression helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DPGEN_TASKS: dict[int, tuple[str, str, str]] = {
    0: ("make_train", "train.prepare", "00.train"),
    1: ("run_train", "train.run", "00.train"),
    2: ("post_train", "train.collect", "00.train"),
    3: ("make_model_devi", "explore.prepare", "01.model_devi"),
    4: ("run_model_devi", "explore.run", "01.model_devi"),
    5: ("post_model_devi", "explore.collect", "01.model_devi"),
    6: ("make_fp", "label.prepare", "02.fp"),
    7: ("run_fp", "label.run", "02.fp"),
    8: ("post_fp", "label.collect", "02.fp"),
}


def _iteration_id(index: int) -> str:
    return f"iter_{index:06d}"
def _dpgen_iter_name(index: int) -> str:
    return f"iter.{index:06d}"
def _read_record(record_path: Path) -> tuple[list[dict[str, int]], list[str]]:
    records: list[dict[str, int]] = []
    warnings: list[str] = []
    if not record_path.exists():
        return records, [f"record file not found: {record_path}"]
    try:
        lines = record_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return records, [f"failed to read record file: {exc}"]
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) < 2:
            warnings.append(f"invalid record.dpgen line {line_no}: {stripped}")
            continue
        try:
            iter_index = int(parts[0])
            task_index = int(parts[1])
        except ValueError:
            warnings.append(f"invalid record.dpgen line {line_no}: {stripped}")
            continue
        records.append({"iter_index": iter_index, "task_index": task_index})
    return records, warnings
def _last_completed(records: list[dict[str, int]]) -> dict[str, Any] | None:
    if not records:
        return None
    item = records[-1]
    task_name, phase, stage_dir = DPGEN_TASKS.get(item["task_index"], ("unknown", "unknown", ""))
    return {
        "iteration_id": _iteration_id(item["iter_index"]),
        "backend_iteration": _dpgen_iter_name(item["iter_index"]),
        "iter_index": item["iter_index"],
        "task_index": item["task_index"],
        "task_name": task_name,
        "phase": phase,
        "stage_dir": stage_dir,
    }
def _next_expected(last: dict[str, Any] | None) -> dict[str, Any] | None:
    if last is None:
        task_name, phase, stage_dir = DPGEN_TASKS[0]
        return {
            "iteration_id": _iteration_id(0),
            "backend_iteration": _dpgen_iter_name(0),
            "iter_index": 0,
            "task_index": 0,
            "task_name": task_name,
            "phase": phase,
            "stage_dir": stage_dir,
        }
    next_iter = int(last["iter_index"])
    next_task = int(last["task_index"]) + 1
    if next_task > 8:
        next_iter += 1
        next_task = 0
    task_name, phase, stage_dir = DPGEN_TASKS[next_task]
    return {
        "iteration_id": _iteration_id(next_iter),
        "backend_iteration": _dpgen_iter_name(next_iter),
        "iter_index": next_iter,
        "task_index": next_task,
        "task_name": task_name,
        "phase": phase,
        "stage_dir": stage_dir,
    }
