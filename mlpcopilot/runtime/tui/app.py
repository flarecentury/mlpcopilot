"""Interactive TUI application wiring."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from rich.console import Console

from mlpcopilot.providers.base import LLMProvider
from mlpcopilot.runtime.jobs import JobStore
from mlpcopilot.runtime.tui.controller import TuiRuntimeController
from mlpcopilot.runtime.tui.input.interactive_app import _run_interactive_app
from mlpcopilot.runtime.tui.input.line_fallback import _run_line_fallback
from mlpcopilot.runtime.tui.runtime_factory import build_tui_agent_loop
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.tui.stores.state_store import apply_persisted_tui_state
from mlpcopilot.runtime.tui.views.logs import (
    capture_tui_logs,
    load_persisted_tool_log,
)
from mlpcopilot.runtime.tui.views.session_view import _load_session_chat

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


async def run_tui(
    config: Config,
    provider: LLMProvider | None,
    *,
    session_id: str = "tui:default",
    console: Console | None = None,
    provider_error: str | None = None,
) -> None:
    """Run a minimal interactive MLP Copilot workbench."""
    console = console or Console()
    with suppress(OSError):
        JobStore(config.workspace_path).reconcile_stale(mark_missing_pid=True)
    state = RuntimeTuiState()
    state.root_session_id = session_id
    state.active_session_id = session_id
    apply_persisted_tui_state(
        state,
        config.workspace_path,
        root_session_id=session_id,
    )
    state.tool_log = load_persisted_tool_log(
        config.workspace_path,
        session_id=state.active_session_id,
        fallback_to_global=False,
    )
    runtime = build_tui_agent_loop(config=config, provider=provider, provider_error=provider_error)
    agent_loop = runtime.agent_loop
    state.mcp_status = agent_loop.mcp_status()
    _load_session_chat(state, agent_loop.sessions.get_or_create(state.active_session_id))

    queue: asyncio.Queue[str] = asyncio.Queue()
    app_ref: dict[str, Any] = {}
    controller = TuiRuntimeController(
        config=config,
        state=state,
        agent_loop=agent_loop,
        session_id=session_id,
        queue=queue,
        app_ref=app_ref,
    )

    if runtime.provider_notice and runtime.provider_notice_reason:
        controller.record_provider_notice(
            reason=runtime.provider_notice_reason,
            content=runtime.provider_notice,
        )

    try:
        with capture_tui_logs(state):
            if console.is_terminal:
                worker_task = asyncio.create_task(controller.run_worker())
                try:
                    await _run_interactive_app(
                        config,
                        state,
                        queue,
                        app_ref,
                        controller.active_turn_task,
                        agent_loop,
                    )
                finally:
                    worker_task.cancel()
                    await asyncio.gather(worker_task, return_exceptions=True)
            else:
                await _run_line_fallback(config, state, queue, console, controller.run_worker)
    finally:
        await agent_loop.close_mcp()
