"""TUI model picker overlay rendering."""

from __future__ import annotations

from typing import Any

from mlpcopilot.runtime.tui.commands.command_runtime import _model_candidates
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.state import RuntimeTuiState


def model_picker_models(config: Any) -> list[str]:
    """Return model candidates for the active runtime config."""
    return _model_candidates(config)


def selected_model(state: RuntimeTuiState, models: list[str]) -> str | None:
    if not models:
        return None
    state.model_picker_selection %= len(models)
    return models[state.model_picker_selection]


def sync_model_picker_selection(state: RuntimeTuiState, config: Any) -> None:
    """Select the current model when the picker opens."""
    current = str(config.agents.defaults.model)
    for index, model in enumerate(model_picker_models(config)):
        if model == current:
            state.model_picker_selection = index
            return
    state.model_picker_selection = 0


def _render_model_picker_ansi(
    state: RuntimeTuiState,
    config: Any,
    *,
    width: int,
    height: int,
) -> str:
    models = model_picker_models(config)
    if not models:
        return "Models: none.\n\nEsc closes this picker."
    state.model_picker_selection %= len(models)
    rows = max(1, height - 4)
    selected = state.model_picker_selection
    start = min(max(0, selected - rows + 1), max(0, len(models) - rows))
    visible = models[start:start + rows]
    current = str(config.agents.defaults.model)
    header = "models | Up/Down select | Enter switch | Esc close"
    divider = "-" * min(width, max(8, len(header)))
    lines = [header, divider, "Current: " + current]
    for index, model in enumerate(visible, start=start):
        marker = ">" if index == selected else " "
        active = "*" if model == current else " "
        lines.append(f"{marker}{active} {_short(model, max(20, width - 4))}")
    lines.append(divider)
    return "\n".join(lines)

