"""Line-oriented fallback for non-terminal TUI execution."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from rich.console import Console

from mlpcopilot.runtime.tui.commands import _task_running_block_message
from mlpcopilot.runtime.tui.input.shell import is_tui_shell_command
from mlpcopilot.runtime.tui.layouts.render import render_tui
from mlpcopilot.runtime.tui.overlays.approvals import _approval_block_message
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


async def _run_line_fallback(
    config: Config,
    state: RuntimeTuiState,
    queue: asyncio.Queue[str],
    console: Console,
    worker_factory: Any,
) -> None:
    worker_task = asyncio.create_task(worker_factory())
    try:
        while True:
            console.clear()
            console.print(render_tui(config, state))
            try:
                user_input = console.input("").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_input in {"exit", "quit", "/exit", "/quit", ":q"}:
                break
            if not user_input:
                continue
            if is_tui_shell_command(user_input):
                queue.put_nowait(user_input)
                state.queued_count = queue.qsize()
                await queue.join()
                continue
            if blocked := _approval_block_message(config, user_input, session_id=state.active_session_id):
                state.add_chat("system", blocked)
                continue
            if blocked := _task_running_block_message(state, user_input):
                state.add_chat("system", blocked)
                continue
            queue.put_nowait(user_input)
            state.queued_count = queue.qsize()
            await queue.join()
    finally:
        worker_task.cancel()
        await asyncio.gather(worker_task, return_exceptions=True)
