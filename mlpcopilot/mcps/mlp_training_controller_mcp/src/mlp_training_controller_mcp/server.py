"""FastMCP server for the MLP training controller."""

from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

try:  # Prefer standalone fastmcp when available.
    from fastmcp import FastMCP
except Exception:  # pragma: no cover - fallback for mcp SDK installs.
    from mcp.server.fastmcp import FastMCP  # type: ignore
from mcp.types import ToolAnnotations

from .backends import DPGenBackend

DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8911
DEFAULT_HTTP_PATH = "/mcp"

mcp = FastMCP("mlp-training-controller-mcp")
READ_ONLY_TOOL = ToolAnnotations(readOnlyHint=True, destructiveHint=False)


def _backend(name: str = "auto") -> DPGenBackend:
    normalized = (name or "auto").strip().lower()
    if normalized in {"auto", "dpgen"}:
        return DPGenBackend()
    raise ValueError(f"Unsupported training backend: {name}")


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_training_project(project_path: str, backend: str = "auto") -> str:
    """Inspect a training project and detect backend state without modifying files."""
    return _backend(backend).inspect_training_project(project_path)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def validate_training_inputs(
    param_path: str,
    machine_path: str,
    backend: str = "dpgen",
    project_path: str | None = None,
) -> str:
    """Validate backend-native training parameter and machine/resource config files."""
    return _backend(backend).validate_training_inputs(
        param_path=param_path,
        machine_path=machine_path,
        project_path=project_path,
    )


@mcp.tool()
async def validate_machine_runtime(
    machine_path: str,
    backend: str = "dpgen",
    project_path: str | None = None,
    stages: str = "train,model_devi,fp",
    timeout_seconds: int = 60,
    max_log_chars: int = 4000,
    exact: bool = False,
    probe_args_json: str | None = None,
    output_path: str | None = None,
) -> str:
    """Run lightweight local probes for machine.json commands and capture truncated logs."""
    return _backend(backend).validate_machine_runtime(
        machine_path=machine_path,
        project_path=project_path,
        stages=stages,
        timeout_seconds=timeout_seconds,
        max_log_chars=max_log_chars,
        exact=exact,
        probe_args_json=probe_args_json,
        output_path=output_path,
    )


@mcp.tool()
async def generate_training_param(
    system_profile_path: str,
    strategy_config_path: str,
    output_path: str,
    backend: str = "dpgen",
) -> str:
    """Generate a backend-native training parameter file from system and strategy profiles."""
    provider = _backend(backend)
    return provider.generate_training_param(
        system_profile_path=system_profile_path,
        strategy_config_path=strategy_config_path,
        output_path=output_path,
    )


@mcp.tool()
async def generate_training_machine(
    machine_profile_path: str,
    output_path: str,
    backend: str = "dpgen",
) -> str:
    """Generate a backend-native machine/resource config file from a machine profile."""
    provider = _backend(backend)
    return provider.generate_training_machine(
        machine_profile_path=machine_profile_path,
        output_path=output_path,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_training_status(project_path: str, backend: str = "auto") -> str:
    """Read current training backend status from project files."""
    return _backend(backend).get_training_status(project_path)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def list_training_iterations(project_path: str, backend: str = "auto") -> str:
    """List training iterations discovered in the project."""
    return _backend(backend).list_training_iterations(project_path)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_training_iteration(
    project_path: str,
    iteration: int,
    backend: str = "auto",
) -> str:
    """Inspect one training iteration by numeric index."""
    return _backend(backend).inspect_training_iteration(project_path, iteration)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def collect_training_logs(
    project_path: str,
    backend: str = "auto",
    max_lines: int = 80,
) -> str:
    """Collect paths, hashes, and redacted tails for candidate training logs."""
    return _backend(backend).collect_training_logs(project_path, max_lines=max_lines)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def analyze_training_failure(
    project_path: str,
    backend: str = "auto",
    max_lines: int = 200,
) -> str:
    """Analyze known failure signatures from training backend logs."""
    return _backend(backend).analyze_training_failure(project_path, max_lines=max_lines)


@mcp.tool()
async def build_training_run_report(
    project_path: str,
    backend: str = "auto",
    output_path: str | None = None,
) -> str:
    """Build a Markdown report from training status, iterations, and failure signatures."""
    return _backend(backend).build_training_run_report(project_path, output_path=output_path)


@mcp.tool()
async def run_training_controller(
    project_path: str,
    backend: str = "dpgen",
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
    mode: str = "auto",
) -> str:
    """Launch dpgen run; DP-GEN continues from record.dpgen when present."""
    return _backend(backend).run_training_controller(
        project_path=project_path,
        param_path=param_path,
        machine_path=machine_path,
        run_id=run_id,
        dpgen_command=dpgen_command,
        mode=mode,
    )


@mcp.tool()
async def start_training_run(
    project_path: str,
    backend: str = "dpgen",
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
) -> str:
    """Compatibility alias for run_training_controller(mode='auto')."""
    return _backend(backend).start_training_run(
        project_path=project_path,
        param_path=param_path,
        machine_path=machine_path,
        run_id=run_id,
        dpgen_command=dpgen_command,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def get_controller_state(
    project_path: str,
    backend: str = "dpgen",
    run_id: str | None = None,
    max_log_lines: int = 80,
) -> str:
    """Read the local controller process state and recent logs."""
    return _backend(backend).get_controller_state(
        project_path=project_path,
        run_id=run_id,
        max_log_lines=max_log_lines,
    )


@mcp.tool()
async def stop_training_run(
    project_path: str,
    backend: str = "dpgen",
    run_id: str | None = None,
    signal_name: str = "TERM",
) -> str:
    """Signal the local DP-GEN controller process; remote scheduler jobs may continue."""
    return _backend(backend).stop_training_run(
        project_path=project_path,
        run_id=run_id,
        signal_name=signal_name,
    )


@mcp.tool()
async def resume_training_run(
    project_path: str,
    backend: str = "dpgen",
    param_path: str | None = None,
    machine_path: str | None = None,
    run_id: str | None = None,
    dpgen_command: str = "dpgen",
) -> str:
    """Compatibility alias for run_training_controller(mode='resume')."""
    return _backend(backend).resume_training_run(
        project_path=project_path,
        param_path=param_path,
        machine_path=machine_path,
        run_id=run_id,
        dpgen_command=dpgen_command,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def plan_training_rewind(
    project_path: str,
    backend: str = "dpgen",
    target: str = "previous_stage",
    target_iteration: int | None = None,
    target_stage: int | None = None,
    mode: str = "soft",
) -> str:
    """Plan a DP-GEN record rewind. Default soft mode preserves iter dirs; hard mode archives later iter dirs instead of deleting them."""
    return _backend(backend).plan_training_rewind(
        project_path=project_path,
        target=target,
        target_iteration=target_iteration,
        target_stage=target_stage,
        mode=mode,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def plan_training_reset(
    project_path: str,
    target_iteration: int,
    target_stage: int,
    backend: str = "dpgen",
    mode: str = "soft",
) -> str:
    """Compatibility alias for plan_training_rewind(target='explicit'); hard mode archives later iter dirs instead of deleting them."""
    return _backend(backend).plan_training_reset(
        project_path=project_path,
        target_iteration=target_iteration,
        target_stage=target_stage,
        mode=mode,
    )


@mcp.tool()
async def apply_training_rewind(
    project_path: str,
    backend: str = "dpgen",
    target: str = "previous_stage",
    target_iteration: int | None = None,
    target_stage: int | None = None,
    mode: str = "soft",
) -> str:
    """Apply a DP-GEN record rewind. Soft preserves iter dirs; hard archives later iter dirs under the backup dir and never deletes them."""
    return _backend(backend).apply_training_rewind(
        project_path=project_path,
        target=target,
        target_iteration=target_iteration,
        target_stage=target_stage,
        mode=mode,
    )


@mcp.tool()
async def reset_training_run(
    project_path: str,
    target_iteration: int,
    target_stage: int,
    backend: str = "dpgen",
    mode: str = "soft",
) -> str:
    """Compatibility alias for apply_training_rewind(target='explicit'); hard mode archives later iter dirs and never deletes them."""
    return _backend(backend).reset_training_run(
        project_path=project_path,
        target_iteration=target_iteration,
        target_stage=target_stage,
        mode=mode,
    )


@mcp.tool()
async def rerun_failed_stage(
    project_path: str,
    backend: str = "dpgen",
    mode: str = "soft",
) -> str:
    """Compatibility alias for apply_training_rewind(target='previous_stage'); hard mode archives later iter dirs and never deletes them."""
    return _backend(backend).rerun_failed_stage(
        project_path=project_path,
        mode=mode,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def list_dispatcher_jobs(
    project_path: str,
    backend: str = "dpgen",
    max_results: int = 200,
) -> str:
    """List DPDispatcher job.json files created by DP-GEN."""
    return _backend(backend).list_dispatcher_jobs(project_path=project_path, max_results=max_results)


@mcp.tool(annotations=READ_ONLY_TOOL)
async def inspect_dispatcher_job(
    project_path: str,
    job_ref: str,
    backend: str = "dpgen",
    max_log_lines: int = 120,
) -> str:
    """Inspect a DPDispatcher job.json file or listed job id."""
    return _backend(backend).inspect_dispatcher_job(
        project_path=project_path,
        job_ref=job_ref,
        max_log_lines=max_log_lines,
    )


@mcp.tool()
async def cancel_scheduler_jobs(
    project_path: str,
    backend: str = "dpgen",
    scheduler: str = "slurm",
    job_ids_json: str | None = None,
) -> str:
    """Cancel explicit Slurm/PBS scheduler job ids."""
    return _backend(backend).cancel_scheduler_jobs(
        project_path=project_path,
        scheduler=scheduler,
        job_ids_json=job_ids_json,
    )


@mcp.tool()
async def cancel_remote_jobs(
    project_path: str,
    backend: str = "dpgen",
    scheduler: str = "slurm",
    job_ids_json: str | None = None,
) -> str:
    """Compatibility alias for cancel_scheduler_jobs."""
    return _backend(backend).cancel_remote_jobs(
        project_path=project_path,
        scheduler=scheduler,
        job_ids_json=job_ids_json,
    )


@mcp.tool()
async def snapshot_training_state(
    project_path: str,
    backend: str = "dpgen",
    output_path: str | None = None,
) -> str:
    """Write a compact hash-based snapshot of DP-GEN training state."""
    return _backend(backend).snapshot_training_state(project_path=project_path, output_path=output_path)


@mcp.tool()
async def collect_iteration_evidence(
    project_path: str,
    iteration: int,
    backend: str = "dpgen",
    output_path: str | None = None,
) -> str:
    """Write a compact evidence manifest for one DP-GEN iteration."""
    return _backend(backend).collect_iteration_evidence(
        project_path=project_path,
        iteration=iteration,
        output_path=output_path,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def plan_config_update(
    config_kind: str,
    config_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Plan a param.json or machine.json merge/replacement without modifying files."""
    return _backend(backend).plan_config_update(
        config_kind=config_kind,
        config_path=config_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def plan_machine_update(
    machine_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Compatibility alias for plan_config_update(config_kind='machine')."""
    return _backend(backend).plan_machine_update(
        machine_path=machine_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


@mcp.tool()
async def apply_config_update(
    config_kind: str,
    config_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Apply a param.json or machine.json merge/replacement."""
    return _backend(backend).apply_config_update(
        config_kind=config_kind,
        config_path=config_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


@mcp.tool()
async def apply_machine_update(
    machine_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Compatibility alias for apply_config_update(config_kind='machine')."""
    return _backend(backend).apply_machine_update(
        machine_path=machine_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


@mcp.tool(annotations=READ_ONLY_TOOL)
async def plan_param_update(
    param_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Compatibility alias for plan_config_update(config_kind='param')."""
    return _backend(backend).plan_param_update(
        param_path=param_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


@mcp.tool()
async def apply_param_update(
    param_path: str,
    backend: str = "dpgen",
    updates_json: str | None = None,
    replacement_path: str | None = None,
) -> str:
    """Compatibility alias for apply_config_update(config_kind='param')."""
    return _backend(backend).apply_param_update(
        param_path=param_path,
        updates_json=updates_json,
        replacement_path=replacement_path,
    )


def serve_stdio() -> None:
    mcp.run(transport="stdio", show_banner=False)


def serve_http(*, host: str = DEFAULT_HTTP_HOST, port: int = DEFAULT_HTTP_PORT, path: str = DEFAULT_HTTP_PATH) -> None:
    mcp.run(transport="http", host=host, port=port, path=path, show_banner=False)


def _parse_args(argv: list[str] | None = None) -> Namespace:
    parser = ArgumentParser(description="MLP training controller MCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http"),
        default=os.getenv("MLP_TRAINING_CONTROLLER_MCP_TRANSPORT", "stdio"),
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MLP_TRAINING_CONTROLLER_MCP_HTTP_HOST", DEFAULT_HTTP_HOST),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MLP_TRAINING_CONTROLLER_MCP_HTTP_PORT", DEFAULT_HTTP_PORT)),
    )
    parser.add_argument(
        "--path",
        default=os.getenv("MLP_TRAINING_CONTROLLER_MCP_HTTP_PATH", DEFAULT_HTTP_PATH),
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    try:
        if args.transport == "stdio":
            serve_stdio()
            return
        serve_http(host=args.host, port=args.port, path=args.path)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
