"""Shared helpers for CLI command modules."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from mlpcopilot.config.schema import Config
from mlpcopilot.utils.helpers import sync_workspace_templates

console = Console()


def _sync_runtime_workspace(
    config: Config,
    workspace_path: Path | None = None,
    *,
    silent: bool = False,
) -> list[str]:
    """Sync the workspace schema required by the selected runtime profile."""
    from mlpcopilot.runtime.profiles import MLPCOPILOT_PROFILE
    from mlpcopilot.runtime.workspace import sync_mlpcopilot_workspace

    target = workspace_path or config.workspace_path
    if config.runtime_profile == MLPCOPILOT_PROFILE:
        return sync_mlpcopilot_workspace(target, silent=silent)
    if silent:
        return sync_workspace_templates(target, silent=True)
    return sync_workspace_templates(target)


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config.

    Routing is driven by ``ProviderSpec.backend`` in the registry.
    """
    from mlpcopilot.providers.factory import make_provider

    try:
        return make_provider(config)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc


def _load_runtime_config(
    config: str | None = None,
    workspace: str | None = None,
    *,
    quiet: bool = False,
) -> Config:
    """Load config and optionally override the active workspace."""
    from mlpcopilot.config.loader import load_config, resolve_config_env_vars, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        if not quiet:
            console.print(f"[dim]Using config: {config_path}[/dim]")

    try:
        loaded = resolve_config_env_vars(load_config(config_path))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
    """Hint users to remove obsolete keys from their config file."""
    import json

    from mlpcopilot.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        console.print(
            "[dim]Hint: `memoryWindow` in your config is no longer used "
            "and can be safely removed.[/dim]"
        )


def _migrate_cron_store(config: "Config") -> None:
    """One-time migration: move legacy global cron store into the workspace."""
    from mlpcopilot.config.paths import get_cron_dir

    legacy_path = get_cron_dir() / "jobs.json"
    new_path = config.workspace_path / "cron" / "jobs.json"
    if legacy_path.is_file() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.move(str(legacy_path), str(new_path))


def _missing_dirs(workspace: Path, dirs: tuple[str, ...]) -> list[str]:
    return [name for name in dirs if not (workspace / name).is_dir()]
