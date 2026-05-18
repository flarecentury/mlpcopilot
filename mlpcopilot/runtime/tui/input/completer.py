"""Prompt completion for TUI slash commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator

from mlpcopilot.command.registry import list_commands
from mlpcopilot.runtime.approval import ApprovalManager
from mlpcopilot.runtime.tui.commands.command_runtime import _model_candidates
from mlpcopilot.runtime.tui.layouts.layout_registry import list_tui_layout_specs
from mlpcopilot.runtime.tui.overlays.approvals import (
    _APPROVAL_DECISION_COMMANDS,
    _approval_action_label,
    _approval_risk_level,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

def _make_tui_completer(config: Config, state: RuntimeTuiState | None = None) -> Any:
    from prompt_toolkit.completion import Completer, Completion

    class TuiCommandCompleter(Completer):
        def get_completions(self, document: Any, complete_event: Any) -> Iterator[Completion]:
            del complete_event
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            parts = text.split(maxsplit=1)
            if len(parts) == 1 and not text.endswith(" "):
                partial = parts[0].lower()
                for command in list_commands(surface="tui", config=config):
                    if state is not None and state.running and not command.available_during_task:
                        continue
                    if command.name.startswith(partial):
                        yield Completion(
                            command.name + (" " if command.takes_arg else ""),
                            start_position=-len(parts[0]),
                            display=command.name,
                            display_meta=command.description,
                        )
                return
            command_name = parts[0].lower()
            if command_name in _APPROVAL_DECISION_COMMANDS:
                partial_id = parts[1] if len(parts) > 1 else ""
                for record in ApprovalManager(
                    config.workspace_path,
                    session_key=state.active_session_id if state is not None else None,
                ).list_pending():
                    if record.approval_id.lower().startswith(partial_id.lower()):
                        yield Completion(
                            record.approval_id,
                            start_position=-len(partial_id),
                            display=record.approval_id,
                            display_meta=f"{_approval_risk_level(record)} {_approval_action_label(record)}",
                        )
                return
            if command_name == "/model":
                partial_model = parts[1] if len(parts) > 1 else ""
                for model in _model_candidates(config):
                    if model.lower().startswith(partial_model.lower()):
                        yield Completion(
                            model,
                            start_position=-len(partial_model),
                            display=model,
                            display_meta="model",
                        )
                return
            if command_name == "/layout":
                partial_layout = parts[1] if len(parts) > 1 else ""
                for layout in list_tui_layout_specs():
                    if layout.name.startswith(partial_layout.lower()):
                        yield Completion(
                            layout.name,
                            start_position=-len(partial_layout),
                            display=layout.name,
                            display_meta=layout.description,
                        )

    return TuiCommandCompleter()
