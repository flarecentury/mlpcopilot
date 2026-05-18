"""Unified slash command metadata for runtime surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CommandDispatch = Literal["approval", "agent", "local", "session", "shared"]
CommandSurface = Literal["gateway", "tui"]


@dataclass(frozen=True, slots=True)
class SlashCommandSpec:
    """Surface-independent slash command declaration."""

    name: str
    description: str
    args: str = ""
    category: str = "runtime"
    dispatch: CommandDispatch = "shared"
    surfaces: frozenset[CommandSurface] = frozenset({"gateway", "tui"})
    aliases: tuple[str, ...] = ()
    priority: bool = False
    takes_arg: bool = False
    available_during_task: bool = True
    hidden_by_default: frozenset[CommandSurface] = frozenset()

    @property
    def usage(self) -> str:
        return f"{self.name} {self.args}".strip()

    @property
    def supports_inline_args(self) -> bool:
        return self.takes_arg


RUNTIME_SLASH_COMMANDS: tuple[SlashCommandSpec, ...] = (
    SlashCommandSpec(
        "/approve",
        "Approve a pending decision",
        args="<id> [reason]",
        dispatch="approval",
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/reject",
        "Reject a pending decision",
        args="<id> [reason]",
        dispatch="approval",
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/changes",
        "Request changes for a pending decision",
        args="<id> [reason]",
        dispatch="approval",
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/approvals",
        "Show pending approvals",
        args="[decisions]",
        dispatch="local",
        takes_arg=True,
    ),
    SlashCommandSpec("/help", "Show commands", dispatch="local"),
    SlashCommandSpec("/status", "Show runtime status", dispatch="local", priority=True),
    SlashCommandSpec("/new", "Start a new conversation", dispatch="session", available_during_task=False),
    SlashCommandSpec("/stop", "Stop the current task", dispatch="local", priority=True),
    SlashCommandSpec("/restart", "Restart the bot process", dispatch="shared", priority=True),
    SlashCommandSpec(
        "/model",
        "Show or switch model",
        args="[model]",
        dispatch="local",
        takes_arg=True,
        available_during_task=False,
    ),
    SlashCommandSpec(
        "/history",
        "Show recent conversation messages",
        args="[n]",
        dispatch="local",
        takes_arg=True,
    ),
    SlashCommandSpec("/dream", "Manually trigger Dream consolidation", dispatch="shared"),
    SlashCommandSpec(
        "/dream-log",
        "Show Dream memory changes",
        args="[sha]",
        dispatch="shared",
        takes_arg=True,
        aliases=("/dream_log",),
    ),
    SlashCommandSpec(
        "/dream-restore",
        "Restore Dream memory version",
        args="[sha]",
        dispatch="shared",
        takes_arg=True,
        aliases=("/dream_restore",),
    ),
    SlashCommandSpec("/runs", "Show recent run manifests", dispatch="local"),
    SlashCommandSpec(
        "/artifacts",
        "Show artifact references for a run",
        args="<run_id>",
        dispatch="local",
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/jobs",
        "Show recent runtime jobs",
        dispatch="local",
        surfaces=frozenset({"tui"}),
        aliases=("/ps",),
    ),
    SlashCommandSpec(
        "/tool-log",
        "Show recent tool log entries",
        dispatch="local",
        surfaces=frozenset({"tui"}),
        aliases=("/toollog",),
    ),
    SlashCommandSpec(
        "/raw",
        "Show a persisted raw tool result",
        args="<selector>",
        dispatch="local",
        surfaces=frozenset({"tui"}),
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/layout",
        "Show or switch TUI layout",
        args="[name]",
        dispatch="local",
        surfaces=frozenset({"tui"}),
        takes_arg=True,
    ),
    SlashCommandSpec(
        "/profile",
        "Show active runtime profile",
        dispatch="local",
        surfaces=frozenset({"tui"}),
        aliases=("/profiles",),
    ),
    SlashCommandSpec(
        "/plan",
        "Show or update the current task plan",
        args="[set|add|done|doing|pending|remove|clear] [text|n]",
        dispatch="local",
        surfaces=frozenset({"gateway", "tui"}),
        takes_arg=True,
        available_during_task=False,
    ),
    SlashCommandSpec(
        "/goal",
        "Show or set the current task goal",
        args="[text|clear]",
        dispatch="local",
        surfaces=frozenset({"gateway", "tui"}),
        takes_arg=True,
        available_during_task=False,
    ),
    SlashCommandSpec(
        "/project",
        "Show or set active MLP project/run pointer",
        args="[set] <project_id> [run_id] | clear",
        dispatch="local",
        surfaces=frozenset({"gateway", "tui"}),
        takes_arg=True,
        available_during_task=False,
    ),
    SlashCommandSpec(
        "/memory-audit",
        "Scan durable memory for likely stale runtime facts",
        dispatch="local",
        surfaces=frozenset({"gateway", "tui"}),
        aliases=("/memory_audit",),
    ),
)


_COMMAND_BY_NAME = {command.name: command for command in RUNTIME_SLASH_COMMANDS}
_ALIAS_TO_COMMAND = {
    alias: command.name
    for command in RUNTIME_SLASH_COMMANDS
    for alias in command.aliases
}


def normalize_command_name(name: str) -> str:
    """Normalize aliases to canonical slash command names."""
    lowered = name.strip().lower()
    if not lowered:
        return lowered
    if not lowered.startswith("/"):
        lowered = f"/{lowered}"
    return _ALIAS_TO_COMMAND.get(lowered, lowered)


def get_command(name: str) -> SlashCommandSpec | None:
    """Return a command spec by canonical name or alias."""
    return _COMMAND_BY_NAME.get(normalize_command_name(name))


def normalize_command_text(raw: str) -> str:
    """Normalize a full slash command line, preserving arguments."""
    stripped = raw.strip()
    parts = stripped.split(maxsplit=1)
    if not parts:
        return stripped
    head = normalize_command_name(parts[0])
    if not head.startswith("/"):
        return stripped
    return f"{head} {parts[1]}".strip() if len(parts) > 1 else head


def _surface_policy(config: object | None, surface: CommandSurface) -> tuple[set[str], set[str] | None]:
    commands = getattr(config, "commands", None)
    surface_config = getattr(commands, surface, None) if commands is not None else None
    hidden = {
        normalize_command_name(item)
        for item in getattr(surface_config, "hide", [])
        if isinstance(item, str)
    }
    raw_show = getattr(surface_config, "show", None)
    shown = None
    if raw_show is not None:
        shown = {normalize_command_name(item) for item in raw_show if isinstance(item, str)}
    return hidden, shown


def command_visible(
    command: SlashCommandSpec,
    *,
    surface: CommandSurface,
    config: object | None = None,
) -> bool:
    """Return whether a command should be displayed/accepted on a surface."""
    if surface not in command.surfaces:
        return False
    hidden, shown = _surface_policy(config, surface)
    if shown is not None and command.name not in shown:
        return False
    if command.name in hidden:
        return False
    if surface in command.hidden_by_default and (shown is None or command.name not in shown):
        return False
    return True


def list_commands(
    *,
    surface: CommandSurface,
    config: object | None = None,
    include_hidden: bool = False,
) -> list[SlashCommandSpec]:
    """List command specs for a surface in presentation order."""
    if include_hidden:
        return [command for command in RUNTIME_SLASH_COMMANDS if surface in command.surfaces]
    return [
        command
        for command in RUNTIME_SLASH_COMMANDS
        if command_visible(command, surface=surface, config=config)
    ]


def format_command_help(
    *,
    surface: CommandSurface,
    config: object | None = None,
    title: str = "MLP Copilot commands:",
) -> str:
    """Build help text from visible command specs."""
    lines = [title]
    for command in list_commands(surface=surface, config=config):
        lines.append(f"{command.usage} - {command.description}")
    return "\n".join(lines)
