"""MLP Copilot workspace initialization and status helpers."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mlpcopilot.agent.skills import SkillsLoader
from mlpcopilot.utils.helpers import sync_workspace_templates

MLPCOPILOT_DIRS = (
    "structures",
    "datasets",
    "checkpoints",
    "configs",
    "validation_plans",
    "runs",
    "reports",
    "figures",
    "approvals",
    "jobs",
    "logs",
    "sessions",
    "memory",
    "skills",
    "projects",
    "artifacts",
    "artifacts/blobs",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

PROJECT_TEMPLATE = """# Project

## Project Identity

- Name: (set project name)
- Target system or application domain: (set target)
- Workspace owner: (set owner)

## Workspace Conventions

- Scientific data moves by file path, object id, or artifact reference.
- Metrics and conclusions must cite tool artifacts or run manifests.
- Large datasets, trajectories, and coordinate payloads stay out of LLM context.

## Acceptance Criteria

- Current criteria reference: (path or artifact id)

## Approved Decisions

- (record high-level approved decisions here, with approval ids when available)
"""

AGENTS_TEMPLATE = """# MLP Copilot Workspace Instructions

This workspace is for the MLP Copilot runtime profile.

## Boundary

- MLP Copilot core is the host runtime: conversation, session, memory, tools, MCP client, approvals, artifacts, TUI/API/gateway.
- MCP servers provide executable scientific tools.
- Skills provide method and workflow guidance.
- Do not implement dataset validation algorithms, checkpoint inference, benchmark execution, or validation methodology in MLP Copilot core.

## Evidence Rules

- Move scientific data by file path, object id, or artifact reference.
- Use MCP artifacts and run manifests as the source of metrics.
- Do not ask the LLM to invent or judge scientific metrics.
- Human-approved decisions should be linked to approval records.

## Task Intake and Alignment

- At the start of a new MLP task, actively collect enough context to make the first step sound: target use case, active project/run, relevant dataset/checkpoint/reference artifacts, acceptance criteria, compute budget, and operational constraints.
- Ask focused questions when this context is missing; for small obvious tasks, proceed with explicit assumptions.
- Persist the agreed goal, plan, and active project/run pointer with the `workstate` tool so future turns stay aligned.
- During long-running work, keep plan status current and refresh live DP-GEN or MLP workflow status through MCP tools rather than memory.

## Scratch Policy

- Temporary code, one-off analysis scripts, exploratory outputs, test files, plots, and draft reports should be written to `~/.mlpcopilot/scratch/` by default.
- Do not write temporary code or temporary validation outputs into the user's project directories by default.
- Only modify project files when the user explicitly asks to write into the project.
- When a scratch result is useful, report the scratch path and wait for the user to decide whether it should be moved or copied into the project.
"""

TOOLS_TEMPLATE = """# MLP Copilot Tool Policy

The MLP Copilot profile keeps the runtime tool surface narrow.

## Default Built-in Tools

- ask_user
- my (read-only unless `tools.my.allowSet` is explicitly enabled)
- read_file
- file_info
- list_dir
- grep
- glob
- write_file
- edit_file
- message
- workstate
- mcp_* tools from configured MCP servers
- web_search and web_fetch only when web tools are explicitly enabled

## Default MCP and Skill Context

- `agentic-file-search` is expected to be available by default when its MCP server is configured or discovered.
- The `agentic-file-search` skill is active context by default; use it for local knowledge-base questions, not for repository source search.
- Current task goal, plan, and active project/run should be persisted through `workstate`, not long-term memory.

## Write Policy

Runtime-authored formal workspace files should stay in these workspace locations:

- validation_plans/
- runs/
- projects/
- artifacts/
- reports/
- approvals/
- PROJECT.md
- memory/

Scientific validation, inference, benchmark execution, and report rendering belong in MCP servers or skills, not MLP Copilot core.

## Scratch Boundary

- Temporary code, one-off analysis scripts, exploratory outputs, test files, plots, and draft reports should go to `~/.mlpcopilot/scratch/` by default.
- Only durable reports, approved artifacts, run manifests, and user-requested project files should be written into workspace project directories.
- Do not put scratch scripts or temporary validation outputs into user project folders unless the user explicitly asks for that target path.
"""


def _now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return text[:32] or "project"


def _new_project_id(name: str) -> str:
    return f"proj_{_slug(name)}_{uuid.uuid4().hex[:8]}"


def _new_run_id() -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{stamp}_{uuid.uuid4().hex[:8]}"


def _validate_identifier(label: str, value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid {label}: {value!r}")
    return value


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def sync_mlpcopilot_workspace(
    workspace: Path,
    *,
    silent: bool = False,
) -> list[str]:
    """Initialize the MLP Copilot workspace schema without overwriting files."""
    workspace = workspace.expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    added: list[str] = []

    def _write_text(relative: str, content: str) -> None:
        path = workspace / relative
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        added.append(relative)

    def _write_json(relative: str, payload: dict[str, Any]) -> None:
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        _write_text(relative, text)

    _write_text("AGENTS.md", AGENTS_TEMPLATE)
    _write_text("PROJECT.md", PROJECT_TEMPLATE)
    _write_text("TOOLS.md", TOOLS_TEMPLATE)

    for dirname in MLPCOPILOT_DIRS:
        path = workspace / dirname
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            added.append(dirname + "/")

    _write_text("approvals/pending.jsonl", "")
    _write_text("approvals/decisions.jsonl", "")
    _write_text("artifacts/artifacts.jsonl", "")
    _write_text("artifacts/events.jsonl", "")

    for name in sync_workspace_templates(workspace, silent=True):
        if name not in added:
            added.append(name)

    if added and not silent:
        from rich.console import Console

        console = Console()
        for name in added:
            console.print(f"  [dim]Created {name}[/dim]")
    return added


def create_mlp_project(
    workspace: Path,
    *,
    name: str,
    target_use_case: str = "",
    project_id: str | None = None,
    owner: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an MLP project directory and project-level state files."""
    workspace = workspace.expanduser()
    sync_mlpcopilot_workspace(workspace, silent=True)
    resolved_project_id = _validate_identifier("project_id", project_id or _new_project_id(name))
    project_dir = workspace / "projects" / resolved_project_id
    project_file = project_dir / "project.json"
    if project_file.exists():
        raise FileExistsError(f"Project already exists: {resolved_project_id}")

    now = _now()
    for dirname in ("inventory", "plans", "runs"):
        (project_dir / dirname).mkdir(parents=True, exist_ok=True)

    project = {
        "schema_version": 1,
        "project_id": resolved_project_id,
        "name": name,
        "domain": "machine_learning_potential",
        "target_use_case": target_use_case,
        "owner": owner,
        "active_run_id": None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }
    _atomic_write_json(project_file, project)
    for name_ in (
        "datasets.jsonl",
        "structures.jsonl",
        "checkpoints.jsonl",
        "reference_data.jsonl",
        "compute_resources.jsonl",
    ):
        (project_dir / "inventory" / name_).write_text("", encoding="utf-8")
    return project


def load_mlp_project(workspace: Path, project_id: str) -> dict[str, Any]:
    project_id = _validate_identifier("project_id", project_id)
    path = workspace.expanduser() / "projects" / project_id / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"Project not found: {project_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("project_id"):
        raise ValueError(f"Invalid project file: {path}")
    return data


def list_mlp_projects(workspace: Path) -> list[dict[str, Any]]:
    projects_dir = workspace.expanduser() / "projects"
    rows: list[dict[str, Any]] = []
    for path in sorted(projects_dir.glob("*/project.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return rows


def create_mlp_run(
    workspace: Path,
    project_id: str,
    *,
    backend: str = "dpgen",
    controller_type: str = "active_learning_controller",
    plan_id: str | None = None,
    run_id: str | None = None,
    set_active: bool = True,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a project-scoped run skeleton with backend-native workdir and UI read-model files."""
    workspace = workspace.expanduser()
    project_id = _validate_identifier("project_id", project_id)
    backend = _validate_identifier("backend", backend)
    project = load_mlp_project(workspace, project_id)
    resolved_run_id = _validate_identifier("run_id", run_id or _new_run_id())
    project_dir = workspace / "projects" / project_id
    run_dir = project_dir / "runs" / resolved_run_id
    run_file = run_dir / "run.json"
    if run_file.exists():
        raise FileExistsError(f"Run already exists: {resolved_run_id}")

    now = _now()
    backend_workdir = f"backend/{backend}"
    for dirname in (
        "controller/rendered_inputs",
        "controller/submit_scripts",
        backend_workdir,
        "iterations",
        "reports",
        "logs",
        "ui",
    ):
        (run_dir / dirname).mkdir(parents=True, exist_ok=True)

    run = {
        "schema_version": 1,
        "run_id": resolved_run_id,
        "project_id": project_id,
        "controller_type": controller_type,
        "backend": backend,
        "backend_workdir": backend_workdir,
        "plan_id": plan_id,
        "status": "created",
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
    }
    _atomic_write_json(run_file, run)
    _atomic_write_json(
        run_dir / "run_state.json",
        {
            "schema_version": 1,
            "project_id": project_id,
            "run_id": resolved_run_id,
            "revision": 1,
            "stage": "not_started",
            "phase": None,
            "iteration_id": None,
            "status": "created",
            "blocking_reason": None,
            "updated_at": now,
        },
    )
    _atomic_write_json(
        run_dir / "controller" / "controller.json",
        {
            "schema_version": 1,
            "project_id": project_id,
            "run_id": resolved_run_id,
            "controller_type": controller_type,
            "backend": backend,
            "backend_workdir": backend_workdir,
            "rendered_inputs_dir": "controller/rendered_inputs",
            "created_at": now,
        },
    )
    (run_dir / "artifacts.jsonl").write_text("", encoding="utf-8")
    (run_dir / "logs" / "tool_calls.jsonl").write_text("", encoding="utf-8")

    if set_active:
        project["active_run_id"] = resolved_run_id
        project["updated_at"] = now
        _atomic_write_json(project_dir / "project.json", project)

    return run


def load_mlp_run(workspace: Path, project_id: str, run_id: str) -> dict[str, Any]:
    project_id = _validate_identifier("project_id", project_id)
    run_id = _validate_identifier("run_id", run_id)
    path = workspace.expanduser() / "projects" / project_id / "runs" / run_id / "run.json"
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {project_id}/{run_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("run_id"):
        raise ValueError(f"Invalid run file: {path}")
    return data


def list_mlp_project_runs(workspace: Path, project_id: str) -> list[dict[str, Any]]:
    project_id = _validate_identifier("project_id", project_id)
    project_dir = workspace.expanduser() / "projects" / project_id
    if not (project_dir / "project.json").exists():
        raise FileNotFoundError(f"Project not found: {project_id}")
    rows: list[dict[str, Any]] = []
    for path in sorted((project_dir / "runs").glob("*/run.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return rows


def configured_mcp_servers(config: Any) -> list[dict[str, Any]]:
    """Return a display-friendly summary of configured MCP servers."""
    rows: list[dict[str, Any]] = []
    for name, server in sorted(config.tools.mcp_servers.items()):
        rows.append(
            {
                "name": name,
                "type": server.type or ("stdio" if server.command else "streamableHttp"),
                "enabled_tools": list(server.enabled_tools),
                "tool_timeout": server.tool_timeout,
                "target": server.command or server.url,
            }
        )
    return rows


def discovered_skills(config: Any, workspace: Path) -> list[dict[str, str]]:
    """Return currently discoverable skills after the active disabled-skill policy."""
    loader = SkillsLoader(
        workspace,
        disabled_skills=set(config.agents.defaults.disabled_skills or []),
    )
    return loader.list_skills(filter_unavailable=False)
