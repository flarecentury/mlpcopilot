"""Health and next-action projection helpers for DP-GEN runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _build_health(
    *,
    diagnostics: list[str],
    iter_dirs: list[Path],
    records: list[dict[str, int]],
    log_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    health = [
        {
            "component": "dpgen_backend",
            "status": "warning" if diagnostics else "ok",
            "message": "; ".join(diagnostics) if diagnostics else f"detected {len(iter_dirs)} iteration directories",
        },
        {
            "component": "dpgen_record",
            "status": "missing" if not records else "ok",
            "message": "record.dpgen has no entries" if not records else f"{len(records)} recorded completed tasks",
        },
    ]
    if not log_summary:
        return health

    progress = log_summary.get("progress") if isinstance(log_summary.get("progress"), dict) else {}
    dispatcher = log_summary.get("dispatcher") if isinstance(log_summary.get("dispatcher"), dict) else {}
    errors = log_summary.get("errors") if isinstance(log_summary.get("errors"), dict) else {}
    selection = log_summary.get("selection") if isinstance(log_summary.get("selection"), dict) else {}
    if progress:
        health.append(
            {
                "component": "dpgen_log",
                "status": "ok",
                "message": f"observed iter.{int(progress.get('iteration', 0)):06d} task {int(progress.get('task', 0)):02d}",
            }
        )
    if dispatcher and any(dispatcher.values()):
        health.append(
            {
                "component": "dispatcher",
                "status": "warning" if dispatcher.get("errors") else "ok",
                "message": f"submitted {dispatcher.get('submitted', 0)}, finished {dispatcher.get('finished', 0)}, recovered {dispatcher.get('recovered', 0)}",
            }
        )
    if selection and any(selection.values()):
        health.append(
            {
                "component": "fp_selection",
                "status": "ok",
                "message": f"label candidates {selection.get('candidate', 0)}, accurate pool {selection.get('accurate', 0)}, failed pool {selection.get('failed', 0)}",
            }
        )
    if errors and any(errors.values()):
        active = ", ".join(key for key, value in errors.items() if value)
        health.append(
            {
                "component": "log_warnings",
                "status": "warning",
                "message": active,
            }
        )
    return health


def _suggested_next(expected: dict[str, Any] | None, run_id: str) -> list[dict[str, Any]]:
    if not expected:
        return []
    return [
        {
            "label": f"inspect {expected['backend_iteration']} {expected['phase']}",
            "action": "inspect_backend_phase",
            "event_id": f"dpgen:{run_id}:{expected['iter_index']}:{expected['task_index']}",
            "source": "record.dpgen",
        }
    ]
