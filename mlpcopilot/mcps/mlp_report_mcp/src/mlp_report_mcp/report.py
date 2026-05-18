"""Evidence-only report generation for MLP workflow artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import artifact, load_json, result, sha256_file


class ReportBackend:
    """Build reports from existing manifests, approval records, and artifacts."""

    def build_evidence_report(
        self,
        workspace_path: str,
        artifact_paths: list[str] | None = None,
        output_path: str | None = None,
        title: str = "MLP Evidence Report",
        max_artifacts: int = 200,
    ) -> str:
        workspace = _resolve(workspace_path)
        warnings: list[str] = []
        errors: list[str] = []
        if not workspace.exists():
            return result(
                status="failed",
                summary="Workspace path does not exist.",
                metrics={"workspace_path": str(workspace)},
                errors=[f"No such workspace path: {workspace}"],
            )

        runs = _load_run_manifests(workspace, warnings)
        approvals = _load_approvals(workspace, warnings)
        artifact_refs = _collect_artifact_refs(
            runs,
            explicit_paths=[_resolve(item) for item in artifact_paths or []],
            max_artifacts=max_artifacts,
            warnings=warnings,
        )
        target = _resolve(output_path) if output_path else _default_report_path(workspace)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                _report_markdown(
                    title=title,
                    workspace=workspace,
                    runs=runs,
                    approvals=approvals,
                    artifact_refs=artifact_refs,
                    warnings=warnings,
                ),
                encoding="utf-8",
            )
        except OSError as exc:
            errors.append(f"{type(exc).__name__}: {exc}")

        artifacts = []
        if target.is_file():
            artifacts.append(artifact(target, "report"))
        status = "failed" if errors else "success"
        return result(
            status=status,
            summary=f"Wrote MLP evidence report: {target}"
            if status == "success"
            else "Failed to write MLP evidence report.",
            metrics={
                "workspace_path": str(workspace),
                "report_path": str(target),
                "run_count": len(runs),
                "artifact_count": len(artifact_refs),
                "pending_approval_count": len(approvals["pending"]),
                "decision_count": len(approvals["decisions"]),
            },
            artifacts=artifacts,
            warnings=warnings,
            errors=errors,
        )


def _load_run_manifests(workspace: Path, warnings: list[str]) -> list[dict[str, Any]]:
    runs_dir = workspace / "runs"
    runs: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return runs
    for path in sorted(runs_dir.glob("*/manifest.json")):
        try:
            payload = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"Skipped invalid run manifest {path}: {type(exc).__name__}: {exc}")
            continue
        if isinstance(payload, dict):
            payload["_manifest_path"] = str(path)
            runs.append(payload)
    runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return runs


def _load_approvals(workspace: Path, warnings: list[str]) -> dict[str, list[dict[str, Any]]]:
    approvals = {"pending": [], "decisions": []}
    approvals_dir = workspace / "approvals"
    if not approvals_dir.is_dir():
        return approvals
    for path in sorted(approvals_dir.rglob("*.jsonl")):
        bucket = "decisions" if path.name == "decisions.jsonl" else "pending"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            warnings.append(f"Skipped approval log {path}: {type(exc).__name__}: {exc}")
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                warnings.append(f"Skipped invalid approval record in {path}: {exc}")
                continue
            if isinstance(payload, dict):
                payload["_source_path"] = str(path)
                approvals[bucket].append(payload)
    return approvals


def _collect_artifact_refs(
    runs: list[dict[str, Any]],
    *,
    explicit_paths: list[Path],
    max_artifacts: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in runs:
        for raw in _as_list(run.get("artifacts")) + _as_list(run.get("outputs")):
            ref = _artifact_ref(raw, source_run=str(run.get("run_id") or ""))
            if ref:
                _append_ref(refs, seen, ref)
    for path in explicit_paths:
        if path.exists() and path.is_file():
            _append_ref(
                refs,
                seen,
                {"type": "explicit", "path": str(path), "sha256": sha256_file(path), "source_run": None},
            )
        else:
            warnings.append(f"Explicit artifact path is not a file: {path}")
    if len(refs) > max_artifacts:
        warnings.append(f"Artifact list truncated to max_artifacts={max_artifacts}.")
        refs = refs[:max_artifacts]
    return refs


def _artifact_ref(raw: Any, *, source_run: str) -> dict[str, Any] | None:
    if isinstance(raw, str):
        return {"type": "artifact", "path": raw, "sha256": None, "source_run": source_run}
    if isinstance(raw, dict):
        path = raw.get("path")
        if isinstance(path, str):
            return {
                "type": raw.get("type") or raw.get("artifact_type") or "artifact",
                "path": path,
                "sha256": raw.get("sha256"),
                "source_run": source_run,
            }
    return None


def _append_ref(refs: list[dict[str, Any]], seen: set[str], ref: dict[str, Any]) -> None:
    key = str(ref.get("path") or "")
    if not key or key in seen:
        return
    seen.add(key)
    refs.append(ref)


def _report_markdown(
    *,
    title: str,
    workspace: Path,
    runs: list[dict[str, Any]],
    approvals: dict[str, list[dict[str, Any]]],
    artifact_refs: list[dict[str, Any]],
    warnings: list[str],
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Generated at: `{datetime.now(UTC).isoformat()}`",
        f"- Workspace: `{workspace}`",
        "",
        "This report summarizes existing evidence only. It does not create scientific metrics or claim model readiness.",
        "",
        "## Runs",
        "",
    ]
    if runs:
        rows = [
            [
                str(run.get("run_id") or ""),
                str(run.get("source") or ""),
                str(run.get("created_at") or ""),
                str(len(_as_list(run.get("metrics")))),
                str(len(_as_list(run.get("artifacts")))),
                str(len(_as_list(run.get("decisions")))),
            ]
            for run in runs
        ]
        lines.extend(_markdown_table(["Run", "Source", "Created", "Metrics", "Artifacts", "Decisions"], rows))
    else:
        lines.append("No run manifests were found.")
    lines.extend(["", "## Artifacts", ""])
    if artifact_refs:
        rows = [
            [
                str(ref.get("type") or ""),
                str(ref.get("source_run") or ""),
                str(ref.get("path") or ""),
                str(ref.get("sha256") or ""),
            ]
            for ref in artifact_refs
        ]
        lines.extend(_markdown_table(["Type", "Run", "Path", "SHA256"], rows))
    else:
        lines.append("No artifact references were found.")

    lines.extend(["", "## Approvals", ""])
    lines.append(f"- Pending approvals: `{len(approvals['pending'])}`")
    lines.append(f"- Decisions: `{len(approvals['decisions'])}`")
    if approvals["pending"] or approvals["decisions"]:
        rows = [
            [
                str(item.get("approval_id") or ""),
                str(item.get("status") or ""),
                str(item.get("action_type") or ""),
                str(item.get("run_id") or ""),
                str(item.get("title") or ""),
            ]
            for item in approvals["pending"] + approvals["decisions"]
        ]
        lines.extend(["", *_markdown_table(["Approval", "Status", "Action", "Run", "Title"], rows)])
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines).rstrip() + "\n"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    normalized_rows = [[_escape_table_cell(cell) for cell in row] for row in rows]
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in normalized_rows),
    ]


def _escape_table_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _default_report_path(workspace: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return workspace / "reports" / f"mlp_evidence_report_{stamp}.md"


def _resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()
