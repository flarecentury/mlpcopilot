"""Artifact pane rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.table import Table

from mlpcopilot.runtime.artifacts import RunManifest
from mlpcopilot.runtime.tui.common import _display_workspace_path
from mlpcopilot.runtime.tui.views.display_document import (
    display_document_title,
    is_display_document,
    render_display_document,
)


def _artifacts_renderable(
    runs: list[RunManifest],
    recent_files: list[Any] | None = None,
    artifacts_display: dict[str, Any] | None = None,
) -> Table:
    if artifacts_display and is_display_document(artifacts_display):
        return render_display_document(artifacts_display)

    table = Table.grid(expand=True)
    table.add_column("Message")
    table.add_row("(no adapter display)")
    return table

def _artifacts_panel_title(workspace: Path, artifacts_display: dict[str, Any] | None = None) -> str:
    if artifacts_display and is_display_document(artifacts_display):
        return display_document_title(artifacts_display, "Artifacts")
    return f"Artifacts ({_display_workspace_path(workspace, max_len=52)})"
