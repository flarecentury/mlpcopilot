"""DP-GEN status, logs, failure analysis, and report operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..schemas import artifact, result, sha256_file
from ..secret_redactor import redact_text


def inspect_training_project(backend: str, project_path: str) -> str:
    from .dpgen_common import (
        STAGES,
        _iter_dirs,
        _load_config,
        _machine_secret_warnings,
        _next_stage,
        _now_iso,
        _project,
        _read_record,
    )

    project = _project(project_path)
    param_path = project / "param.json"
    machine_path = project / "machine.json"
    iter_dirs = _iter_dirs(project)
    current_iter, current_stage, record_warnings = _read_record(project)
    next_iter, next_stage, next_stage_name = _next_stage(current_iter, current_stage)
    machine_data, machine_errors = _load_config(machine_path) if machine_path.exists() else (None, [])
    warnings = list(record_warnings)
    if machine_data is not None:
        warnings.extend(_machine_secret_warnings(machine_data))
    warnings.extend(machine_errors)
    metrics = {
        "backend": backend,
        "project_path": str(project),
        "project_exists": project.is_dir(),
        "has_param": param_path.is_file(),
        "has_machine": machine_path.is_file(),
        "has_record": (project / "record.dpgen").is_file(),
        "has_log": (project / "dpgen.log").is_file(),
        "iterations_found": len(iter_dirs),
        "current_iteration": current_iter,
        "current_stage": current_stage,
        "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
        "next_iteration": next_iter,
        "next_stage": next_stage,
        "next_stage_name": next_stage_name,
        "status_source": "record.dpgen + project files",
        "queried_at": _now_iso(),
        "has_controller_state": any(project.glob("runs/*/training_controller_state.json")),
    }
    return result(
        status="success" if project.is_dir() else "failed",
        summary=f"Detected DP-GEN backend project with {len(iter_dirs)} iterations."
        if project.is_dir()
        else f"Project path does not exist: {project}",
        metrics=metrics,
        artifacts=[
            artifact(path, "config")
            for path in (param_path, machine_path, project / "record.dpgen", project / "dpgen.log")
            if path.is_file()
        ],
        warnings=warnings,
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def get_training_status(backend: str, project_path: str) -> str:
    from .dpgen_common import (
        STAGES,
        _iter_dirs,
        _next_stage,
        _now_iso,
        _project,
        _read_record,
        _status_for_iter,
    )

    project = _project(project_path)
    iter_dirs = _iter_dirs(project)
    current_iter, current_stage, warnings = _read_record(project)
    next_iter, next_stage, next_stage_name = _next_stage(current_iter, current_stage)
    current_path = project / f"iter.{current_iter:06d}" if current_iter is not None else (iter_dirs[-1] if iter_dirs else None)
    current_metrics = _status_for_iter(current_path) if current_path and current_path.exists() else {}
    record_path = project / "record.dpgen"
    metrics = {
        "backend": backend,
        "project_path": str(project),
        "iterations_found": len(iter_dirs),
        "current_iteration": current_iter,
        "current_stage": current_stage,
        "stage_name": STAGES.get(current_stage) if current_stage is not None else None,
        "next_iteration": next_iter,
        "next_stage": next_stage,
        "next_stage_name": next_stage_name,
        "status_source": "record.dpgen + iteration directories",
        "record_path": str(record_path),
        "record_sha256": sha256_file(record_path) if record_path.is_file() else None,
        "queried_at": _now_iso(),
        **current_metrics,
    }
    return result(
        status="success" if project.is_dir() else "failed",
        summary=(
            f"DP-GEN backend is at iter.{current_iter:06d} stage {current_stage} "
            f"{STAGES.get(current_stage, 'unknown')}."
            if current_iter is not None and current_stage is not None
            else "No record.dpgen state found."
        ),
        metrics=metrics,
        artifacts=[artifact(project / "record.dpgen", "status")] if (project / "record.dpgen").is_file() else [],
        warnings=warnings,
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def list_training_iterations(backend: str, project_path: str) -> str:
    from .dpgen_common import _iter_dirs, _project, _status_for_iter

    project = _project(project_path)
    iterations = [_status_for_iter(path) for path in _iter_dirs(project)]
    return result(
        status="success" if project.is_dir() else "failed",
        summary=f"Found {len(iterations)} DP-GEN backend iterations.",
        metrics={"backend": backend, "iterations": iterations},
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def inspect_training_iteration(backend: str, project_path: str, iteration: int) -> str:
    from .dpgen_common import _project, _status_for_iter

    project = _project(project_path)
    iter_path = project / f"iter.{iteration:06d}"
    if not iter_path.is_dir():
        return result(
            status="failed",
            summary=f"Iteration not found: iter.{iteration:06d}",
            errors=[f"No such iteration directory: {iter_path}"],
        )
    metrics = _status_for_iter(iter_path)
    artifacts = [
        artifact(path, "log")
        for pattern in ("00.train/*/train.log", "01.model_devi/task.*/model_devi.out", "02.fp/task.*/OUTCAR", "02.fp/task.*/vasprun.xml")
        for path in iter_path.glob(pattern)
        if path.is_file()
    ][:100]
    return result(
        status="success",
        summary=f"Inspected DP-GEN backend iteration iter.{iteration:06d}.",
        metrics={"backend": backend, **metrics},
        artifacts=artifacts,
    )


def collect_training_logs(backend: str, project_path: str, max_lines: int = 80) -> str:
    from .dpgen_common import LOG_CANDIDATES, _project, _tail

    project = _project(project_path)
    log_paths: list[Path] = []
    for pattern in LOG_CANDIDATES:
        log_paths.extend(path for path in project.glob(pattern) if path.is_file())
    log_paths = sorted(set(log_paths))
    snippets = [
        {"path": str(path), "sha256": sha256_file(path), "tail": _tail(path, max_lines=max_lines)}
        for path in log_paths[:50]
    ]
    return result(
        status="success" if project.is_dir() else "failed",
        summary=f"Collected {len(log_paths)} candidate DP-GEN backend log files.",
        metrics={"backend": backend, "logs_found": len(log_paths), "snippets": snippets},
        artifacts=[artifact(path, "log") for path in log_paths[:100]],
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def analyze_training_failure(backend: str, project_path: str, max_lines: int = 200) -> str:
    from .dpgen_common import FAILURE_PATTERNS, LOG_CANDIDATES, _project, _tail

    project = _project(project_path)
    log_paths: list[Path] = []
    for pattern in LOG_CANDIDATES:
        log_paths.extend(path for path in project.glob(pattern) if path.is_file())
    log_paths = sorted(set(log_paths))
    findings: list[dict[str, Any]] = []
    for path in log_paths[:100]:
        lines = _tail(path, max_lines=max_lines)
        text = "\n".join(lines)
        for failure_type, pattern, summary, actions in FAILURE_PATTERNS:
            match = pattern.search(text)
            if match:
                evidence_line = next((line for line in lines if pattern.search(line)), match.group(0))
                findings.append(
                    {
                        "failure_type": failure_type,
                        "summary": summary,
                        "path": str(path),
                        "evidence": redact_text(evidence_line)[:500],
                        "recommended_actions": actions,
                    }
                )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in findings:
        key = (str(item["failure_type"]), str(item["path"]))
        if key not in seen:
            unique.append(item)
            seen.add(key)
    status = "success" if project.is_dir() else "failed"
    summary = f"Detected {len(unique)} possible failure signatures." if unique else "No known failure signature detected in candidate logs."
    return result(
        status=status,
        summary=summary,
        metrics={"backend": backend, "findings": unique, "logs_scanned": len(log_paths)},
        artifacts=[artifact(path, "log") for path in log_paths[:100]],
        warnings=[] if unique else ["No rule matched; inspect collected logs manually."],
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )


def build_training_run_report(
    backend: str,
    project_path: str,
    output_path: str | None = None,
) -> str:
    from .dpgen_common import (
        STAGES,
        _iter_dirs,
        _project,
        _read_record,
        _status_for_iter,
        _write_manifest,
    )

    project = _project(project_path)
    if output_path:
        report_path = _project(output_path)
    else:
        stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        report_path = project / "reports" / f"training_run_report_{stamp}.md"

    iter_dirs = _iter_dirs(project)
    current_iter, current_stage, warnings = _read_record(project)
    iterations = [_status_for_iter(path) for path in iter_dirs]
    failure_payload = json.loads(analyze_training_failure(backend, project_path))
    findings = failure_payload.get("metrics", {}).get("findings", [])

    param_path = project / "param.json"
    machine_path = project / "machine.json"
    lines = [
        "# Training Run Report",
        "",
        f"- Backend: `{backend}`",
        f"- Project: `{project}`",
        f"- Generated at: `{datetime.now(tz=UTC).isoformat()}`",
        f"- Current iteration: `{current_iter}`",
        f"- Current stage: `{current_stage}`",
        f"- Stage name: `{STAGES.get(current_stage) if current_stage is not None else None}`",
        f"- Iterations found: `{len(iter_dirs)}`",
        "",
        "## Config Artifacts",
        "",
    ]
    lines.append(f"- `param.json`: `{sha256_file(param_path)}`" if param_path.is_file() else "- `param.json`: missing")
    lines.append(f"- `machine.json`: `{sha256_file(machine_path)}`" if machine_path.is_file() else "- `machine.json`: missing")

    lines.extend(["", "## Iteration Summary", ""])
    if iterations:
        lines.append("| Iteration | Train | Model Devi | FP | Candidate | Failed | Accurate | FP Tasks | Data Dirs |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for item in iterations:
            lines.append(
                "| {iteration} | {has_train} | {has_model_devi} | {has_fp} | "
                "{candidate_frames} | {failed_frames} | {accurate_frames} | {fp_tasks} | {data_dirs} |".format(**item)
            )
    else:
        lines.append("No `iter.??????` directories found.")

    lines.extend(["", "## Failure Analysis", ""])
    if findings:
        for item in findings:
            lines.extend(
                [
                    f"### {item.get('failure_type')}",
                    "",
                    f"- Summary: {item.get('summary')}",
                    f"- Path: `{item.get('path')}`",
                    f"- Evidence: `{item.get('evidence')}`",
                    "- Recommended actions:",
                ]
            )
            for action in item.get("recommended_actions") or []:
                lines.append(f"  - {action}")
            lines.append("")
    else:
        lines.append("No known failure signature detected by the current rule set.")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This report summarizes training-control evidence only. It does not claim checkpoint reliability or dataset coverage.",
        ]
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    artifacts_payload = [artifact(report_path, "report")]
    manifest_artifact = _write_manifest(
        project,
        source="build_training_run_report",
        inputs=[
            {"path": str(param_path), "sha256": sha256_file(param_path) if param_path.is_file() else None},
            {"path": str(machine_path), "sha256": sha256_file(machine_path) if machine_path.is_file() else None},
        ],
        outputs=[{"path": str(report_path), "sha256": sha256_file(report_path)}],
        artifacts_payload=artifacts_payload,
        warnings=warnings,
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )
    if manifest_artifact is not None:
        artifacts_payload.append(manifest_artifact)
    return result(
        status="success" if project.is_dir() else "failed",
        summary=f"Generated training run report: {report_path}",
        metrics={
            "backend": backend,
            "project_path": str(project),
            "output_path": str(report_path),
            "iterations_found": len(iter_dirs),
            "findings_count": len(findings),
        },
        artifacts=artifacts_payload,
        warnings=[] if project.is_dir() else [f"Report generated for missing/non-directory project path: {project}"],
        errors=[] if project.is_dir() else [f"No such project directory: {project}"],
    )
