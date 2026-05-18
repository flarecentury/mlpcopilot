"""FastMCP server for MLP dataset inspection and validation."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore
from mcp.types import ToolAnnotations

from .dataset import DatasetBackend

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8912
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP("mlp-dataset-mcp")
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


def _backend() -> DatasetBackend:
    return DatasetBackend()


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_dataset(dataset_path: str, max_files: int = 200) -> str:
    """Inspect dataset files, hashes, and recognized layouts without scientific conclusions."""
    return _backend().inspect_dataset(dataset_path=dataset_path, max_files=max_files)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def validate_dataset_schema(dataset_path: str, schema_path: str) -> str:
    """Validate a dataset against a simple JSON/YAML file-presence schema."""
    return _backend().validate_dataset_schema(dataset_path=dataset_path, schema_path=schema_path)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def validate_dataset_integrity(dataset_path: str, max_files: int = 500) -> str:
    """Run lightweight file/layout integrity checks for MLP datasets."""
    return _backend().validate_dataset_integrity(dataset_path=dataset_path, max_files=max_files)


@mcp.tool()
async def build_dataset_validation_report(
    dataset_path: str,
    output_path: str | None = None,
    max_files: int = 500,
) -> str:
    """Build a Markdown report from dataset inspection and integrity checks."""
    return _backend().build_dataset_validation_report(
        dataset_path=dataset_path,
        output_path=output_path,
        max_files=max_files,
    )


def _parser() -> ArgumentParser:
    parser = ArgumentParser(description="MLP dataset MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default=os.getenv("MLP_DATASET_MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.getenv("MLP_DATASET_MCP_HOST", DEFAULT_HTTP_HOST))
    parser.add_argument("--port", type=int, default=int(os.getenv("MLP_DATASET_MCP_PORT", str(DEFAULT_HTTP_PORT))))
    parser.add_argument("--path", default=os.getenv("MLP_DATASET_MCP_PATH", DEFAULT_HTTP_PATH))
    return parser


def main(argv: list[str] | None = None) -> None:
    args: Namespace = _parser().parse_args(argv)
    if args.transport == "http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port, path=args.path)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
