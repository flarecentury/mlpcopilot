"""Runtime-only MCP facade for the DP-GEN adapter.

These tools are intended for the runtime adapter registry, not for the agent
tool registry. They return display/read-model files for the UI to render.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from mlpcopilot.plugins.dpgen_adapter.projector import project_dpgen_run
from mlpcopilot.plugins.dpgen_adapter.workspace_init import init_dpgen_workspace_overlay

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]


def init_workspace_overlay(workspace: str, force: bool = False) -> str:
    """Install DP-GEN workspace overlay assets."""
    return json.dumps(
        init_dpgen_workspace_overlay(Path(workspace), force=force),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )


def render_run_status(workspace: str, project_id: str, run_id: str) -> str:
    """Refresh DP-GEN run projection and return written display document paths."""
    return json.dumps(
        project_dpgen_run(Path(workspace), project_id, run_id),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )


def build_mcp():
    if FastMCP is None:
        raise RuntimeError("fastmcp is not installed")
    mcp = FastMCP("dpgen-adapter")
    mcp.tool(init_workspace_overlay)
    mcp.tool(render_run_status)
    return mcp


def serve_stdio() -> None:
    build_mcp().run(transport="stdio", show_banner=False)


def _parse_args(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(description="DP-GEN runtime adapter MCP server.")
    parser.add_argument("--transport", choices=("stdio",), default="stdio")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.transport == "stdio":
        serve_stdio()


if __name__ == "__main__":
    main()

