"""FastMCP server for evidence-only MLP workflow reports."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore

from .report import ReportBackend

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8914
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP("mlp-report-mcp")


def _backend() -> ReportBackend:
    return ReportBackend()


@mcp.tool()
async def build_evidence_report(
    workspace_path: str,
    artifact_paths: list[str] | None = None,
    output_path: str | None = None,
    title: str = "MLP Evidence Report",
    max_artifacts: int = 200,
) -> str:
    """Build a Markdown report from existing run, artifact, and approval evidence."""
    return _backend().build_evidence_report(
        workspace_path=workspace_path,
        artifact_paths=artifact_paths,
        output_path=output_path,
        title=title,
        max_artifacts=max_artifacts,
    )


def _parser() -> ArgumentParser:
    parser = ArgumentParser(description="MLP report MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("MLP_REPORT_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("MLP_REPORT_MCP_HOST", DEFAULT_HTTP_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MLP_REPORT_MCP_PORT", str(DEFAULT_HTTP_PORT))),
    )
    parser.add_argument("--path", default=os.getenv("MLP_REPORT_MCP_PATH", DEFAULT_HTTP_PATH))
    return parser


def main(argv: list[str] | None = None) -> None:
    args: Namespace = _parser().parse_args(argv)
    if args.transport == "http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port, path=args.path)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
