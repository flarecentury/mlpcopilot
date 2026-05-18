"""Chat transcript, markdown, scroll, and pager rendering."""

from __future__ import annotations

import re
import shutil
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text

from mlpcopilot.runtime.tui.common import (
    _render_rich_ansi,
    _sanitize_terminal_output_for_tui,
    _short,
)
from mlpcopilot.runtime.tui.state import RuntimeTuiState, TuiMessage

if TYPE_CHECKING:
    from mlpcopilot.config.schema import Config

_CHAT_MARKDOWN_ROLES = {"assistant", "system"}
_CHAT_BOTTOM_PADDING_LINES = 1

def _render_pager_ansi(state: RuntimeTuiState) -> str:
    columns, rows = shutil.get_terminal_size(fallback=(120, 30))
    return _pager_ansi(
        state,
        width=max(20, columns - 8),
        height=max(6, rows - 8),
    )

def _chat_viewport_size(
    viewport_width: int | None,
    viewport_height: int | None,
    *,
    has_pending: bool,
) -> tuple[int | None, int | None]:
    if viewport_width is None or viewport_height is None:
        return None, None
    body_height = viewport_height - (9 if has_pending else 0)
    bottom_height = max(5, body_height // 4)
    top_height = max(8 if has_pending else 12, body_height - bottom_height)
    # The top row is split 3:2 between Chat and Tool Log, plus panel borders.
    chat_width = max(20, int(viewport_width * 0.60) - 4)
    chat_height = max(3, top_height - 2)
    return chat_width, chat_height

def _chat_scroll_metrics(
    state: RuntimeTuiState,
    *,
    terminal_width: int,
    terminal_height: int,
    has_pending: bool,
) -> tuple[int, int]:
    body_height = max(10, terminal_height - 4)
    chat_width, chat_height = _chat_viewport_size(
        terminal_width,
        body_height,
        has_pending=has_pending,
    )
    if not chat_width or not chat_height:
        return 4, 0
    lines = _chat_rendered_lines(state, chat_width)
    content_height = _chat_content_height(chat_height)
    page = max(1, content_height - 1)
    return page, _max_scroll_from_bottom(lines, height=content_height)

def _chat_panel_title(config: Config, state: RuntimeTuiState) -> str:
    title = f"Chat / Task (current model: {_short(config.agents.defaults.model, 44)})"
    if state.chat_scroll > 0:
        title = f"{title} up {state.chat_scroll}"
    return title

def _chat_renderable(
    state: RuntimeTuiState,
    *,
    viewport_width: int | None = None,
    viewport_height: int | None = None,
) -> Any:
    if not state.chat:
        return Text("No chat yet.")
    if viewport_width and viewport_height:
        lines = _chat_rendered_lines(state, viewport_width)
        content_height = _chat_content_height(viewport_height)
        state.chat_scroll = _clamp_scroll_from_bottom(
            lines,
            height=content_height,
            scroll_from_bottom=state.chat_scroll,
        )
        visible = _slice_chat_lines_from_bottom(
            lines,
            height=content_height,
            scroll_from_bottom=state.chat_scroll,
        )
        return Text.from_ansi("\n".join(visible))
    return _chat_transcript_renderable(state)

def _chat_content_height(viewport_height: int) -> int:
    return max(1, viewport_height - _CHAT_BOTTOM_PADDING_LINES)

def _chat_transcript_renderable(state: RuntimeTuiState, *, limit: int | None = 6) -> Any:
    renderables: list[Any] = []
    recent = state.chat if limit is None else state.chat[-limit:]
    for index, item in enumerate(recent):
        renderables.append(
            Text(
                f"{item.role}:",
                style="bold cyan" if item.role == "user" else "bold green",
            )
        )
        renderables.append(_chat_message_renderable(item))
        if index < len(recent) - 1:
            renderables.append(Text(""))
    return Group(*renderables)

def _chat_message_renderable(item: TuiMessage) -> Any:
    content = _format_short_approval_prompt(item.content.strip())
    if not content:
        return Text("")
    if _looks_like_exec_resume_output(content):
        content = _sanitize_terminal_output_for_tui(content)
        return Text.from_ansi(content, no_wrap=True, overflow="crop")
    if item.role in _CHAT_MARKDOWN_ROLES and _looks_like_markdown(content):
        return Markdown(content, code_theme="monokai", hyperlinks=False)
    return Text(content)

def _looks_like_exec_resume_output(content: str) -> bool:
    return "Resumed exec after approval:\n" in content or (
        content.startswith("Approval ") and "\nOutput:\n" in content
    )


def _format_short_approval_prompt(content: str) -> str:
    if not re.search(r"\bapr_[0-9a-f]{12}\b", content, flags=re.IGNORECASE):
        return content
    if not re.search(r"/approve\s+apr_[0-9a-f]{12}", content, flags=re.IGNORECASE):
        return content
    if len(content) > 360:
        return content
    content = re.sub(r"\n{2,}", "\n", content)
    content = re.sub(r"\s+(请(?:回复|发送)\s+/approve\b)", r"\n\1", content)
    content = re.sub(r"\s+(或在终端运行\s+mlpcopilot\b)", r"\n\1", content)
    return content

def _looks_like_markdown(content: str) -> bool:
    return bool(
        re.search(
            r"(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|```|>\s)|"
            r"(\*\*[^*\n]+\*\*|`[^`\n]+`|\[[^\]\n]+\]\([^)]+\))",
            content,
        )
    )

def _chat_rendered_lines(state: RuntimeTuiState, width: int) -> list[str]:
    ansi = _render_rich_ansi(
        _chat_transcript_renderable(state, limit=None),
        width=width,
        height=4000,
    )
    return ansi.rstrip("\n").splitlines() or [""]

def _message_rendered_lines(item: TuiMessage, width: int) -> list[str]:
    ansi = _render_rich_ansi(_chat_message_renderable(item), width=width, height=4000)
    return ansi.rstrip("\n").splitlines() or [""]

def _slice_chat_lines_from_bottom(
    lines: list[str],
    *,
    height: int,
    scroll_from_bottom: int,
) -> list[str]:
    if height <= 0:
        return []
    scroll = _clamp_scroll_from_bottom(
        lines,
        height=height,
        scroll_from_bottom=scroll_from_bottom,
    )
    end = len(lines) - scroll
    start = max(0, end - height)
    visible = list(lines[start:end])
    if not visible:
        return visible
    if start > 0:
        visible[0] = f"... {start} older line(s) above ..."
    if end < len(lines):
        visible[-1] = f"... {len(lines) - end} newer line(s) below ..."
    return visible

def _max_scroll_from_bottom(lines: list[str], *, height: int) -> int:
    if height <= 0:
        return 0
    return max(0, len(lines) - height)

def _clamp_scroll_from_bottom(
    lines: list[str],
    *,
    height: int,
    scroll_from_bottom: int,
) -> int:
    return min(
        max(0, scroll_from_bottom),
        _max_scroll_from_bottom(lines, height=height),
    )

def _open_pager_for_latest_message(state: RuntimeTuiState) -> bool:
    for idx in range(len(state.chat) - 1, -1, -1):
        if state.chat[idx].content.strip():
            state.pager_message_index = idx
            state.pager_scroll = 0
            return True
    return False

def _pager_message(state: RuntimeTuiState) -> TuiMessage | None:
    if not state.chat:
        return None
    idx = state.pager_message_index
    if idx is None or idx < 0 or idx >= len(state.chat):
        idx = len(state.chat) - 1
        state.pager_message_index = idx
    return state.chat[idx]

def _pager_ansi(state: RuntimeTuiState, *, width: int, height: int) -> str:
    item = _pager_message(state)
    if item is None:
        return "No message is available.\n\nEsc closes this pager."

    content_height = max(1, height - 4)
    lines = _message_rendered_lines(item, width)
    max_scroll = max(0, len(lines) - content_height)
    state.pager_scroll = min(max(0, state.pager_scroll), max_scroll)
    start = state.pager_scroll
    end = min(len(lines), start + content_height)
    pct = 100 if max_scroll == 0 else int((state.pager_scroll / max_scroll) * 100)
    header = (
        f"{item.role} message {state.pager_message_index + 1 if state.pager_message_index is not None else '-'}"
        f"/{len(state.chat)} | {pct}% | PgUp/PgDn scroll | Home/End jump | Esc close"
    )
    divider = "-" * min(width, max(8, len(header)))
    return "\n".join([header, divider, *lines[start:end], divider])
