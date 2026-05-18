"""Generic adapter display document rendering."""

from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text


def is_display_document(value: Any) -> bool:
    """Return whether *value* looks like an adapter display document."""
    return (
        isinstance(value, dict)
        and value.get("kind") == "display_document"
        and isinstance(value.get("body"), list)
    )


def display_document_title(value: dict[str, Any], fallback: str) -> str:
    title = value.get("title")
    return str(title) if title else fallback


def render_display_document(value: dict[str, Any]):
    """Render an adapter-provided display document without domain logic."""
    renderables = []
    summary = value.get("summary")
    if summary:
        renderables.append(Text(str(summary)))
    for block in value.get("body") or []:
        if not isinstance(block, dict):
            continue
        renderables.append(_render_block(block))
    if not renderables:
        return Text("(empty)", style="dim")
    return Group(*renderables)


def _render_block(block: dict[str, Any]):
    kind = str(block.get("type") or "markdown")
    if kind == "markdown":
        return Markdown(str(block.get("text") or ""))
    if kind == "key_values":
        return _key_values(block)
    if kind == "table":
        return _table(block)
    if kind == "list":
        return _list(block)
    if kind in {"log", "code"}:
        title = str(block.get("title") or "")
        text = str(block.get("text") or "")
        return Text(f"{title + chr(10) if title else ''}{text}")
    if kind == "divider":
        return Text("-" * 24, style="dim")
    return Markdown(str(block.get("text") or block))


def _key_values(block: dict[str, Any]) -> Table:
    table = Table.grid(expand=True)
    table.add_column("Key", no_wrap=True)
    table.add_column("Value")
    for item in block.get("items") or []:
        if not isinstance(item, dict):
            continue
        table.add_row(str(item.get("key") or ""), str(item.get("value") or ""))
    return table


def _table(block: dict[str, Any]) -> Table:
    columns = [str(item) for item in block.get("columns") or []]
    table = Table(expand=True, box=None, pad_edge=False)
    if not columns:
        table.add_column("Value")
    else:
        for column in columns:
            table.add_column(column)
    for row in block.get("rows") or []:
        if isinstance(row, list):
            values = [str(item) for item in row]
        else:
            values = [str(row)]
        if columns and len(values) < len(columns):
            values.extend("" for _ in range(len(columns) - len(values)))
        table.add_row(*values[: max(1, len(columns))])
    return table


def _list(block: dict[str, Any]) -> Text:
    lines: list[str] = []
    title = str(block.get("title") or "")
    if title:
        lines.append(title)
    for item in block.get("items") or []:
        if isinstance(item, dict):
            text = item.get("text") or item.get("label") or item
        else:
            text = item
        lines.append(f"- {text}")
    return Text("\n".join(lines))
