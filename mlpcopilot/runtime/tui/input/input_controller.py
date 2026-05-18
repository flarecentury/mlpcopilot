"""Input state and key action controller for the interactive TUI."""

from __future__ import annotations

import asyncio
from typing import Any

from mlpcopilot.runtime.tui.commands.command_registry import (
    get_tui_command,
    is_immediate_local_tui_command,
    is_tui_approval_decision_command,
    is_tui_stop_command,
    normalize_tui_command_alias,
    task_running_block_message,
)
from mlpcopilot.runtime.tui.input.input_buffer import (
    _accept_tui_buffer,
    _navigate_input_history,
)
from mlpcopilot.runtime.tui.input.input_pager import TuiPagerActions
from mlpcopilot.runtime.tui.input.input_pickers import TuiPickerActions
from mlpcopilot.runtime.tui.input.input_slash import TuiSlashMenuActions
from mlpcopilot.runtime.tui.overlays import active_tui_overlay_id
from mlpcopilot.runtime.tui.overlays.approvals import (
    _APPROVAL_ACTIONS,
    _approval_block_message,
    _first_pending_approval,
    _selected_approval_action,
)
from mlpcopilot.runtime.tui.overlays.slash_menu import input_text_before_cursor
from mlpcopilot.runtime.tui.state import RuntimeTuiState


class TuiInputController(TuiPagerActions, TuiSlashMenuActions, TuiPickerActions):
    """Own prompt input actions independent from prompt_toolkit wiring."""

    def __init__(
        self,
        *,
        config: Any,
        state: RuntimeTuiState,
        queue: Any,
        app_ref: dict[str, Any],
        active_turn_task: dict[str, Any] | None = None,
        agent_loop: Any | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.queue = queue
        self.app_ref = app_ref
        self.active_turn_task = active_turn_task
        self.agent_loop = agent_loop
        self.input_box: Any | None = None
        self.immediate_tasks: set[asyncio.Task[Any]] = set()

    def invalidate(self) -> None:
        app = self.app_ref.get("app")
        if app is not None:
            app.invalidate()

    def submit(self, text: str) -> None:
        raw = text.strip()
        if not raw:
            return
        if raw in {"exit", "quit", "/exit", "/quit", ":q"}:
            self.app_ref["app"].exit()
            return
        from mlpcopilot.runtime.tui.input.shell import is_tui_shell_command

        if is_tui_shell_command(raw):
            self.queue.put_nowait(raw)
            self.state.queued_count = self.queue.qsize()
            self.invalidate()
            return
        normalized = normalize_tui_command_alias(raw)
        if is_tui_stop_command(raw):
            if len(normalized.split(maxsplit=1)) > 1:
                from mlpcopilot.runtime.tui.commands.command_runtime import (
                    handle_tui_runtime_command,
                )
                from mlpcopilot.runtime.tui.views.logs import save_persisted_tool_log

                self.state.add_chat("user", raw)
                result = handle_tui_runtime_command(self.config, normalized, state=self.state)
                if result:
                    self.state.add_chat("system", result)
                if self.state.tool_log:
                    save_persisted_tool_log(
                        self.config.workspace_path,
                        self.state.tool_log,
                        session_id=self.state.active_session_id,
                    )
                self.invalidate()
                return
            self.state.add_chat("user", raw)
            task = self.active_turn_task.get("task") if self.active_turn_task is not None else None
            if task is not None and not task.done():
                task.cancel()
                marked = self.state.cancel_running_tool_entries()
                if marked:
                    from mlpcopilot.runtime.tui.views.logs import save_persisted_tool_log

                    save_persisted_tool_log(
                        self.config.workspace_path,
                        self.state.tool_log,
                        session_id=self.state.active_session_id,
                    )
                self.state.add_chat(
                    "system",
                    "Stop requested. Waiting for the current tool to terminate...",
                )
            else:
                marked = self.state.cancel_running_tool_entries("stale running entry cleared by /stop")
                if marked:
                    from mlpcopilot.runtime.tui.views.logs import save_persisted_tool_log

                    save_persisted_tool_log(
                        self.config.workspace_path,
                        self.state.tool_log,
                        session_id=self.state.active_session_id,
                    )
                    self.state.add_chat("system", f"No active task to stop. Marked {marked} running tool log entr{'y' if marked == 1 else 'ies'} as cancelled.")
                else:
                    self.state.add_chat("system", "No active task to stop.")
            self.invalidate()
            return
        if self.handle_immediate_approval_command(raw, normalized):
            return
        if blocked := _approval_block_message(self.config, raw, session_id=self.state.active_session_id):
            self.state.add_chat("system", blocked)
            self.invalidate()
            return
        if normalized == "/layout":
            self.state.add_chat("user", raw)
            self.open_layout_picker()
            return
        if normalized == "/model":
            if blocked := task_running_block_message(self.state.running, normalized):
                self.state.add_chat("system", blocked)
                self.invalidate()
                return
            self.state.add_chat("user", raw)
            self.open_model_picker()
            return
        if self.handle_immediate_local_command(raw, normalized):
            return
        if unknown := self.unknown_slash_message(normalized):
            self.state.add_chat("user", raw)
            self.state.add_chat("system", unknown)
            self.invalidate()
            return
        if blocked := task_running_block_message(self.state.running, raw):
            self.state.add_chat("system", blocked)
            self.invalidate()
            return
        self.queue.put_nowait(raw)
        self.state.queued_count = self.queue.qsize()
        self.invalidate()

    def has_pending_approval(self) -> bool:
        return _first_pending_approval(self.config, session_id=self.state.active_session_id) is not None

    def active_overlay_id(self) -> str | None:
        return active_tui_overlay_id(
            approval_pending=self.has_pending_approval(),
            pager_open=self.state.is_overlay_open("pager"),
            tool_log_pager_open=self.state.is_overlay_open("tool_log_pager"),
            overlay_stack=self.state.overlay_stack,
        )

    def overlay_is(self, overlay_id: str) -> bool:
        return self.active_overlay_id() == overlay_id

    def handle_immediate_approval_command(self, raw: str, normalized: str) -> bool:
        if not is_tui_approval_decision_command(normalized):
            return False
        if self.agent_loop is None:
            return False
        self.state.add_chat("user", raw)
        task = asyncio.create_task(self._run_immediate_approval_command(normalized))
        self.immediate_tasks.add(task)
        task.add_done_callback(self.immediate_tasks.discard)
        self.invalidate()
        return True

    async def _run_immediate_approval_command(self, normalized: str) -> None:
        from mlpcopilot.runtime.tui.commands.command_approvals import (
            _handle_tui_approval_command,
            approval_continuation_prompt,
            approval_continuation_result,
        )
        from mlpcopilot.runtime.tui.overlays.approvals import _first_pending_approval
        from mlpcopilot.runtime.tui.queue_items import TuiQueuedInput
        from mlpcopilot.runtime.tui.views.logs import save_persisted_tool_log

        result = await _handle_tui_approval_command(
            self.config,
            self.agent_loop,
            normalized,
            self.state,
        )
        if result:
            self.state.add_chat("system", result)
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
        save_persisted_tool_log(
            self.config.workspace_path,
            self.state.tool_log,
            session_id=self.state.active_session_id,
        )
        self.invalidate()

    def handle_immediate_local_command(self, raw: str, normalized: str) -> bool:
        if not is_immediate_local_tui_command(normalized):
            return False
        if blocked := task_running_block_message(self.state.running, normalized):
            self.state.add_chat("system", blocked)
            self.invalidate()
            return True
        from mlpcopilot.runtime.tui.commands.command_runtime import handle_tui_runtime_command

        result = handle_tui_runtime_command(
            self.config,
            normalized,
            agent_loop=self.agent_loop,
            state=self.state,
            session_id=self.state.active_session_id,
        )
        if result is None:
            return False
        self.state.add_chat("user", raw)
        self.state.add_chat("system", result)
        self.invalidate()
        return True

    def unknown_slash_message(self, normalized: str) -> str | None:
        if not normalized.startswith("/"):
            return None
        command_name = normalized.split(maxsplit=1)[0].lower()
        if get_tui_command(command_name) is not None:
            return None
        return f"Unknown command: {command_name}. Use /help."

    def submit_approval_decision(self, action: str) -> None:
        record = _first_pending_approval(self.config, session_id=self.state.active_session_id)
        if record is None:
            self.state.add_chat("system", "No pending approvals.")
            self.invalidate()
            return
        self.submit(f"/{action} {record.approval_id}")
        buffer = getattr(self.input_box, "buffer", None)
        if buffer is not None:
            buffer.reset()

    def submit_selected_approval_decision(self) -> None:
        self.submit_approval_decision(_selected_approval_action(self.state.approval_selection))

    def accept_buffer(self, buffer: Any) -> bool:
        return _accept_tui_buffer(
            buffer,
            submit=self.submit,
            has_pending_approval=self.has_pending_approval,
            submit_selected_approval_decision=self.submit_selected_approval_decision,
        )

    def move_approval_selection(self, delta: int) -> None:
        if not self.has_pending_approval():
            return
        self.state.approval_selection = (
            self.state.approval_selection + delta
        ) % len(_APPROVAL_ACTIONS)
        self.invalidate()

    def navigate_history(self, buffer: Any, delta: int) -> None:
        navigating_completion = getattr(buffer, "complete_state", None) is not None
        _navigate_input_history(buffer, delta)
        if not navigating_completion:
            self.state.slash_menu_suppressed_text = input_text_before_cursor(buffer)
            self.state.slash_menu_selection = 0
            self.invalidate()

    def complete(self, buffer: Any) -> None:
        from prompt_toolkit.completion import CompleteEvent

        if buffer.complete_state:
            current = buffer.complete_state.current_completion
            if current is not None:
                buffer.apply_completion(current)
                return
        buffer.start_completion(
            select_first=True,
            complete_event=CompleteEvent(completion_requested=True),
        )
        if buffer.complete_state and buffer.complete_state.current_completion:
            buffer.apply_completion(buffer.complete_state.current_completion)
