"""Layout registry for switchable MLP Copilot TUI bodies."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TUI_LAYOUT = "four_pane"


@dataclass(frozen=True, slots=True)
class TuiLayoutSpec:
    name: str
    description: str
    min_width: int = 100
    min_height: int = 24


_TUI_LAYOUT_SPECS: tuple[TuiLayoutSpec, ...] = (
    TuiLayoutSpec(
        name="four_pane",
        description="Default Chat, Companion, Tool Log, Artifacts, and Approvals workspace",
    ),
    TuiLayoutSpec(
        name="compact",
        description="Compact Chat, Tool Log, Artifacts, and Approvals workspace",
        min_width=80,
        min_height=20,
    ),
    TuiLayoutSpec(
        name="campaign_focus",
        description="Companion-focused workspace for long MLP workflows",
        min_width=100,
        min_height=24,
    ),
    TuiLayoutSpec(
        name="approval_focus",
        description="Approval-focused workspace for review and decisions",
        min_width=90,
        min_height=22,
    ),
)
_TUI_LAYOUT_BY_NAME = {layout.name: layout for layout in _TUI_LAYOUT_SPECS}


def list_tui_layout_specs() -> tuple[TuiLayoutSpec, ...]:
    return _TUI_LAYOUT_SPECS


def get_tui_layout_spec(name: str) -> TuiLayoutSpec | None:
    return _TUI_LAYOUT_BY_NAME.get(name.strip().lower())


def normalize_tui_layout_name(name: str | None) -> str:
    if not name:
        return DEFAULT_TUI_LAYOUT
    normalized = name.strip().lower().replace("-", "_")
    return normalized if normalized in _TUI_LAYOUT_BY_NAME else DEFAULT_TUI_LAYOUT


def format_tui_layouts(current: str | None = None) -> str:
    active = normalize_tui_layout_name(current)
    lines = [f"Current layout: {active}", "Available layouts:"]
    for layout in _TUI_LAYOUT_SPECS:
        marker = "*" if layout.name == active else "-"
        lines.append(f"{marker} {layout.name} - {layout.description}")
    return "\n".join(lines)
