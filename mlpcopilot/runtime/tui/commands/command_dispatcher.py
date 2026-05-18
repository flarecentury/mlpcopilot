"""TUI command dispatch with explicit local/approval/agent boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mlpcopilot.command.registry import command_visible
from mlpcopilot.runtime.tui.commands.command_approvals import _handle_tui_approval_command
from mlpcopilot.runtime.tui.commands.command_registry import (
    get_tui_command,
    normalize_tui_command_alias,
)
from mlpcopilot.runtime.tui.commands.command_runtime import handle_tui_runtime_command
from mlpcopilot.runtime.tui.state import RuntimeTuiState
from mlpcopilot.runtime.workstate import (
    apply_goal_command,
    apply_plan_command,
    apply_project_command,
    refresh_workstate_summary_for_session,
)

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


async def dispatch_tui_command(
    config: Config,
    agent_loop: Any,
    session_id: str,
    raw: str,
    state: RuntimeTuiState | None = None,
) -> str | None:
    """Dispatch TUI commands through local handlers or the shared slash router."""
    stripped = normalize_tui_command_alias(raw.strip())
    if not stripped:
        return None
    if result := await _handle_tui_approval_command(config, agent_loop, stripped, state):
        return result
    if result := _handle_tui_project_command(config, agent_loop, session_id, stripped):
        return result
    if result := await _handle_tui_workstate_command(agent_loop, session_id, stripped):
        return result
    if result := handle_tui_runtime_command(config, stripped, agent_loop, state, session_id):
        return result
    if not stripped.startswith("/"):
        return None

    command_name = stripped.split(maxsplit=1)[0].lower()
    command = get_tui_command(command_name)
    if command is None or not command_visible(command, surface="tui", config=config):
        return f"Unknown command: {command_name}. Use /help."
    if command.dispatch == "local":
        return f"Command {command.name} is registered as local but has no handler."
    if command.dispatch == "agent":
        return None

    from mlpcopilot.bus.events import InboundMessage
    from mlpcopilot.command.router import CommandContext

    msg = InboundMessage(
        channel="cli",
        sender_id="tui",
        chat_id=session_id.split(":", 1)[-1],
        content=stripped,
        session_key_override=session_id,
    )
    session = agent_loop.sessions.get_or_create(session_id)
    ctx = CommandContext(msg=msg, session=session, key=session_id, raw=stripped, loop=agent_loop)
    if agent_loop.commands.is_priority(stripped):
        outbound = await agent_loop.commands.dispatch_priority(ctx)
    elif agent_loop.commands.is_dispatchable_command(stripped):
        outbound = await agent_loop.commands.dispatch(ctx)
    else:
        return f"Unknown command: {command_name}. Use /help."
    return outbound.content if outbound else None


def _handle_tui_project_command(
    config: Config,
    agent_loop: Any,
    session_id: str,
    stripped: str,
) -> str | None:
    parts = stripped.split(maxsplit=1)
    if not parts or parts[0].lower() != "/project":
        return None
    args = parts[1] if len(parts) > 1 else ""
    session = agent_loop.sessions.get_or_create(session_id)
    try:
        result = apply_project_command(session, args, workspace=config.workspace_path)
    except Exception as exc:
        result = f"Error: {exc}"
    agent_loop.sessions.save(session)
    return result


async def _handle_tui_workstate_command(agent_loop: Any, session_id: str, stripped: str) -> str | None:
    parts = stripped.split(maxsplit=1)
    if not parts or parts[0].lower() not in {"/goal", "/plan"}:
        return None
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    session = agent_loop.sessions.get_or_create(session_id)
    result = apply_goal_command(session, args) if command == "/goal" else apply_plan_command(session, args)
    if args.strip():
        _schedule_tui_workstate_summary_refresh(
            agent_loop,
            session_id,
            "goal" if command == "/goal" else "plan",
        )
    agent_loop.sessions.save(session)
    if args.strip():
        return f"{result}\nSummary: AI refresh running in background."
    return result


def _schedule_tui_workstate_summary_refresh(
    agent_loop: Any,
    session_id: str,
    target: str,
) -> None:
    coro = refresh_workstate_summary_for_session(
        agent_loop.sessions,
        session_id,
        provider=getattr(agent_loop, "provider", None),
        model=getattr(agent_loop, "model", None),
        target=target,  # type: ignore[arg-type]
    )
    scheduler = getattr(agent_loop, "_schedule_background", None)
    if callable(scheduler):
        scheduler(coro)
    else:
        import asyncio
        asyncio.create_task(coro)
