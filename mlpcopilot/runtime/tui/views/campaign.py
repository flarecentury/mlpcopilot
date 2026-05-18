"""Adapter display pane rendering for the MLP Copilot TUI."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.segment import Segment
from rich.text import Text

from mlpcopilot.runtime.tui.views.display_document import (
    is_display_document,
    render_display_document,
)

_STALE_DISPLAY_SECONDS = 3600


def _campaign_panel_title() -> str:
    return "Companion"


def _campaign_renderable(
    workspace: Path,
    companion_display: dict[str, Any] | None = None,
    workstate_display: str = "",
    *,
    stale_after_seconds: int = _STALE_DISPLAY_SECONDS,
) -> Any:
    """Render only adapter-provided display documents."""
    summary = workstate_display.strip()
    if companion_display and is_display_document(companion_display):
        return _CompanionRenderable(
            _render_companion_document(
                companion_display,
                stale_after_seconds=stale_after_seconds,
            ),
            summary,
        )
    if summary:
        return _CompanionRenderable(None, summary)
    return Text("(no adapter display)", style="dim")


class _CompanionRenderable:
    """Render adapter content at top while pinning goal/plan summary at bottom."""

    def __init__(self, main: Any | None, summary: str) -> None:
        self.main = main
        self.summary = summary

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        summary = _summary_text(self.summary)
        summary_lines = console.render_lines(
            summary,
            options.update(no_wrap=True, overflow="ellipsis", height=2),
            pad=True,
        )[-2:]
        height = options.height or options.max_height
        if height <= 0:
            height = None
        if self.main is None:
            top_lines: list[list[Segment]] = []
        else:
            top_options = options.update(height=max(0, height - 2) if height else None)
            top_lines = console.render_lines(self.main, top_options, pad=True)
            if height:
                top_lines = top_lines[: max(0, height - 2)]

        blank_count = max(0, height - len(top_lines) - len(summary_lines)) if height else 0
        for line in top_lines:
            yield from line
            yield Segment.line()
        for _ in range(blank_count):
            yield Segment.line()
        for index, line in enumerate(summary_lines):
            yield from line
            if index < len(summary_lines) - 1:
                yield Segment.line()


def _summary_text(summary: str) -> Text:
    lines = summary.splitlines()
    goal = lines[0] if lines else "goal: -"
    plan = lines[1] if len(lines) > 1 else "plan: -"
    return Text(f"{goal}\n{plan}", style="black", no_wrap=True, overflow="ellipsis")


def _render_companion_document(
    companion_display: dict[str, Any],
    *,
    stale_after_seconds: int,
) -> Any:
    """Render adapter content with source freshness metadata for the Companion pane."""
    rendered = render_display_document(companion_display)
    metadata = _companion_metadata_text(
        companion_display,
        stale_after_seconds=stale_after_seconds,
    )
    if not metadata:
        return rendered
    return Group(rendered, metadata)


def _companion_metadata_text(
    companion_display: dict[str, Any],
    *,
    stale_after_seconds: int,
) -> Text | None:
    source = _source_label(companion_display)
    updated = _first_text(
        companion_display.get("updated_at"),
        companion_display.get("queried_at"),
        companion_display.get("created_at"),
    )
    parts: list[str] = []
    if source:
        parts.append(f"source: {source}")
    if updated:
        parts.append(f"updated: {updated}")
    stale = _stale_label(updated, stale_after_seconds=stale_after_seconds)
    if stale:
        parts.append(stale)
    if not parts:
        return None
    return Text(" | ".join(parts), style="dim", no_wrap=True, overflow="ellipsis")


def _source_label(companion_display: dict[str, Any]) -> str:
    status_source = _first_text(companion_display.get("status_source"))
    if status_source:
        return status_source
    source = companion_display.get("source")
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        nested = _first_text(source.get("status_source"), source.get("name"), source.get("path"))
        if nested:
            return nested
    return _first_text(companion_display.get("producer")) or ""


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None or value == "":
            continue
        return str(value)
    return ""


def _stale_label(raw_timestamp: str, *, stale_after_seconds: int) -> str:
    if stale_after_seconds <= 0:
        return ""
    timestamp = _parse_timestamp(raw_timestamp)
    if timestamp is None:
        return ""
    age_seconds = (datetime.now(UTC) - timestamp).total_seconds()
    if age_seconds <= stale_after_seconds:
        return ""
    if age_seconds >= 86400:
        return f"stale: {int(age_seconds // 86400)}d"
    return f"stale: {int(age_seconds // 60)}m"


def _parse_timestamp(raw_timestamp: str) -> datetime | None:
    if not raw_timestamp:
        return None
    text = raw_timestamp.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
