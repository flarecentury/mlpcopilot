"""Session goal/plan state tool for the agent."""

from __future__ import annotations

from typing import Any, Literal

from mlpcopilot.agent.tools.base import Tool
from mlpcopilot.agent.tools.session_context import current_session_key
from mlpcopilot.runtime.workstate import (
    apply_goal_command,
    apply_plan_command,
    apply_project_command,
    format_workstate_context,
    set_active_project,
)

WorkStateAction = Literal[
    "get",
    "set_goal",
    "clear_goal",
    "set_plan",
    "add_plan",
    "update_plan_status",
    "remove_plan",
    "clear_plan",
    "set_active_project",
    "clear_active_project",
]


class WorkStateTool(Tool):
    """Read and update the current session goal/plan."""

    def __init__(self, sessions: Any) -> None:
        self._sessions = sessions
        self._fallback_session_key = ""

    def set_context(self, channel: str, chat_id: str, session_key: str | None = None) -> None:
        self._fallback_session_key = session_key or f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "workstate"

    @property
    def description(self) -> str:
        return (
            "Read or update the current session goal and plan. "
            "It can also set or clear the active MLP project/run pointer used "
            "as runtime context for MCP calls. "
            "Use this whenever the user asks to set, clear, show, add to, remove from, "
            "or mark items done/in-progress/pending in the goal or plan. "
            "Also use it when a new substantial task has a clear goal, plan, or active "
            "project/run so future turns stay aligned; ask a focused question first "
            "when the goal is still ambiguous. "
            "Do not merely say the plan changed: call this tool so the Companion panel "
            "and future context are updated. When all plan items are completed, there is "
            "no current active plan and the Companion plan line should show '-'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get",
                        "set_goal",
                        "clear_goal",
                        "set_plan",
                        "add_plan",
                        "update_plan_status",
                        "remove_plan",
                        "clear_plan",
                        "set_active_project",
                        "clear_active_project",
                    ],
                },
                "text": {
                    "type": "string",
                    "description": "Goal text, full plan text, or plan item text depending on action.",
                },
                "index": {
                    "type": "integer",
                    "description": "1-based plan item index for update_plan_status/remove_plan.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "Target status for update_plan_status.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Active MLP project id for set_active_project.",
                },
                "run_id": {
                    "type": "string",
                    "description": "Active MLP run id for set_active_project.",
                },
                "backend": {
                    "type": "string",
                    "description": "Backend name such as dpgen for set_active_project.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Backend-native project path for MCP tools.",
                },
                "param_path": {
                    "type": "string",
                    "description": "Path to param.json, if known.",
                },
                "machine_path": {
                    "type": "string",
                    "description": "Path to machine.json, if known.",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: WorkStateAction,
        text: str | None = None,
        index: int | None = None,
        status: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        backend: str | None = None,
        project_path: str | None = None,
        param_path: str | None = None,
        machine_path: str | None = None,
        **_: Any,
    ) -> str:
        session_key = current_session_key(self._fallback_session_key)
        if not session_key:
            return "Error: no active session for workstate"
        session = self._sessions.get_or_create(session_key)

        if action == "get":
            result = format_workstate_context(session) or "Current Goal: none\nCurrent Plan: none"
        elif action == "set_goal":
            result = apply_goal_command(session, text or "")
        elif action == "clear_goal":
            result = apply_goal_command(session, "clear")
        elif action == "set_plan":
            result = apply_plan_command(session, f"set {text or ''}".strip())
        elif action == "add_plan":
            result = apply_plan_command(session, f"add {text or ''}".strip())
        elif action == "update_plan_status":
            if index is None:
                return "Error: index is required for update_plan_status"
            command = _status_command(status)
            if command is None:
                return "Error: status must be pending, in_progress, or completed"
            result = apply_plan_command(session, f"{command} {index}")
        elif action == "remove_plan":
            if index is None:
                return "Error: index is required for remove_plan"
            result = apply_plan_command(session, f"remove {index}")
        elif action == "clear_plan":
            result = apply_plan_command(session, "clear")
        elif action == "set_active_project":
            if not project_id:
                return "Error: project_id is required for set_active_project"
            pointer = set_active_project(
                session,
                project_id=project_id,
                run_id=run_id or "",
                backend=backend or "",
                project_path=project_path or "",
                param_path=param_path or "",
                machine_path=machine_path or "",
            )
            result = "Active project set:\n" + "\n".join(
                f"{key}: {value}" for key, value in pointer.to_dict().items()
            )
        elif action == "clear_active_project":
            result = apply_project_command(session, "clear")
        else:
            return f"Error: unknown workstate action {action}"

        self._sessions.save(session)
        current = format_workstate_context(session) or "Current Goal: none\nCurrent Plan: none"
        return f"{result}\n\n{current}"


def _status_command(status: str | None) -> str | None:
    if status == "completed":
        return "done"
    if status == "in_progress":
        return "doing"
    if status == "pending":
        return "pending"
    return None
