"""Blocking local shell execution for TUI bang commands."""

from __future__ import annotations

import subprocess
import time
from typing import Any

from mlpcopilot.runtime.tui.common import _sanitize_terminal_output_for_tui, _short
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry

_SHELL_OUTPUT_LIMIT = 12_000


def is_tui_shell_command(text: str) -> bool:
    """Return whether input should be consumed as a local TUI shell command."""
    return text.startswith("!")


def run_tui_shell_command(config: Any, state: RuntimeTuiState, raw_input: str) -> str:
    """Run a bang-prefixed command in bash, blocking the TUI worker until exit."""
    command = raw_input[1:].strip()
    if not command:
        return "Usage: !<bash command>"

    cwd = config.workspace_path
    entry = ToolLogEntry(name="shell", status="running", detail=_short(command, 160))
    state.tool_log.append(entry)
    state.trim_tool_log()

    try:
        completed = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        entry.status = "error"
        entry.duration_s = max(0.0, time.monotonic() - entry.started_at)
        entry.error = str(exc)
        return f"Shell command failed to start: {exc}"

    entry.duration_s = max(0.0, time.monotonic() - entry.started_at)
    entry.status = "ok" if completed.returncode == 0 else "error"
    if completed.returncode != 0:
        entry.error = f"exit code {completed.returncode}"

    stdout = _clean_shell_output(completed.stdout)
    stderr = _clean_shell_output(completed.stderr)
    return _format_shell_result(
        command=command,
        cwd=str(cwd),
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _clean_shell_output(value: str) -> str:
    return _truncate_shell_output(_sanitize_terminal_output_for_tui(value.strip()))


def _truncate_shell_output(value: str) -> str:
    if len(value) <= _SHELL_OUTPUT_LIMIT:
        return value
    omitted = len(value) - _SHELL_OUTPUT_LIMIT
    return f"{value[:_SHELL_OUTPUT_LIMIT]}\n... truncated {omitted} characters ..."


def _format_shell_result(
    *,
    command: str,
    cwd: str,
    returncode: int,
    stdout: str,
    stderr: str,
) -> str:
    status = "completed OK" if returncode == 0 else f"exited {returncode}"
    parts = [
        f"Shell command {status}: {command}",
        f"cwd: {cwd}",
    ]
    if stdout:
        parts.extend(["", "stdout:", stdout])
    if stderr:
        parts.extend(["", "stderr:", stderr])
    if not stdout and not stderr:
        parts.extend(["", "(no output)"])
    return "\n".join(parts)
