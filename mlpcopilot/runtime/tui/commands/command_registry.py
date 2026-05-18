"""TUI projection of the shared slash command registry."""

from __future__ import annotations

from mlpcopilot.command.registry import (
    SlashCommandSpec,
    format_command_help,
    get_command,
    list_commands,
    normalize_command_text,
)

TuiSlashCommand = SlashCommandSpec

_TUI_SLASH_COMMANDS: tuple[TuiSlashCommand, ...] = tuple(list_commands(surface="tui"))
_TUI_SLASH_COMMAND_BY_NAME = {command.name: command for command in _TUI_SLASH_COMMANDS}
_TUI_COMMAND_ALIASES = {
    alias.lstrip("/")
    for command in _TUI_SLASH_COMMANDS
    for alias in command.aliases
}
_TUI_COMMAND_ALIASES.update(command.name.lstrip("/") for command in _TUI_SLASH_COMMANDS)

_IMMEDIATE_LOCAL_COMMANDS = {
    command.name
    for command in _TUI_SLASH_COMMANDS
    if command.dispatch in {"approval", "local"} and command.name not in {"/stop", "/goal", "/plan", "/project"}
}


def get_tui_command(name: str) -> TuiSlashCommand | None:
    """Return command metadata by slash-prefixed name or alias."""
    command = get_command(name)
    if command is None or "tui" not in command.surfaces:
        return None
    return command


def normalize_tui_command_alias(raw: str) -> str:
    """Normalize accepted bare TUI command aliases to slash commands."""
    stripped = raw.strip()
    parts = stripped.split(maxsplit=1)
    if not parts:
        return stripped
    head = parts[0]
    if head.startswith("/"):
        return normalize_command_text(stripped)
    if head.lower() not in _TUI_COMMAND_ALIASES:
        return stripped
    tail = stripped[len(head):]
    return normalize_command_text(f"/{head}{tail}")


def tui_command_name(raw: str) -> str:
    normalized = normalize_tui_command_alias(raw.strip())
    return normalized.split(maxsplit=1)[0].lower() if normalized else ""


def is_tui_stop_command(raw: str) -> bool:
    return tui_command_name(raw) == "/stop"


def is_tui_approval_decision_command(raw: str) -> bool:
    return tui_command_name(raw) in {"/approve", "/reject", "/changes"}


def is_immediate_local_tui_command(raw: str) -> bool:
    return tui_command_name(raw) in _IMMEDIATE_LOCAL_COMMANDS


def task_running_block_message(running: bool, raw: str) -> str | None:
    if not running:
        return None
    command_name = tui_command_name(raw)
    if not command_name.startswith("/"):
        return None
    command = get_tui_command(command_name)
    if command is None or command.available_during_task:
        return None
    return f"{command.name} is disabled while a task is running."


def format_tui_help(config: object | None = None) -> str:
    """Build local TUI slash command help from the shared registry."""
    return format_command_help(surface="tui", config=config, title="MLP Copilot TUI commands:")
