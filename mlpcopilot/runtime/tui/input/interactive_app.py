"""Prompt-toolkit application assembly for the interactive TUI."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from mlpcopilot.runtime.tui.input.completer import _make_tui_completer
from mlpcopilot.runtime.tui.input.input_controller import TuiInputController
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


async def _run_interactive_app(
    config: Config,
    state: RuntimeTuiState,
    queue: asyncio.Queue[str],
    app_ref: dict[str, Any],
    active_turn_task: dict[str, asyncio.Task[Any] | None] | None = None,
    agent_loop: Any | None = None,
) -> None:
    from prompt_toolkit.application import Application
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.output import create_output
    from prompt_toolkit.styles import Style
    from prompt_toolkit.widgets import TextArea

    from mlpcopilot.config.paths import get_cli_history_path
    from mlpcopilot.runtime.tui.input.keymap import build_tui_key_bindings
    from mlpcopilot.runtime.tui.layouts.layout import build_tui_prompt_layout, tui_style_dict

    history_path = get_cli_history_path().with_name("tui_history")
    history_path.parent.mkdir(parents=True, exist_ok=True)

    controller = TuiInputController(
        config=config,
        state=state,
        queue=queue,
        app_ref=app_ref,
        active_turn_task=active_turn_task,
        agent_loop=agent_loop,
    )

    input_box = TextArea(
        multiline=False,
        height=1,
        wrap_lines=False,
        prompt="",
        history=FileHistory(str(history_path)),
        accept_handler=controller.accept_buffer,
        completer=_make_tui_completer(config, state),
        complete_while_typing=False,
    )
    controller.input_box = input_box
    key_bindings = build_tui_key_bindings(controller=controller, state=state, config=config)
    output = create_output()
    if hasattr(output, "enable_cpr"):
        output.enable_cpr = False
    app = Application(
        layout=build_tui_prompt_layout(config=config, state=state, input_box=input_box),
        key_bindings=key_bindings,
        full_screen=_tui_full_screen_enabled(),
        mouse_support=False,
        output=output,
        refresh_interval=0.25,
        style=Style.from_dict(tui_style_dict()),
    )
    app_ref["app"] = app
    await app.run_async()


def _tui_full_screen_enabled() -> bool:
    value = os.environ.get("MLPCOPILOT_TUI_FULLSCREEN", "").strip().lower()
    if value in {"0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    return not _is_vscode_terminal()


def _is_vscode_terminal() -> bool:
    return os.environ.get("TERM_PROGRAM", "").strip().lower() == "vscode"
