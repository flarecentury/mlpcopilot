#!/usr/bin/env python3
"""Smoke-test the DP-GEN runtime adapter against an existing DP-GEN workdir.

This script is intentionally runnable as a standalone test utility:

    uv run python tests/test_dpgen_adapter_real_data.py

It creates a temporary MLP Copilot workspace, installs the DP-GEN adapter
overlay, symlinks the real DP-GEN directory into a test run, projects it, and
verifies that only adapter display documents are produced for the TUI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

DEFAULT_WORKSPACE_DPGEN_PATH = (
    Path.home()
    / ".mlpcopilot"
    / "workspace"
    / "projects"
    / "local_dpgen"
    / "runs"
    / "run_local"
    / "backend"
    / "dpgen"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test dpgen_adapter with a real DP-GEN workdir.")
    default_dpgen = os.getenv("MLPCOPILOT_REAL_DPGEN_FIXTURE")
    parser.add_argument(
        "--dpgen-path",
        type=Path,
        default=Path(default_dpgen).expanduser() if default_dpgen else None,
        help="Existing DP-GEN workdir. Defaults to MLPCOPILOT_REAL_DPGEN_FIXTURE when set.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the temporary workspace after the test and print its path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dpgen_path is None:
        raise SystemExit("Provide --dpgen-path or set MLPCOPILOT_REAL_DPGEN_FIXTURE.")
    source = args.dpgen_path.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"DP-GEN path not found: {source}")

    if args.keep_workspace:
        import tempfile

        workspace_root = Path(tempfile.mkdtemp(prefix="mlpcopilot_dpgen_adapter_test_"))
        try:
            result = run_test(workspace_root, source)
            print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        except Exception:
            print(f"Kept workspace for debugging: {workspace_root}")
            raise
        print(f"Kept workspace: {workspace_root}")
        return 0

    with TemporaryDirectory(prefix="mlpcopilot_dpgen_adapter_test_") as td:
        result = run_test(Path(td), source)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


def run_test(workspace: Path, source: Path) -> dict:
    from mlpcopilot.config.schema import Config
    from mlpcopilot.plugins.dpgen_adapter import init_dpgen_workspace_overlay, project_dpgen_run
    from mlpcopilot.runtime.tui.layouts.render_data import (
        _load_active_display_docs,
        collect_tui_render_data,
    )
    from mlpcopilot.runtime.tui.views.artifacts_panel import _artifacts_renderable
    from mlpcopilot.runtime.tui.views.campaign import _campaign_renderable
    from mlpcopilot.runtime.workspace import (
        create_mlp_project,
        create_mlp_run,
        sync_mlpcopilot_workspace,
    )

    workspace.mkdir(parents=True, exist_ok=True)
    sync_mlpcopilot_workspace(workspace, silent=True)
    overlay = init_dpgen_workspace_overlay(workspace)

    project = create_mlp_project(
        workspace,
        name="DSH SOAP DP-GEN sample",
        project_id="proj_dsh_soap",
        target_use_case="Adapter smoke test against existing DP-GEN iteration data",
    )
    create_mlp_run(workspace, project["project_id"], run_id="run_dsh_soap", backend="dpgen")
    run_dir = workspace / "projects" / project["project_id"] / "runs" / "run_dsh_soap"
    backend_link = run_dir / "backend" / "dpgen"
    replace_with_symlink(backend_link, source)

    started = time.time()
    summary = project_dpgen_run(workspace, project["project_id"], "run_dsh_soap")
    elapsed = time.time() - started

    artifacts_doc, companion_doc = _load_active_display_docs(workspace)
    assert_display_doc(artifacts_doc, "artifacts.display.json")
    assert_display_doc(companion_doc, "companion.display.json")

    ui_dir = run_dir / "ui"
    assert not (ui_dir / "artifacts.state.json").exists(), "legacy artifacts.state.json should not exist"
    assert not (ui_dir / "companion.state.json").exists(), "legacy companion.state.json should not exist"

    artifacts_jsonl = [line for line in (run_dir / "artifacts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(artifacts_jsonl) == summary["artifacts"], "artifacts.jsonl count should match projection summary"

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(workspace)}},
        }
    )
    render_data = collect_tui_render_data(config)
    # Smoke-test that the generic TUI renderers accept adapter DisplayDocument payloads.
    _campaign_renderable(
        workspace,
        companion_display=render_data.companion_display,
        workstate_display=render_data.workstate_display,
    )
    _artifacts_renderable(render_data.runs, render_data.recent_files, render_data.artifacts_display)

    return {
        "status": "ok",
        "workspace": str(workspace),
        "source": str(source),
        "elapsed_seconds": round(elapsed, 2),
        "overlay_installed": overlay["installed"],
        "record_entries": summary["record_entries"],
        "detected_iterations": summary["detected_iterations"],
        "artifacts": summary["artifacts"],
        "last_completed": summary["last_completed"],
        "next_expected": summary["next_expected"],
        "artifacts_display": {
            "title": artifacts_doc.get("title"),
            "summary": artifacts_doc.get("summary"),
        },
        "companion_display": {
            "title": companion_doc.get("title"),
            "summary": companion_doc.get("summary"),
            "severity": companion_doc.get("severity"),
        },
        "legacy_state_files_exist": {
            "artifacts_state": (ui_dir / "artifacts.state.json").exists(),
            "companion_state": (ui_dir / "companion.state.json").exists(),
        },
    }


def test_real_dpgen_fixture_projects_to_tui_display(tmp_path: Path) -> None:
    source = resolve_real_dpgen_fixture_or_skip()

    result = run_test(tmp_path, source)

    assert result["record_entries"] >= 2
    assert result["detected_iterations"] >= 2
    assert _has_stage_product(source, "00.train")
    assert _has_stage_product(source, "01.model_devi")
    assert _has_stage_product(source, "02.fp")
    assert result["companion_display"]["title"] == "DP-GEN Companion"
    assert result["artifacts_display"]["title"] == "DP-GEN Artifacts"


def test_training_controller_reads_real_dpgen_fixture(tmp_path: Path) -> None:
    source = resolve_real_dpgen_fixture_or_skip()
    mcp_src = Path(__file__).resolve().parents[1] / "mlpcopilot" / "mcps" / "mlp_training_controller_mcp" / "src"
    sys.path.insert(0, str(mcp_src))
    from mlp_training_controller_mcp.backends.dpgen import DPGenBackend  # noqa: E402

    backend = DPGenBackend()
    inspected = json.loads(backend.inspect_training_project(str(source)))
    status = json.loads(backend.get_training_status(str(source)))
    iterations = json.loads(backend.list_training_iterations(str(source)))
    logs = json.loads(backend.collect_training_logs(str(source), max_lines=20))
    failures = json.loads(backend.analyze_training_failure(str(source), max_lines=80))

    assert inspected["status"] == "success"
    assert inspected["metrics"]["has_record"] is True
    assert inspected["metrics"]["iterations_found"] >= 2
    assert status["status"] == "success"
    assert status["metrics"]["status_source"] == "record.dpgen + iteration directories"
    assert iterations["status"] == "success"
    assert len(iterations["metrics"]["iterations"]) >= 2
    assert logs["status"] == "success"
    assert logs["metrics"]["logs_found"] > 0
    assert failures["status"] == "success"
    assert failures["metrics"]["logs_scanned"] > 0


def resolve_real_dpgen_fixture_or_skip() -> Path:
    raw_env = os.getenv("MLPCOPILOT_REAL_DPGEN_FIXTURE")
    candidates = [
        Path(raw_env).expanduser() if raw_env else None,
        DEFAULT_WORKSPACE_DPGEN_PATH.expanduser(),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        source = candidate.resolve(strict=False)
        if _looks_like_real_dpgen_run(source):
            return source
    pytest.skip(
        "real DP-GEN fixture not found; set MLPCOPILOT_REAL_DPGEN_FIXTURE "
        "or create ~/.mlpcopilot/workspace/projects/local_dpgen/runs/run_local/backend/dpgen"
    )


def _looks_like_real_dpgen_run(path: Path) -> bool:
    return path.is_dir() and (path / "record.dpgen").is_file() and any(path.glob("iter.*"))


def _has_stage_product(path: Path, stage_dir: str) -> bool:
    return any(item.is_dir() for item in path.glob(f"iter.*/{stage_dir}"))


def replace_with_symlink(link_path: Path, target: Path) -> None:
    if link_path.is_symlink() or link_path.is_file():
        link_path.unlink()
    elif link_path.is_dir():
        link_path.rmdir()
    link_path.symlink_to(target, target_is_directory=True)


def assert_display_doc(value: dict | None, label: str) -> None:
    assert isinstance(value, dict), f"{label} was not loaded"
    assert value.get("kind") == "display_document", f"{label} is not a display document"
    assert isinstance(value.get("body"), list), f"{label} has no display body"


if __name__ == "__main__":
    raise SystemExit(main())
