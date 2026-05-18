"""TUI layout picker overlay rendering."""

from __future__ import annotations

from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.layouts.layout_registry import (
    TuiLayoutSpec,
    list_tui_layout_specs,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState


def layout_picker_specs() -> list[TuiLayoutSpec]:
    """Return available TUI layout specs in picker order."""
    return list_tui_layout_specs()


def selected_layout(state: RuntimeTuiState, specs: list[TuiLayoutSpec]) -> TuiLayoutSpec | None:
    if not specs:
        return None
    state.layout_picker_selection %= len(specs)
    return specs[state.layout_picker_selection]


def sync_layout_picker_selection(state: RuntimeTuiState) -> None:
    """Select the current layout when the picker opens."""
    for index, spec in enumerate(layout_picker_specs()):
        if spec.name == state.layout_name:
            state.layout_picker_selection = index
            return
    state.layout_picker_selection = 0


def _render_layout_picker_ansi(
    state: RuntimeTuiState,
    specs: list[TuiLayoutSpec],
    *,
    width: int,
    height: int,
) -> str:
    if not specs:
        return "Layouts: none.\n\nEsc closes this picker."
    state.layout_picker_selection %= len(specs)
    rows = max(1, height - 4)
    selected = state.layout_picker_selection
    start = min(max(0, selected - rows + 1), max(0, len(specs) - rows))
    visible = specs[start:start + rows]
    header = "layouts | Up/Down select | Enter switch | Esc close"
    divider = "-" * min(width, max(8, len(header)))
    lines = [header, divider, "Current: " + state.layout_name]
    for index, spec in enumerate(visible, start=start):
        marker = ">" if index == selected else " "
        active = "*" if spec.name == state.layout_name else " "
        lines.append(
            f"{marker}{active} {spec.name.ljust(18)} {_short(spec.description, max(20, width - 24))}"
        )
    lines.append(divider)
    return "\n".join(lines)

