"""Best-effort refresh of MLP Copilot DP-GEN runtime projections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def refresh_mlpcopilot_projection_for_backend(
    backend_path: Path,
    *,
    original_project_path: str | None = None,
) -> dict[str, Any] | None:
    """Refresh workspace read models when a DP-GEN backend belongs to an MLP run.

    The training-controller MCP can also operate on a plain DP-GEN directory.
    In that case there is no workspace run to refresh and this returns None.
    """
    matches = _find_workspace_runs_for_backend(backend_path, original_project_path=original_project_path)
    if not matches:
        return None

    try:
        from mlpcopilot.plugins.dpgen_adapter.projector import project_dpgen_run
    except Exception as exc:  # pragma: no cover - only hit in standalone plugin deployments
        return {
            "status": "skipped",
            "reason": f"mlpcopilot runtime projector is unavailable: {type(exc).__name__}: {exc}",
            "matched_runs": [_match_payload(match) for match in matches],
        }

    refreshed: list[dict[str, Any]] = []
    errors: list[str] = []
    for match in matches:
        workspace, project_id, run_id = match
        try:
            summary = project_dpgen_run(workspace, project_id, run_id)
        except Exception as exc:
            errors.append(f"{project_id}/{run_id}: {type(exc).__name__}: {exc}")
            continue
        refreshed.append(
            {
                "workspace": str(workspace),
                "project_id": project_id,
                "run_id": run_id,
                "run_state": summary.get("written", {}).get("run_state"),
                "artifacts_display": summary.get("written", {}).get("artifacts_display"),
                "companion_display": summary.get("written", {}).get("companion_display"),
                "record_entries": summary.get("record_entries"),
                "last_completed": summary.get("last_completed"),
                "next_expected": summary.get("next_expected"),
            }
        )

    if not refreshed and errors:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"
    return {
        "status": status,
        "refreshed": refreshed,
        "errors": errors,
    }


def _find_workspace_runs_for_backend(
    backend_path: Path,
    *,
    original_project_path: str | None = None,
) -> list[tuple[Path, str, str]]:
    candidates: list[tuple[Path, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    path_candidates = [backend_path]
    if original_project_path:
        path_candidates.append(Path(original_project_path).expanduser())

    for raw_path in path_candidates:
        match = _match_from_structural_path(raw_path)
        if match is not None:
            key = (str(_resolve(match[0])), match[1], match[2])
            if key not in seen:
                seen.add(key)
                candidates.append(match)

    for workspace in _workspace_scan_roots(path_candidates):
        if not workspace.exists():
            continue
        target = _resolve(backend_path)
        for run_file in sorted(workspace.glob("projects/*/runs/*/run.json")):
            run_dir = run_file.parent
            run = _read_json(run_file)
            if not run or run.get("backend") != "dpgen":
                continue
            candidate_backend = _run_backend_path(run_dir, run)
            if not _same_path(candidate_backend, target):
                continue
            project_id = str(run.get("project_id") or run_dir.parents[1].name)
            run_id = str(run.get("run_id") or run_dir.name)
            key = (str(_resolve(workspace)), project_id, run_id)
            if key not in seen:
                seen.add(key)
                candidates.append((workspace, project_id, run_id))
    return candidates


def _match_from_structural_path(path: Path) -> tuple[Path, str, str] | None:
    parts = path.expanduser().parts
    for index, part in enumerate(parts):
        if part != "projects":
            continue
        if index + 3 >= len(parts):
            continue
        if parts[index + 2] != "runs":
            continue
        workspace = Path(*parts[:index])
        project_id = parts[index + 1]
        run_id = parts[index + 3]
        run_dir = workspace / "projects" / project_id / "runs" / run_id
        run = _read_json(run_dir / "run.json")
        if not run or run.get("backend") != "dpgen":
            continue
        if _same_path(_run_backend_path(run_dir, run), path):
            return workspace, project_id, run_id
    return None


def _workspace_scan_roots(paths: list[Path]) -> list[Path]:
    roots: list[Path] = []
    for path in paths:
        match = _workspace_root_from_path(path)
        if match is not None:
            roots.append(match)
    roots.append(Path.home() / ".mlpcopilot" / "workspace")
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(_resolve(root))
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _workspace_root_from_path(path: Path) -> Path | None:
    parts = path.expanduser().parts
    for index, part in enumerate(parts):
        if part == "projects":
            return Path(*parts[:index])
    return None


def _run_backend_path(run_dir: Path, run: dict[str, Any]) -> Path:
    raw = str(run.get("backend_workdir") or "backend/dpgen")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = run_dir / path
    return path


def _same_path(left: Path, right: Path) -> bool:
    return _resolve(left) == _resolve(right)


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except OSError:
        return path.expanduser().absolute()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _match_payload(match: tuple[Path, str, str]) -> dict[str, str]:
    workspace, project_id, run_id = match
    return {
        "workspace": str(workspace),
        "project_id": project_id,
        "run_id": run_id,
    }
