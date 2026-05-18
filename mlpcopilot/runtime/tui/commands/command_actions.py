"""State-changing local slash command actions for the TUI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from mlpcopilot.runtime.jobs import JobRecord, JobStore
from mlpcopilot.runtime.tui.layouts.layout_registry import (
    format_tui_layouts,
    get_tui_layout_spec,
    normalize_tui_layout_name,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState, ToolLogEntry

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config


def stop_tui_job(config: Config, job_id: str, state: RuntimeTuiState | None = None) -> str:
    record, message = JobStore(config.workspace_path).stop(job_id.strip())
    if state is not None:
        _record_job_stop_tool_log(state, record, job_id.strip(), message)
    return message


def _record_job_stop_tool_log(
    state: RuntimeTuiState,
    record: JobRecord | None,
    job_id: str,
    message: str,
) -> None:
    if record is None:
        state.tool_log.append(
            ToolLogEntry(
                name="job",
                status="error",
                detail=job_id,
                error=message,
            )
        )
    else:
        state.tool_log.append(
            ToolLogEntry(
                name=record.kind or "job",
                status=record.status,
                detail=record.command or record.job_id,
            )
        )
    state.trim_tool_log()


def switch_tui_model(config: Config, agent_loop: Any, model: str) -> str:
    """Switch the in-process TUI runtime model without writing the config file."""
    new_model = model.strip()
    if not new_model:
        return "Usage: /model <model>"
    old_model = config.agents.defaults.model
    if new_model == old_model:
        return f"Current model: {old_model}"

    from mlpcopilot.providers.factory import build_provider_snapshot

    updated = config.model_copy(deep=True)
    updated.agents.defaults.model = new_model
    try:
        snapshot = build_provider_snapshot(updated)
    except ValueError as exc:
        return f"Error: {exc}"

    apply_snapshot = getattr(agent_loop, "_apply_provider_snapshot", None)
    if apply_snapshot is None:
        return "Error: active runtime cannot switch models"
    apply_snapshot(snapshot)
    config.agents.defaults.model = new_model
    return f"Model switched: {old_model} -> {new_model}"


def switch_tui_layout(
    state: RuntimeTuiState | None,
    layout_name: str,
    *,
    workspace: Path | None = None,
) -> str:
    """Switch the active TUI layout and persist it for this workspace when possible."""
    current = normalize_tui_layout_name(state.layout_name if state is not None else None)
    requested = layout_name.strip()
    if not requested:
        return format_tui_layouts(current)
    spec = get_tui_layout_spec(requested)
    if spec is None:
        return f"Unknown layout: {requested}. Use /layout."
    if state is None:
        return f"Current layout: {spec.name}"
    state.layout_name = spec.name
    if workspace is not None:
        from mlpcopilot.runtime.tui.stores.state_store import save_tui_state

        save_tui_state(workspace, state)
    return f"Layout switched: {current} -> {spec.name}"


def _format_model_status(config: Config) -> str:
    lines = [
        f"Current model: {config.agents.defaults.model}",
        "Switch with /model <model>.",
    ]
    candidates = _model_candidates(config)
    if candidates:
        lines.append("Candidates:")
        lines.extend(f"- {model}" for model in candidates[:10])
    return "\n".join(lines)


def _model_candidates(config: Config) -> list[str]:
    """Return conservative model completion candidates for the active provider."""
    current = config.agents.defaults.model
    provider_name = config.get_provider_name(current) or ""
    candidates = [current]
    if provider_name == "openai_codex" or current.startswith(("openai-codex/", "openai_codex/")):
        candidates.extend(
            [
                "openai-codex/gpt-5.4-mini",
                "openai-codex/gpt-5.3-codex",
                "openai-codex/gpt-5.1-codex",
            ]
        )
    elif provider_name == "github_copilot" or current.startswith(("github-copilot/", "github_copilot/")):
        candidates.extend(
            [
                "github_copilot/gpt-5.4-mini",
                "github-copilot/gpt-5.3-codex",
                "github-copilot/gpt-5.1",
            ]
        )
    elif provider_name == "openai" or current.startswith("openai/"):
        candidates.extend(["openai/gpt-5.2", "openai/gpt-5", "gpt-5-chat", "gpt-4o"])

    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item and item not in seen:
            unique.append(item)
            seen.add(item)
    return unique
