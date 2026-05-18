"""CLI command wiring for MLP Copilot."""

from __future__ import annotations

import os
import sys
from contextlib import suppress

import typer

from mlpcopilot import __version__
from mlpcopilot.cli import (
    channel_commands,
    chat_commands,
    onboard_commands,
    provider_commands,
    runtime_commands,
    tui_commands,
)
from mlpcopilot.cli.chat_commands import (
    SafeFileHistory,
    _flush_pending_tty_input,
    _init_prompt_session,
    _is_exit_command,
    _make_console,
    _print_agent_response,
    _print_cli_progress_line,
    _print_interactive_line,
    _print_interactive_progress_line,
    _print_interactive_response,
    _read_interactive_input_async,
    _render_interactive_ansi,
    _response_renderable,
    _restore_terminal,
)
from mlpcopilot.cli.common import (
    _load_runtime_config,
    _make_provider,
    _migrate_cron_store,
    _missing_dirs,
    _sync_runtime_workspace,
    console,
)
from mlpcopilot.cli.onboard_commands import _merge_missing_defaults, _onboard_plugins

__all__ = [
    "SafeFileHistory",
    "_flush_pending_tty_input",
    "_init_prompt_session",
    "_is_exit_command",
    "_load_runtime_config",
    "_make_console",
    "_make_provider",
    "_merge_missing_defaults",
    "_migrate_cron_store",
    "_missing_dirs",
    "_onboard_plugins",
    "_print_agent_response",
    "_print_cli_progress_line",
    "_print_interactive_line",
    "_print_interactive_progress_line",
    "_print_interactive_response",
    "_read_interactive_input_async",
    "_render_interactive_ansi",
    "_response_renderable",
    "_restore_terminal",
    "_sync_runtime_workspace",
    "app",
]

# Force UTF-8 encoding for Windows console.
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        with suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    name="mlpcopilot",
    context_settings={"help_option_names": ["-h", "--help"]},
    help="MLP Copilot - MLP workflow runtime",
    no_args_is_help=True,
)


def version_callback(value: bool):
    if value:
        console.print(f"MLP Copilot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """MLP Copilot - MLP workflow runtime."""
    pass


onboard_commands.register(app)
chat_commands.register(app)
tui_commands.register(app)
runtime_commands.register(app)
channel_commands.register(app)
provider_commands.register(app)


if __name__ == "__main__":
    app()
