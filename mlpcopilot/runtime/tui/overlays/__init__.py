"""Overlay metadata and priority rules for the MLP Copilot TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TuiOverlayId = Literal[
    "approval",
    "pager",
    "tool_log_pager",
    "job_picker",
    "layout_picker",
    "model_picker",
]


@dataclass(frozen=True, slots=True)
class TuiOverlaySpec:
    id: TuiOverlayId
    title: str
    blocks_input: bool
    can_close_with_esc: bool
    priority: int


APPROVAL_OVERLAY = TuiOverlaySpec(
    id="approval",
    title="Approval Required",
    blocks_input=True,
    can_close_with_esc=False,
    priority=100,
)
PAGER_OVERLAY = TuiOverlaySpec(
    id="pager",
    title="Message Pager",
    blocks_input=True,
    can_close_with_esc=True,
    priority=10,
)
TOOL_LOG_PAGER_OVERLAY = TuiOverlaySpec(
    id="tool_log_pager",
    title="Tool Log Pager",
    blocks_input=True,
    can_close_with_esc=True,
    priority=10,
)
JOB_PICKER_OVERLAY = TuiOverlaySpec(
    id="job_picker",
    title="Jobs",
    blocks_input=True,
    can_close_with_esc=True,
    priority=10,
)
LAYOUT_PICKER_OVERLAY = TuiOverlaySpec(
    id="layout_picker",
    title="Layouts",
    blocks_input=True,
    can_close_with_esc=True,
    priority=10,
)
MODEL_PICKER_OVERLAY = TuiOverlaySpec(
    id="model_picker",
    title="Models",
    blocks_input=True,
    can_close_with_esc=True,
    priority=10,
)

_OVERLAYS_BY_ID = {
    APPROVAL_OVERLAY.id: APPROVAL_OVERLAY,
    PAGER_OVERLAY.id: PAGER_OVERLAY,
    TOOL_LOG_PAGER_OVERLAY.id: TOOL_LOG_PAGER_OVERLAY,
    JOB_PICKER_OVERLAY.id: JOB_PICKER_OVERLAY,
    LAYOUT_PICKER_OVERLAY.id: LAYOUT_PICKER_OVERLAY,
    MODEL_PICKER_OVERLAY.id: MODEL_PICKER_OVERLAY,
}


def get_tui_overlay_spec(overlay_id: str) -> TuiOverlaySpec | None:
    return _OVERLAYS_BY_ID.get(overlay_id)


def is_tui_overlay_esc_closable(overlay_id: str | None) -> bool:
    if overlay_id is None:
        return False
    spec = get_tui_overlay_spec(overlay_id)
    return bool(spec and spec.can_close_with_esc)


def active_tui_overlay(
    *,
    approval_pending: bool,
    pager_open: bool,
    tool_log_pager_open: bool = False,
    overlay_stack: list[str] | None = None,
) -> TuiOverlaySpec | None:
    """Return the highest-priority active overlay."""
    if approval_pending:
        return APPROVAL_OVERLAY
    if overlay_stack:
        for overlay_id in reversed(overlay_stack):
            spec = get_tui_overlay_spec(overlay_id)
            if spec is not None:
                return spec
    if tool_log_pager_open:
        return TOOL_LOG_PAGER_OVERLAY
    if pager_open:
        return PAGER_OVERLAY
    return None


def active_tui_overlay_id(
    *,
    approval_pending: bool,
    pager_open: bool,
    tool_log_pager_open: bool = False,
    overlay_stack: list[str] | None = None,
) -> str | None:
    overlay = active_tui_overlay(
        approval_pending=approval_pending,
        pager_open=pager_open,
        tool_log_pager_open=tool_log_pager_open,
        overlay_stack=overlay_stack,
    )
    return overlay.id if overlay is not None else None
