"""Terminal workbench CLI command."""

from __future__ import annotations

import asyncio

import typer

from .common import _load_runtime_config, _sync_runtime_workspace, console


def tui(
    session_id: str = typer.Option("tui:default", "--session", "-s", help="Session ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Config file path"),
    once: bool = typer.Option(False, "--once", help="Render one read-only TUI snapshot and exit"),
):
    """Open the MLP Copilot terminal workbench."""
    from mlpcopilot.providers.factory import make_provider
    from mlpcopilot.runtime.tui import render_tui, run_tui

    config_obj = _load_runtime_config(config, workspace, quiet=True)
    _sync_runtime_workspace(config_obj, silent=True)

    if once:
        console.print(render_tui(config_obj))
        return

    provider = None
    provider_error = None
    try:
        provider = make_provider(config_obj)
    except ValueError as exc:
        provider_error = str(exc)
    asyncio.run(
        run_tui(
            config_obj,
            provider,
            session_id=session_id,
            console=console,
            provider_error=provider_error,
        )
    )


def register(app: typer.Typer) -> None:
    app.command()(tui)
