"""FastMCP server for MLP checkpoint inspection and metrics evaluation."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # type: ignore
from mcp.types import ToolAnnotations

from .checkpoint import ModelEvalBackend

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8913
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP("mlp-model-eval-mcp")
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


def _backend() -> ModelEvalBackend:
    return ModelEvalBackend()


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_checkpoint(checkpoint_path: str, max_files: int = 100) -> str:
    """Inspect checkpoint files and hashes without running model inference."""
    return _backend().inspect_checkpoint(checkpoint_path=checkpoint_path, max_files=max_files)


@mcp.tool()
async def validate_checkpoint_on_dataset(
    checkpoint_path: str,
    dataset_path: str,
    metric_config_path: str | None = None,
    run_if_metrics_missing: bool = False,
    dp_command: str = "dp",
    backend: str | None = None,
    data_source: str = "system",
    numb_test: int = 0,
    rand_seed: int | None = None,
    shuffle_test: bool = False,
    atomic: bool = False,
    head: str | None = None,
    output_dir: str | None = None,
    timeout_seconds: int = 60,
) -> str:
    """Check checkpoint metrics, optionally running DeePMD-kit v3 dp test."""
    return _backend().validate_checkpoint_on_dataset(
        checkpoint_path=checkpoint_path,
        dataset_path=dataset_path,
        metric_config_path=metric_config_path,
        run_if_metrics_missing=run_if_metrics_missing,
        dp_command=dp_command,
        backend=backend,
        data_source=data_source,
        numb_test=numb_test,
        rand_seed=rand_seed,
        shuffle_test=shuffle_test,
        atomic=atomic,
        head=head,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
async def run_deepmd_test(
    checkpoint_path: str,
    dataset_path: str,
    data_source: str = "system",
    dp_command: str = "dp",
    backend: str | None = None,
    numb_test: int = 0,
    rand_seed: int | None = None,
    shuffle_test: bool = False,
    atomic: bool = False,
    head: str | None = None,
    output_dir: str | None = None,
    timeout_seconds: int = 60,
) -> str:
    """Run DeePMD-kit v3 dp test with timeout and artifact capture."""
    return _backend().run_deepmd_test(
        checkpoint_path=checkpoint_path,
        dataset_path=dataset_path,
        data_source=data_source,
        dp_command=dp_command,
        backend=backend,
        numb_test=numb_test,
        rand_seed=rand_seed,
        shuffle_test=shuffle_test,
        atomic=atomic,
        head=head,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
async def predict_energy_force(
    structure_path: str,
    checkpoint_path: str,
    structure_format: str | None = None,
    frame_index: int = 0,
    output_path: str | None = None,
    extxyz_path: str | None = None,
    head: str | None = None,
    max_inline_atoms: int = 64,
) -> str:
    """Predict energy and forces for one ASE-readable structure."""
    return _backend().predict_energy_force(
        structure_path=structure_path,
        checkpoint_path=checkpoint_path,
        structure_format=structure_format,
        frame_index=frame_index,
        output_path=output_path,
        extxyz_path=extxyz_path,
        head=head,
        max_inline_atoms=max_inline_atoms,
    )


@mcp.tool()
async def batch_predict(
    structure_dir: str,
    checkpoint_path: str,
    structure_glob: str = "*",
    recursive: bool = True,
    structure_format: str | None = None,
    output_dir: str | None = None,
    head: str | None = None,
    max_structures: int = 200,
    write_extxyz: bool = True,
) -> str:
    """Predict energy and forces for ASE-readable structure files."""
    return _backend().batch_predict(
        structure_dir=structure_dir,
        checkpoint_path=checkpoint_path,
        structure_glob=structure_glob,
        recursive=recursive,
        structure_format=structure_format,
        output_dir=output_dir,
        head=head,
        max_structures=max_structures,
        write_extxyz=write_extxyz,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def compare_checkpoints(
    checkpoint_a: str,
    checkpoint_b: str,
    dataset_path: str | None = None,
    metric_config_path: str | None = None,
) -> str:
    """Compare checkpoint metadata and any supplied precomputed metrics."""
    return _backend().compare_checkpoints(
        checkpoint_a=checkpoint_a,
        checkpoint_b=checkpoint_b,
        dataset_path=dataset_path,
        metric_config_path=metric_config_path,
    )


@mcp.tool()
async def build_checkpoint_metrics(
    metrics_path: str,
    checkpoint_path: str | None = None,
    dataset_path: str | None = None,
    output_path: str | None = None,
) -> str:
    """Normalize a precomputed checkpoint metrics artifact and record hashes."""
    return _backend().build_checkpoint_metrics(
        metrics_path=metrics_path,
        checkpoint_path=checkpoint_path,
        dataset_path=dataset_path,
        output_path=output_path,
    )


@mcp.tool()
async def build_checkpoint_benchmark_report(
    metrics_path: str,
    checkpoint_path: str | None = None,
    dataset_path: str | None = None,
    output_path: str | None = None,
    plot_paths: list[str] | None = None,
    title: str = "Checkpoint Benchmark Report",
    max_hash_files: int = 500,
) -> str:
    """Build a Markdown checkpoint benchmark report from existing metrics artifacts."""
    return _backend().build_checkpoint_benchmark_report(
        metrics_path=metrics_path,
        checkpoint_path=checkpoint_path,
        dataset_path=dataset_path,
        output_path=output_path,
        plot_paths=plot_paths,
        title=title,
        max_hash_files=max_hash_files,
    )


@mcp.tool()
async def build_benchmark_plots(
    metrics_path: str,
    output_dir: str | None = None,
    detail_prefix: str | None = None,
    energy_detail_path: str | None = None,
    force_detail_path: str | None = None,
    max_points: int = 10000,
) -> str:
    """Build PNG benchmark plots from metrics JSON/YAML or dp test detail files."""
    return _backend().build_benchmark_plots(
        metrics_path=metrics_path,
        output_dir=output_dir,
        detail_prefix=detail_prefix,
        energy_detail_path=energy_detail_path,
        force_detail_path=force_detail_path,
        max_points=max_points,
    )


def _parser() -> ArgumentParser:
    parser = ArgumentParser(description="MLP model evaluation MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=os.getenv("MLP_MODEL_EVAL_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument("--host", default=os.getenv("MLP_MODEL_EVAL_MCP_HOST", DEFAULT_HTTP_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MLP_MODEL_EVAL_MCP_PORT", str(DEFAULT_HTTP_PORT))),
    )
    parser.add_argument("--path", default=os.getenv("MLP_MODEL_EVAL_MCP_PATH", DEFAULT_HTTP_PATH))
    return parser


def main(argv: list[str] | None = None) -> None:
    args: Namespace = _parser().parse_args(argv)
    if args.transport == "http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port, path=args.path)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
