"""Footer and status-line rendering for the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text

from mlpcopilot.runtime.approval import ApprovalRecord
from mlpcopilot.runtime.tui.common import _tool_approval_policy, _write_policy
from mlpcopilot.runtime.tui.input.keymap import tui_action_key_label
from mlpcopilot.runtime.tui.state import RuntimeTuiState

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def _footer_help_line(config: Config, state: RuntimeTuiState, pending: list[ApprovalRecord]) -> Text:
    status = _footer_status(config, state, pending)
    quit_key = tui_action_key_label(config, "quit")
    if pending:
        return _footer_segments(
            [
                ("Left/Right", "select"),
                (f"Enter/{tui_action_key_label(config, 'approve')}", "approve"),
                (f"Esc/{tui_action_key_label(config, 'reject')}", "reject"),
                (tui_action_key_label(config, "changes"), "changes"),
            ],
            status=status,
            key_style="bold yellow",
            quit_key=quit_key,
        )
    if state.is_overlay_open("job_picker"):
        return _footer_segments(
            [
                ("Up/Down", "select"),
                ("Enter", "stop"),
                ("Esc", "close"),
            ],
            status=status,
            key_style="bold cyan",
            quit_key=quit_key,
        )
    if state.is_overlay_open("layout_picker"):
        return _footer_segments(
            [
                ("Up/Down", "select"),
                ("Enter", "switch"),
                ("Esc", "close"),
            ],
            status=status,
            key_style="bold cyan",
            quit_key=quit_key,
        )
    if state.is_overlay_open("model_picker"):
        return _footer_segments(
            [
                ("Up/Down", "select"),
                ("Enter", "switch"),
                ("Esc", "close"),
            ],
            status=status,
            key_style="bold cyan",
            quit_key=quit_key,
        )
    if state.is_overlay_open("pager") or state.is_overlay_open("tool_log_pager"):
        return _footer_segments(
            [
                ("Up/Down/PgUp/PgDn", "scroll"),
                ("Home/End", "jump"),
                ("Esc", "close"),
            ],
            status=status,
            key_style="bold cyan",
            quit_key=quit_key,
        )
    if state.running:
        return _footer_segments(
            [
                ("PgUp/PgDn", "chat"),
                (tui_action_key_label(config, "pager"), "pager"),
                (tui_action_key_label(config, "tool_log"), "tool log"),
                (tui_action_key_label(config, "jobs"), "jobs"),
                (tui_action_key_label(config, "layout"), "layout"),
                (tui_action_key_label(config, "model"), "model"),
                ("/status", ""),
                ("/stop", ""),
            ],
            status=status,
            key_style="bold cyan",
            quit_key=quit_key,
        )
    return _footer_segments(
        [
            ("Enter", "send"),
            ("Up/Down", "history"),
            ("PgUp/PgDn", "chat"),
            (tui_action_key_label(config, "pager"), "pager"),
            (tui_action_key_label(config, "tool_log"), "tool log"),
            (tui_action_key_label(config, "jobs"), "jobs"),
            (tui_action_key_label(config, "layout"), "layout"),
            (tui_action_key_label(config, "model"), "model"),
        ],
        status=status,
        key_style="bold cyan",
        quit_key=quit_key,
    )


def _footer_segments(
    items: list[tuple[str, str]],
    *,
    status: str,
    key_style: str,
    quit_key: str = "Ctrl-C",
) -> Text:
    text = Text()
    for idx, (key, label) in enumerate(items):
        if idx:
            text.append(" | ", style="dim")
        text.append(key, style=key_style)
        if label:
            text.append(f" {label}", style="white")
        if idx == 0:
            text.append("   ")
            text.append(status, style="bold green")
    text.append("   ")
    if quit_key != "-":
        text.append(quit_key, style="bold red")
        text.append(" quit", style="white")
    return text


def _footer_status(config: Config, state: RuntimeTuiState, pending: list[ApprovalRecord]) -> str:
    if pending:
        task = "approval"
    elif state.running:
        task = "running"
    else:
        task = "idle"
    if state.queued_count:
        task = f"{task}+{state.queued_count}"
    write_policy = _write_policy(config)
    tool_policy = _tool_approval_policy(config)
    mcp_allowlist = [
        item for item in getattr(config.tools, "approval_allowlist", [])
        if isinstance(item, str) and item.startswith("mcp_")
    ]
    mcp_policy = "gated+readonly" if not mcp_allowlist else f"gated+readonly+allowlist({len(mcp_allowlist)})"
    return f"{task} | read workspace | writes {write_policy} | tools {tool_policy} | mcp {mcp_policy}"
