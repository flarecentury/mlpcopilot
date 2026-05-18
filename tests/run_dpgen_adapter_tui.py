#!/usr/bin/env python3
"""Prepare a DP-GEN adapter workspace and render or launch the full TUI.

Examples:

    # Render one TUI snapshot in the terminal.
    uv run python tests/run_dpgen_adapter_tui.py

    # Launch the interactive TUI against the prepared workspace.
    uv run python tests/run_dpgen_adapter_tui.py --interactive --keep-workspace

    # Use a different DP-GEN workdir.
    uv run python tests/run_dpgen_adapter_tui.py --dpgen-path /path/to/dpgen/run

The adapter determines the current DP-GEN iteration from the last valid line in
`record.dpgen`. Log files are used only for additional progress/health display.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DPGEN_PATH = Path(
    os.getenv(
        "MLPCOPILOT_TUI_DPGEN_DIR",
        str(REPO_ROOT / "demos" / "dpgen_quickstart" / "fixture"),
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or launch TUI using dpgen_adapter output.")
    parser.add_argument(
        "--dpgen-path",
        type=Path,
        default=DEFAULT_DPGEN_PATH,
        help=f"Existing DP-GEN workdir. Default: {DEFAULT_DPGEN_PATH}",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch the interactive `mlpcopilot tui` after preparing the workspace.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep the prepared workspace after the script exits.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Use this workspace instead of a temporary one.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.dpgen_path.expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"DP-GEN path not found: {source}")

    if args.workspace is not None:
        workspace = args.workspace.expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        return run(workspace, source, interactive=args.interactive, keep_workspace=True)

    if args.keep_workspace:
        workspace = Path(tempfile.mkdtemp(prefix="mlpcopilot_dpgen_tui_"))
        return run(workspace, source, interactive=args.interactive, keep_workspace=True)

    with TemporaryDirectory(prefix="mlpcopilot_dpgen_tui_") as td:
        return run(Path(td), source, interactive=args.interactive, keep_workspace=False)


def run(workspace: Path, source: Path, *, interactive: bool, keep_workspace: bool) -> int:
    from mlpcopilot.config.schema import Config
    from mlpcopilot.plugins.dpgen_adapter import init_dpgen_workspace_overlay, project_dpgen_run
    from mlpcopilot.runtime.tui import render_tui
    from mlpcopilot.runtime.workspace import create_mlp_project, create_mlp_run, sync_mlpcopilot_workspace

    sync_mlpcopilot_workspace(workspace, silent=True)
    overlay = init_dpgen_workspace_overlay(workspace)
    project = create_project_once(workspace, create_mlp_project)
    create_run_once(workspace, project["project_id"], create_mlp_run)

    run_dir = workspace / "projects" / project["project_id"] / "runs" / "run_dsh_soap"
    backend_link = run_dir / "backend" / "dpgen"
    replace_with_symlink(backend_link, source)

    summary = project_dpgen_run(workspace, project["project_id"], "run_dsh_soap")
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "source": str(source),
                "overlay_installed": overlay["installed"],
                "record_entries": summary["record_entries"],
                "detected_iterations": summary["detected_iterations"],
                "last_completed": summary["last_completed"],
                "next_expected": summary["next_expected"],
                "artifacts": summary["artifacts"],
                "display_docs": {
                    "artifacts": summary["written"]["artifacts_display"],
                    "companion": summary["written"]["companion_display"],
                },
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    )

    if interactive:
        print(f"\nLaunching TUI for workspace: {workspace}\n")
        cmd = [sys.executable, "-m", "mlpcopilot", "tui", "--workspace", str(workspace)]
        try:
            return subprocess.run(cmd, check=False).returncode
        finally:
            if keep_workspace:
                print(f"Workspace kept: {workspace}")

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"workspace": str(workspace)}},
        }
    )
    print("\n--- TUI snapshot ---\n")
    from rich.console import Console

    Console().print(render_tui(config))
    if keep_workspace:
        print(f"\nWorkspace kept: {workspace}")
    return 0


def create_project_once(workspace: Path, create_mlp_project):
    try:
        return create_mlp_project(
            workspace,
            name="DSH SOAP DP-GEN sample",
            project_id="proj_dsh_soap",
            target_use_case="DP-GEN adapter TUI test",
        )
    except FileExistsError:
        project_file = workspace / "projects" / "proj_dsh_soap" / "project.json"
        return json.loads(project_file.read_text(encoding="utf-8"))


def create_run_once(workspace: Path, project_id: str, create_mlp_run) -> None:
    try:
        create_mlp_run(workspace, project_id, run_id="run_dsh_soap", backend="dpgen")
    except FileExistsError:
        project_file = workspace / "projects" / project_id / "project.json"
        project = json.loads(project_file.read_text(encoding="utf-8"))
        project["active_run_id"] = "run_dsh_soap"
        project_file.write_text(json.dumps(project, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def replace_with_symlink(link_path: Path, target: Path) -> None:
    if link_path.is_symlink() or link_path.is_file():
        link_path.unlink()
    elif link_path.is_dir():
        link_path.rmdir()
    link_path.symlink_to(target, target_is_directory=True)


if __name__ == "__main__":
    raise SystemExit(main())
