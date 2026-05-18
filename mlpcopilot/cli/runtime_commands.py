"""MLP runtime/project/run/artifact CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from .common import _load_runtime_config, _missing_dirs, console
from .onboard_commands import _onboard_plugins

mlp_app = typer.Typer(help="Manage MLP Copilot runtime state")


@mlp_app.command("init")
def mlp_init(
    workspace: str = typer.Option(..., "--workspace", "-w", help="MLP Copilot workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Initialize an MLP Copilot workspace and profile config."""
    from mlpcopilot.config.loader import get_config_path, load_config, save_config, set_config_path
    from mlpcopilot.config.schema import Config
    from mlpcopilot.runtime.profiles import MLPCOPILOT_PROFILE, apply_runtime_profile_defaults
    from mlpcopilot.runtime.workspace import sync_mlpcopilot_workspace

    workspace_path = Path(workspace).expanduser().resolve()
    config_path = Path(config).expanduser().resolve() if config else get_config_path()
    set_config_path(config_path)

    loaded = load_config(config_path) if config_path.exists() else Config()
    loaded.runtime_profile = MLPCOPILOT_PROFILE
    loaded.agents.defaults.workspace = str(workspace_path)
    apply_runtime_profile_defaults(loaded)
    save_config(loaded, config_path)
    _onboard_plugins(config_path)
    loaded = load_config(config_path)
    loaded.runtime_profile = MLPCOPILOT_PROFILE
    loaded.agents.defaults.workspace = str(workspace_path)
    apply_runtime_profile_defaults(loaded)
    save_config(loaded, config_path)

    added = sync_mlpcopilot_workspace(workspace_path)
    console.print(f"[green]✓[/green] MLP Copilot config saved at {config_path}")
    console.print(f"[green]✓[/green] Workspace ready at {workspace_path}")
    if not added:
        console.print("[dim]Workspace already matched the MLP Copilot schema[/dim]")


@mlp_app.command("status")
def mlp_status(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show MLP Copilot runtime status."""
    from mlpcopilot.runtime.approval import ApprovalManager
    from mlpcopilot.runtime.artifacts import ArtifactIndex
    from mlpcopilot.runtime.profiles import MLPCOPILOT_PROFILE
    from mlpcopilot.runtime.workspace import (
        MLPCOPILOT_DIRS,
        configured_mcp_servers,
        discovered_skills,
    )

    cfg = _load_runtime_config(config, workspace)
    workspace_path = cfg.workspace_path
    mcp_servers = configured_mcp_servers(cfg)
    skills = discovered_skills(cfg, workspace_path)
    approvals = ApprovalManager(workspace_path)
    runs = ArtifactIndex(workspace_path).list_runs()

    table = Table(title="MLP Copilot Runtime")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("Profile", cfg.runtime_profile)
    table.add_row("Workspace", str(workspace_path))
    table.add_row("Workspace exists", "yes" if workspace_path.exists() else "no")
    table.add_row("Missing schema dirs", ", ".join(_missing_dirs(workspace_path, MLPCOPILOT_DIRS)) or "none")
    table.add_row("MCP servers", str(len(mcp_servers)))
    table.add_row("Skills", str(len(skills)))
    table.add_row("Run manifests", str(len(runs)))
    table.add_row("Pending approvals", str(len(approvals.list_pending())))
    table.add_row("Approval decisions", str(len(approvals.list_decisions())))
    table.add_row("Web tools", "enabled" if cfg.tools.web.enable else "disabled")
    table.add_row("Exec tool", "enabled" if cfg.tools.exec.enable else "disabled")
    table.add_row("Exec allowlist", str(len(cfg.tools.exec.allow_commands)))
    table.add_row("Tool approval allowlist", str(len(cfg.tools.approval_allowlist)))
    table.add_row(
        "Exec approval",
        "required" if cfg.tools.exec.approval_required else "not required",
    )
    table.add_row("Workspace restriction", "enabled" if cfg.tools.restrict_to_workspace else "disabled")
    console.print(table)

    if cfg.runtime_profile != MLPCOPILOT_PROFILE:
        console.print("[yellow]Warning:[/yellow] runtimeProfile is not mlpcopilot")


@mlp_app.command("capabilities")
def mlp_capabilities(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show configured MCP servers and discoverable skills."""
    from mlpcopilot.runtime.workspace import configured_mcp_servers, discovered_skills

    cfg = _load_runtime_config(config, workspace)
    mcp_servers = configured_mcp_servers(cfg)
    skills = discovered_skills(cfg, cfg.workspace_path)

    mcp_table = Table(title="MCP Servers")
    mcp_table.add_column("Name", style="cyan")
    mcp_table.add_column("Type")
    mcp_table.add_column("Target")
    mcp_table.add_column("Enabled Tools")
    mcp_table.add_column("Timeout")
    for server in mcp_servers:
        mcp_table.add_row(
            server["name"],
            server["type"] or "",
            server["target"] or "",
            ", ".join(server["enabled_tools"]),
            str(server["tool_timeout"]),
        )
    if not mcp_servers:
        mcp_table.add_row("(none)", "", "", "", "")
    console.print(mcp_table)

    skills_table = Table(title="Skills")
    skills_table.add_column("Name", style="cyan")
    skills_table.add_column("Source")
    skills_table.add_column("Path")
    for skill in skills:
        skills_table.add_row(skill["name"], skill["source"], skill["path"])
    if not skills:
        skills_table.add_row("(none)", "", "")
    console.print(skills_table)


projects_app = typer.Typer(help="Manage MLP Copilot projects")
mlp_app.add_typer(projects_app, name="projects")


@projects_app.command("create")
def mlp_projects_create(
    name: str = typer.Argument(..., help="Project name"),
    target_use_case: str = typer.Option("", "--target-use-case", "--goal", help="Target use case or validation goal"),
    project_id: str | None = typer.Option(None, "--project-id", help="Explicit project ID"),
    owner: str = typer.Option("", "--owner", help="Workspace owner"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Create a project-scoped MLP workspace skeleton."""
    from mlpcopilot.runtime.workspace import create_mlp_project

    cfg = _load_runtime_config(config, workspace)
    try:
        project = create_mlp_project(
            cfg.workspace_path,
            name=name,
            target_use_case=target_use_case,
            project_id=project_id,
            owner=owner,
        )
    except (FileExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Project created: {project['project_id']}")
    console.print(f"[dim]{cfg.workspace_path / 'projects' / project['project_id']}[/dim]")


@projects_app.command("list")
def mlp_projects_list(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """List project-scoped MLP workspaces."""
    from mlpcopilot.runtime.workspace import list_mlp_projects

    cfg = _load_runtime_config(config, workspace)
    projects = list_mlp_projects(cfg.workspace_path)

    table = Table(title="MLP Projects")
    table.add_column("Project ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Active Run")
    table.add_column("Updated")
    for project in projects:
        table.add_row(
            str(project.get("project_id") or ""),
            str(project.get("name") or ""),
            str(project.get("status") or ""),
            str(project.get("active_run_id") or ""),
            str(project.get("updated_at") or project.get("created_at") or ""),
        )
    if not projects:
        table.add_row("(none)", "", "", "", "")
    console.print(table)


@projects_app.command("show")
def mlp_projects_show(
    project_id: str = typer.Argument(..., help="Project ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show a project and its project-scoped runs."""
    import json

    from mlpcopilot.runtime.workspace import list_mlp_project_runs, load_mlp_project

    cfg = _load_runtime_config(config, workspace)
    try:
        project = load_mlp_project(cfg.workspace_path, project_id)
        runs = list_mlp_project_runs(cfg.workspace_path, project_id)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    payload = dict(project)
    payload["runs"] = runs
    console.print_json(json.dumps(payload, ensure_ascii=False))


artifacts_app = typer.Typer(help="Inspect project-scoped MLP artifacts")
mlp_app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("inspect")
def mlp_artifacts_inspect(
    project_id: str = typer.Argument(..., help="Project ID"),
    run_id: str = typer.Argument(..., help="Run ID"),
    artifact: str = typer.Argument(..., help="Artifact id, name, path, or relative path"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Inspect one project-scoped artifact record."""
    import json

    from mlpcopilot.runtime.artifact_records import find_run_artifact, redact_secrets

    cfg = _load_runtime_config(config, workspace)
    try:
        record = find_run_artifact(cfg.workspace_path, project_id, run_id, artifact)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(redact_secrets(record), ensure_ascii=False))


@artifacts_app.command("lineage")
def mlp_artifacts_lineage(
    project_id: str = typer.Argument(..., help="Project ID"),
    run_id: str = typer.Argument(..., help="Run ID"),
    artifact: str = typer.Argument(..., help="Artifact id, name, path, or relative path"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show artifact parents and children from project-scoped records."""
    import json

    from mlpcopilot.runtime.artifact_records import artifact_lineage

    cfg = _load_runtime_config(config, workspace)
    try:
        payload = artifact_lineage(cfg.workspace_path, project_id, run_id, artifact)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(payload, ensure_ascii=False))


@artifacts_app.command("attach")
def mlp_artifacts_attach(
    project_id: str = typer.Argument(..., help="Project ID"),
    run_id: str = typer.Argument(..., help="Run ID"),
    artifact: str = typer.Argument(..., help="Artifact id, name, path, or relative path"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Build a compact artifact context block for chat/tool use."""
    import json

    from mlpcopilot.runtime.artifact_records import artifact_attach_context

    cfg = _load_runtime_config(config, workspace)
    try:
        payload = artifact_attach_context(cfg.workspace_path, project_id, run_id, artifact)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(payload, ensure_ascii=False))


@mlp_app.command("approvals")
def mlp_approvals(
    include_decisions: bool = typer.Option(False, "--decisions", help="Show decision log instead of pending approvals"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show pending approvals or recorded approval decisions."""
    from mlpcopilot.runtime.approval import ApprovalManager

    cfg = _load_runtime_config(config, workspace)
    manager = ApprovalManager(cfg.workspace_path)
    records = manager.list_decisions() if include_decisions else manager.list_pending()

    table = Table(title="Approval Decisions" if include_decisions else "Pending Approvals")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Status")
    table.add_column("Action")
    table.add_column("Title")
    table.add_column("Run")
    table.add_column("Created")
    for record in records:
        table.add_row(
            record.approval_id,
            record.status,
            record.action_type,
            record.title,
            record.run_id or "",
            record.created_at,
        )
    if not records:
        table.add_row("(none)", "", "", "", "", "")
    console.print(table)


@mlp_app.command("approve")
def mlp_approve(
    approval_id: str = typer.Argument(..., help="Approval ID"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Decision reason"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Approve a pending approval."""
    from mlpcopilot.runtime.approval import ApprovalManager

    cfg = _load_runtime_config(config, workspace)
    try:
        record = ApprovalManager(cfg.workspace_path).approve(
            approval_id,
            decided_by="cli",
            reason=reason,
        )
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Approval {record.approval_id} marked approved")


@mlp_app.command("reject")
def mlp_reject(
    approval_id: str = typer.Argument(..., help="Approval ID"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Decision reason"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Reject a pending approval."""
    from mlpcopilot.runtime.approval import ApprovalManager

    cfg = _load_runtime_config(config, workspace)
    try:
        record = ApprovalManager(cfg.workspace_path).reject(
            approval_id,
            decided_by="cli",
            reason=reason,
        )
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Approval {record.approval_id} marked rejected")


@mlp_app.command("changes")
def mlp_changes(
    approval_id: str = typer.Argument(..., help="Approval ID"),
    reason: str | None = typer.Option(None, "--reason", "-r", help="Requested changes"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Mark a pending approval as needing changes."""
    from mlpcopilot.runtime.approval import ApprovalManager

    cfg = _load_runtime_config(config, workspace)
    try:
        record = ApprovalManager(cfg.workspace_path).needs_changes(
            approval_id,
            decided_by="cli",
            reason=reason,
        )
    except (KeyError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]✓[/green] Approval {record.approval_id} marked needs_changes")


runs_app = typer.Typer(help="Inspect MLP Copilot run manifests")
mlp_app.add_typer(runs_app, name="runs")


@runs_app.command("create")
def mlp_runs_create(
    project_id: str = typer.Argument(..., help="Project ID"),
    backend: str = typer.Option("dpgen", "--backend", help="Backend name for the native workdir"),
    controller_type: str = typer.Option(
        "active_learning_controller",
        "--controller-type",
        help="Generic controller type",
    ),
    plan_id: str | None = typer.Option(None, "--plan-id", help="Optional plan ID"),
    run_id: str | None = typer.Option(None, "--run-id", help="Explicit run ID"),
    no_set_active: bool = typer.Option(False, "--no-set-active", help="Do not set this as the active project run"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Create a project-scoped run skeleton with backend-native workdir."""
    from mlpcopilot.runtime.workspace import create_mlp_run

    cfg = _load_runtime_config(config, workspace)
    try:
        run = create_mlp_run(
            cfg.workspace_path,
            project_id,
            backend=backend,
            controller_type=controller_type,
            plan_id=plan_id,
            run_id=run_id,
            set_active=not no_set_active,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    run_path = cfg.workspace_path / "projects" / project_id / "runs" / run["run_id"]
    console.print(f"[green]✓[/green] Run created: {run['run_id']}")
    console.print(f"[dim]{run_path}[/dim]")


@runs_app.command("sync-dpgen")
def mlp_runs_sync_dpgen(
    project_id: str = typer.Argument(..., help="Project ID"),
    run_id: str = typer.Argument(..., help="Project-scoped run ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Project a DP-GEN backend workdir into run state and UI read-model files."""
    import json

    from mlpcopilot.plugins.dpgen_adapter import project_dpgen_run

    cfg = _load_runtime_config(config, workspace)
    try:
        summary = project_dpgen_run(cfg.workspace_path, project_id, run_id)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(summary, ensure_ascii=False))


@runs_app.command("list")
def mlp_runs_list(
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """List run manifests."""
    from mlpcopilot.runtime.artifacts import ArtifactIndex

    cfg = _load_runtime_config(config, workspace)
    runs = ArtifactIndex(cfg.workspace_path).list_runs()

    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Created")
    table.add_column("Source")
    table.add_column("Artifacts")
    table.add_column("Errors")
    for manifest in runs:
        table.add_row(
            manifest.run_id,
            manifest.created_at,
            manifest.source,
            str(len(manifest.artifacts)),
            str(len(manifest.errors)),
        )
    if not runs:
        table.add_row("(none)", "", "", "", "")
    console.print(table)


@runs_app.command("show")
def mlp_runs_show(
    run_id: str = typer.Argument(..., help="Run ID"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Show a run manifest."""
    import json

    from mlpcopilot.runtime.artifacts import ArtifactIndex

    cfg = _load_runtime_config(config, workspace)
    try:
        manifest = ArtifactIndex(cfg.workspace_path).load(run_id)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    console.print_json(json.dumps(manifest.to_dict(), ensure_ascii=False))


def register(app: typer.Typer) -> None:
    app.add_typer(mlp_app, name="mlp")
