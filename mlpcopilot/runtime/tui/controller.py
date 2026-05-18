"""Runtime controller for TUI queue processing and agent turn lifecycle."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from mlpcopilot.runtime.tui.commands import dispatch_tui_command
from mlpcopilot.runtime.tui.commands.command_approvals import (
    approval_continuation_prompt,
    approval_continuation_result,
)
from mlpcopilot.runtime.tui.common import _short
from mlpcopilot.runtime.tui.input.shell import is_tui_shell_command, run_tui_shell_command
from mlpcopilot.runtime.tui.overlays.approvals import _first_pending_approval
from mlpcopilot.runtime.tui.queue_items import TuiQueuedInput
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry
from mlpcopilot.runtime.tui.stores.state_store import save_tui_state
from mlpcopilot.runtime.tui.views.logs import (
    load_persisted_tool_log,
    persist_raw_tool_event_results,
    save_persisted_tool_log,
)


def _is_new_session_command(raw: str) -> bool:
    parts = raw.strip().split(maxsplit=1)
    return bool(parts and parts[0].lower() in {"/new", "new"})


def _reset_tui_session_view(state: RuntimeTuiState) -> None:
    state.chat.clear()
    state.tool_log.clear()
    state.approval_continuation_results.clear()
    state.chat_scroll = 0
    state.approval_selection = 0
    state.close_all_overlays()
    state.pager_scroll = 0
    state.pager_message_index = None
    state.tool_log_pager_scroll = 0
    state.slash_menu_selection = 0
    state.slash_menu_suppressed_text = ""
    state.job_picker_selection = 0
    state.layout_picker_selection = 0
    state.model_picker_selection = 0


def _new_tui_session_id() -> str:
    return f"tui:{time.time_ns()}"


def _resolve_numeric_ask_reply(state: RuntimeTuiState, raw: str) -> str:
    """Map a bare numeric reply to the latest assistant option text."""
    text = raw.strip()
    if not re.fullmatch(r"\d{1,2}", text):
        return raw
    selected = int(text)
    if selected <= 0:
        return raw
    for message in reversed(state.chat):
        if message.role != "assistant":
            continue
        options: dict[int, str] = {}
        for line in message.content.splitlines():
            match = re.match(r"^\s*(\d{1,2})[\.)]?\s+(.+?)\s*$", line)
            if match:
                options[int(match.group(1))] = match.group(2)
        if selected in options:
            return options[selected]
        break
    return raw


class TuiRuntimeController:
    """Own the TUI worker, active task, streaming, and tool log persistence."""

    def __init__(
        self,
        *,
        config: Any,
        state: RuntimeTuiState,
        agent_loop: Any,
        session_id: str,
        queue: asyncio.Queue[str],
        app_ref: dict[str, Any],
    ) -> None:
        self.config = config
        self.state = state
        self.agent_loop = agent_loop
        self.session_id = state.active_session_id or session_id
        self.queue = queue
        self.app_ref = app_ref
        self.active_turn_task: dict[str, asyncio.Task[Any] | None] = {"task": None}

    def invalidate(self) -> None:
        app = self.app_ref.get("app")
        if app is not None:
            app.invalidate()

    def persist_tool_log(self) -> None:
        save_persisted_tool_log(
            self.config.workspace_path,
            self.state.tool_log,
            session_id=self.state.active_session_id,
        )

    def record_provider_notice(self, *, reason: str, content: str) -> None:
        self.state.add_chat("system", content)
        self.state.record_log("warning", "mlpcopilot.runtime.tui", reason)
        self.persist_tool_log()

    async def progress(
        self,
        content: str,
        *,
        tool_hint: bool = False,
        tool_events: list[dict[str, Any]] | None = None,
    ) -> None:
        if tool_events:
            tool_events = persist_raw_tool_event_results(self.config.workspace_path, tool_events)
            self.state.record_tool_events(tool_events)
            self.persist_tool_log()
        elif tool_hint and content.strip():
            self.state.tool_log.append(
                ToolLogEntry(name="agent", status="progress", detail=_short(content, 160))
            )
            self.state.trim_tool_log()
            self.persist_tool_log()
        self.invalidate()

    async def await_active_task(self, task: asyncio.Task[Any]) -> tuple[bool, Any]:
        self.active_turn_task["task"] = task
        try:
            return False, await task
        except asyncio.CancelledError:
            if asyncio.current_task() and asyncio.current_task().cancelling():
                raise
            marked = self.state.cancel_running_tool_entries()
            if marked:
                self.persist_tool_log()
            self.state.add_chat("system", "Task stopped.")
            return True, None
        finally:
            if self.active_turn_task.get("task") is task:
                self.active_turn_task["task"] = None

    async def run_worker(self) -> None:
        while True:
            queued_input = await self.queue.get()
            if isinstance(queued_input, TuiQueuedInput):
                raw_user_input = queued_input.content
                show_user_message = queued_input.show_user_message
                input_metadata = dict(queued_input.metadata)
            else:
                raw_user_input = str(queued_input)
                show_user_message = True
                input_metadata = {}
            user_input = _resolve_numeric_ask_reply(self.state, raw_user_input)
            stream_message_index: int | None = None
            stream_had_content = False
            self.state.queued_count = self.queue.qsize()
            self.state.running = True
            self.state.current_input = user_input
            if show_user_message:
                self.state.add_chat("user", user_input)
            self.invalidate()
            try:
                async def _stream(delta: str) -> None:
                    nonlocal stream_message_index, stream_had_content
                    if not delta:
                        return
                    stream_message_index = self.state.append_chat_stream(
                        stream_message_index,
                        delta,
                    )
                    stream_had_content = True
                    self.invalidate()

                async def _stream_end(*, resuming: bool = False) -> None:
                    nonlocal stream_message_index
                    stream_message_index = None
                    self.invalidate()

                if is_tui_shell_command(user_input):
                    result = run_tui_shell_command(self.config, self.state, user_input)
                    self.state.add_chat("system", result)
                    self.persist_tool_log()
                    continue

                command_cancelled, result = await self.await_active_task(
                    asyncio.create_task(
                        dispatch_tui_command(
                            self.config,
                            self.agent_loop,
                            self.state.active_session_id,
                            user_input,
                            self.state,
                        )
                    )
                )
                if command_cancelled:
                    continue
                if result:
                    if _is_new_session_command(user_input):
                        _reset_tui_session_view(self.state)
                        self.session_id = _new_tui_session_id()
                        self.state.active_session_id = self.session_id
                        save_tui_state(self.config.workspace_path, self.state)
                        self.state.tool_log = load_persisted_tool_log(
                            self.config.workspace_path,
                            session_id=self.state.active_session_id,
                            fallback_to_global=False,
                        )
                    self.state.add_chat("system", result)
                    self.persist_tool_log()
                    if item := approval_continuation_result(result):
                        self.state.approval_continuation_results.append(item)
                    pending_approval = _first_pending_approval(
                        self.config,
                        session_id=self.state.active_session_id,
                    )
                    if (
                        pending_approval is None
                        and (followup := approval_continuation_prompt(
                            self.state.approval_continuation_results
                        ))
                    ):
                        self.state.approval_continuation_results.clear()
                        self.queue.put_nowait(
                            TuiQueuedInput(
                                content=followup,
                                show_user_message=False,
                                source="approval_continuation",
                                metadata={
                                    "_skip_user_persist": True,
                                    "_tui_internal": "approval_continuation",
                                },
                            )
                        )
                        self.state.queued_count = self.queue.qsize()
                    continue
                turn_task = asyncio.create_task(
                    self.agent_loop.process_direct(
                        user_input,
                        session_key=self.state.active_session_id,
                        channel="cli",
                        chat_id=self.state.active_session_id.split(":", 1)[-1],
                        on_progress=self.progress,
                        on_stream=_stream,
                        on_stream_end=_stream_end,
                        metadata=input_metadata,
                    )
                )
                turn_cancelled, response = await self.await_active_task(turn_task)
                if turn_cancelled:
                    continue
                self.state.mcp_status = self.agent_loop.mcp_status()
                if response and response.content:
                    if response.metadata.get("_streamed"):
                        if not stream_had_content:
                            self.state.add_chat("assistant", response.content)
                    else:
                        self.state.add_chat("assistant", response.content)
            finally:
                self.queue.task_done()
                self.state.running = not self.queue.empty()
                self.state.queued_count = self.queue.qsize()
                self.state.current_input = ""
                self.invalidate()
