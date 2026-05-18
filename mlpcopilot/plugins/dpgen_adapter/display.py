"""Display document builders for the DP-GEN adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import PRODUCER
from .io import _rel


def _artifact_display_iteration_id(
    artifacts: list[dict[str, Any]],
    *,
    focus_iteration_id: str | None = None,
    fallback_iteration_id: str | None = None,
) -> str:
    iteration_ids = {
        str(item.get("iteration_id"))
        for item in artifacts
        if item.get("iteration_id")
    }
    if focus_iteration_id and focus_iteration_id in iteration_ids:
        return focus_iteration_id
    if fallback_iteration_id and fallback_iteration_id in iteration_ids:
        return fallback_iteration_id
    if focus_iteration_id or fallback_iteration_id:
        return focus_iteration_id or fallback_iteration_id or ""
    return max(iteration_ids, default="")


def _artifact_display_rows(
    artifacts: list[dict[str, Any]],
    workspace: Path,
    *,
    display_iteration_id: str = "",
) -> list[dict[str, Any]]:
    operator_kinds = {
        "training_stage",
        "model_deviation_stage",
        "fp_stage",
        "dpgen_log",
        "dispatcher_log",
        "error_log",
        "recover_log",
    }
    priority = {
        "error_log": 0,
        "recover_log": 1,
        "dispatcher_log": 2,
        "dpgen_log": 3,
        "training_stage": 10,
        "model_deviation_stage": 20,
        "fp_stage": 30,
    }
    limits = {
        "dpgen_log": 1,
        "dispatcher_log": 1,
        "error_log": 1,
        "recover_log": 1,
    }
    latest_iteration = _artifact_display_iteration_id(artifacts)

    def _actionable_log(item: dict[str, Any]) -> bool:
        kind = str(item.get("kind") or "")
        if kind not in {"dpgen_log", "dispatcher_log", "error_log", "recover_log"}:
            return True
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        if kind == "error_log":
            return True
        return bool(
            metrics.get("errors")
            or metrics.get("warnings")
            or metrics.get("keyboard_interrupt")
            or metrics.get("traceback")
        )

    sorted_artifacts = sorted(
        artifacts,
        key=lambda item: (
            priority.get(str(item.get("kind") or ""), 100),
            str(item.get("iteration_id") or display_iteration_id or latest_iteration),
            str(item.get("name") or item.get("path") or ""),
        ),
    )
    seen_by_kind: dict[str, int] = {}
    rows: list[dict[str, Any]] = []
    for item in sorted_artifacts:
        kind = str(item.get("kind") or "")
        if kind not in operator_kinds:
            continue
        if item.get("iteration_id"):
            selected_iteration = display_iteration_id or latest_iteration
            if selected_iteration and item.get("iteration_id") != selected_iteration:
                continue
        if not _actionable_log(item):
            continue
        limit = limits.get(kind)
        seen_by_kind[kind] = seen_by_kind.get(kind, 0) + 1
        if limit is not None and seen_by_kind[kind] > limit:
            continue
        path = Path(str(item.get("path") or ""))
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        health_flags: list[str] = []
        if path and not path.exists():
            health_flags.append("missing")
        rows.append(
            {
                "artifact_id": item.get("artifact_id"),
                "kind": item.get("kind"),
                "scope": item.get("iteration_id") or "run",
                "status": "missing" if health_flags else item.get("status", "ready"),
                "name": item.get("name") or path.name,
                "metrics": metrics,
                "path": str(path) if path else "",
                "relative_path": _rel(path, workspace) if path else "",
                "health_flags": health_flags,
            }
        )
        if len(rows) >= 8:
            break
    return rows
def _workload_from_artifacts(artifacts: list[dict[str, Any]], iteration_id: str | None) -> dict[str, Any]:
    totals = {"candidate": 0, "accurate": 0, "failed": 0}
    systems: set[int] = set()
    for item in artifacts:
        if item.get("kind") != "fp_selection_report":
            continue
        if iteration_id and item.get("iteration_id") != iteration_id:
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        selection = metrics.get("selection")
        frames = metrics.get("frames")
        if selection in totals and isinstance(frames, int):
            totals[selection] += frames
        system = metrics.get("system")
        if isinstance(system, int):
            systems.add(system)
    return {
        "systems": len(systems),
        **totals,
    }
def _compact_health_status(health: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "error" for item in health):
        return "error"
    if any(item.get("status") in {"warning", "missing"} for item in health):
        return "warning"
    return "ok"
def _display_document(
    *,
    title: str,
    summary: str,
    severity: str,
    updated_at: str,
    body: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "display_document",
        "producer": PRODUCER,
        "title": title,
        "summary": summary,
        "severity": severity,
        "updated_at": updated_at,
        "body": body,
    }
def _kv(items: list[tuple[str, Any]]) -> dict[str, Any]:
    return {
        "type": "key_values",
        "items": [{"key": key, "value": "" if value is None else str(value)} for key, value in items],
    }
def _list_block(title: str, values: list[Any]) -> dict[str, Any]:
    items: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("message") or value.get("label") or value.get("component") or value
            status = value.get("status")
            text = f"{status}: {label}" if status else str(label)
        else:
            text = str(value)
        items.append({"text": text})
    return {"type": "list", "title": title, "items": items}
def _compact_metrics(values: list[tuple[str, Any]]) -> str:
    return " | ".join(f"{label} {value}" for label, value in values if value not in {None, "", "-"})
def _display_metric_pairs(metrics: dict[str, Any], keys: list[str]) -> str:
    parts: list[str] = []
    for key in keys:
        if key in metrics and metrics.get(key) not in {None, ""}:
            label = {
                "errors": "err",
                "warnings": "warn",
                "lines": "lines",
                "models": "models",
                "curves": "curves",
                "logs": "logs",
                "candidate": "cand",
                "accurate": "acc",
                "failed": "fail",
                "tasks": "tasks",
                "datasets": "data",
            }.get(key, key)
            parts.append(f"{label}={metrics.get(key)}")
    return " ".join(parts) or "-"
def _artifact_kind_counts(artifacts: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in artifacts:
        kind = str(item.get("kind") or "unknown")
        counts[kind] = counts.get(kind, 0) + 1
    return counts
def _important_health_lines(health: list[dict[str, Any]], *, limit: int = 4) -> list[str]:
    actionable = [
        item
        for item in health
        if str(item.get("status") or "") in {"error", "warning", "missing"}
    ]
    if not actionable:
        return ["no blocking adapter signals"]
    priority = {"error": 0, "warning": 1, "missing": 2}
    rows = sorted(
        actionable,
        key=lambda item: (
            priority.get(str(item.get("status") or ""), 9),
            str(item.get("component") or ""),
        ),
    )
    lines: list[str] = []
    for item in rows[:limit]:
        status = item.get("status") or "-"
        component = item.get("component") or "health"
        message = item.get("message") or ""
        if component == "dispatcher":
            continue
        if component == "log_warnings":
            continue
        lines.append(f"{component} {status}{' | ' + str(message) if message else ''}")
    return lines
def _stage_ref(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    iteration = value.get("backend_iteration") or value.get("iteration_id") or "-"
    task = value.get("task_index")
    task_name = value.get("task_name") or value.get("phase") or ""
    stage = f"stage{task}" if task is not None else "stage?"
    suffix = f" {task_name}" if task_name else ""
    return f"{iteration} {stage}{suffix}"
def _next_stage_ref(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    task = value.get("task_index")
    task_name = value.get("task_name") or value.get("phase") or ""
    stage = f"stage{task}" if task is not None else "stage?"
    return f"{stage} {task_name}".strip()
def _risk_text(dispatcher: dict[str, Any], log_errors: dict[str, Any]) -> str:
    risks: list[str] = []
    if dispatcher.get("errors"):
        risks.append(f"dispatcher err {dispatcher.get('errors')}")
    for key, value in log_errors.items():
        if value:
            risks.append(str(key).replace("_", " "))
    return " | ".join(risks) or "none"
def _companion_display_document(
    *,
    project: dict[str, Any],
    project_id: str,
    run_id: str,
    run_state: dict[str, Any],
    companion_model: dict[str, Any],
    health: list[dict[str, Any]],
    iter_dirs: list[Path],
    records: list[dict[str, int]],
    diagnostics: list[str],
    updated_at: str,
) -> dict[str, Any]:
    last = run_state.get("last_completed") if isinstance(run_state.get("last_completed"), dict) else {}
    expected = run_state.get("next_expected") if isinstance(run_state.get("next_expected"), dict) else {}
    workload = companion_model.get("workload") if isinstance(companion_model.get("workload"), dict) else {}
    log_summary = run_state.get("log_summary") if isinstance(run_state.get("log_summary"), dict) else {}
    log_selection = log_summary.get("selection") if isinstance(log_summary.get("selection"), dict) else {}
    dispatcher = log_summary.get("dispatcher") if isinstance(log_summary.get("dispatcher"), dict) else {}
    log_errors = log_summary.get("errors") if isinstance(log_summary.get("errors"), dict) else {}
    selection = log_selection if any(log_selection.values()) else workload
    health_status = companion_model.get("health_status") or "info"
    state_text = _stage_ref(last)
    next_text = _next_stage_ref(expected)
    selection_text = _compact_metrics(
        [
            ("cand", selection.get("candidate", 0)),
            ("acc", selection.get("accurate", 0)),
            ("fail", selection.get("failed", 0)),
        ]
    )
    queue_text = _compact_metrics(
        [
            ("sub", dispatcher.get("submitted", 0)),
            ("done", dispatcher.get("finished", 0)),
            ("rec", dispatcher.get("recovered", 0)),
            ("err", dispatcher.get("errors", 0)),
        ]
    )
    risk_text = _risk_text(dispatcher, log_errors)
    summary = f"{state_text} | next {next_text} | {health_status}"
    body = [
        _kv(
            [
                ("Run", run_id),
                ("State", state_text),
                ("Next", next_text),
                ("Select", selection_text),
                ("Queue", queue_text),
                ("Risk", risk_text),
            ]
        )
    ]
    signals = [line for line in _important_health_lines(health) if line]
    if signals and signals != ["no blocking adapter signals"]:
        body.append(_list_block("Risk detail", signals))
    if diagnostics:
        body.append(_list_block("Diagnostics", diagnostics))
    return _display_document(
        title="DP-GEN Companion",
        summary=summary,
        severity=health_status,
        updated_at=updated_at,
        body=body,
    )
def _artifacts_display_document(
    *,
    project_id: str,
    run_id: str,
    artifact_model: dict[str, Any],
    all_artifacts: list[dict[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    rows = artifact_model.get("rows") if isinstance(artifact_model.get("rows"), list) else []
    counts = _artifact_kind_counts(all_artifacts)
    count_text = " | ".join(
        part
        for part in (
            f"ckpt {counts.get('model_checkpoint', 0)}",
            f"log {sum(value for key, value in counts.items() if key.endswith('_log') or key == 'log')}",
            f"data {counts.get('label_dataset', 0)}",
            f"cfg {counts.get('config', 0)}",
            f"stage {counts.get('training_stage', 0) + counts.get('model_deviation_stage', 0) + counts.get('fp_stage', 0)}",
        )
        if not part.endswith(" 0")
    )
    table_rows: list[list[str]] = []
    for row in rows[:8]:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        kind = str(row.get("kind") or "-")
        if kind in {"error_log", "dispatcher_log", "dpgen_log", "recover_log"} or kind.endswith("_log"):
            metrics_text = _display_metric_pairs(metrics, ["errors", "warnings", "lines"])
        elif kind in {"training_stage", "model_deviation_stage", "fp_stage"}:
            metrics_text = _display_metric_pairs(metrics, ["models", "curves", "logs", "tasks", "datasets", "candidate", "accurate", "failed"])
        else:
            metrics_text = " ".join(f"{key}={value}" for key, value in list(metrics.items())[:3])
        table_rows.append(
            [
                str(row.get("name") or row.get("path") or kind),
                metrics_text or "-",
            ]
        )
    body = [
        _kv(
            [
                ("Total", len(all_artifacts)),
                ("Types", count_text or "-"),
                ("Focus", artifact_model.get("display_iteration_id") or "-"),
            ]
        ),
        {
            "type": "table",
            "columns": ["Priority", "Signal"],
            "rows": table_rows or [["state", "(no artifacts)"]],
        },
    ]
    return _display_document(
        title="DP-GEN Artifacts",
        summary="priority evidence",
        severity="info",
        updated_at=updated_at,
        body=body,
    )
