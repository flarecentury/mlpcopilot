"""Workspace overlay installation for the DP-GEN runtime adapter."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

PLUGIN_DIR = Path(__file__).resolve().parent
ASSETS_DIR = PLUGIN_DIR / "assets"


def init_dpgen_workspace_overlay(workspace: Path, *, force: bool = False) -> dict[str, Any]:
    """Install DP-GEN adapter overlay files without touching runtime core files."""
    workspace = workspace.expanduser()
    installed: list[str] = []
    skipped: list[str] = []
    for source_root, target_root in (
        (ASSETS_DIR / "workspace", workspace / "profiles" / "dpgen"),
        (ASSETS_DIR / "templates", workspace / "profiles" / "dpgen" / "templates"),
    ):
        if not source_root.exists():
            continue
        for source in sorted(source_root.iterdir()):
            if not source.is_file():
                continue
            target = target_root / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not force:
                skipped.append(_rel(target, workspace))
                continue
            shutil.copyfile(source, target)
            installed.append(_rel(target, workspace))
    return {
        "status": "success",
        "adapter": "dpgen_adapter",
        "installed": installed,
        "skipped": skipped,
    }


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)

