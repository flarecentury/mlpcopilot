"""Runtime profile constants and helpers."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

MLPCOPILOT_PROFILE = "mlpcopilot"

MLPCOPILOT_CHANNEL_ALLOWLIST = frozenset({"telegram"})

MLPCOPILOT_ENABLED_BUILTIN_TOOLS = (
    "ask_user",
    "my",
    "read_file",
    "file_info",
    "list_dir",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
    "write_file",
    "edit_file",
    "message",
    "workstate",
)

MLPCOPILOT_EXEC_ALLOW_COMMANDS = (
    "pwd",
    "ls",
    "ls -a",
    "ls -al",
    "ls -la",
    "whoami",
    "id",
    "date",
    "uname",
    "uname -a",
    "hostname",
    "df -h",
    "du -sh .",
    "free -h",
    "ps aux",
    "git status",
    "git status --short",
    "git diff --stat",
    "git branch --show-current",
    "git log --oneline -5",
    "python --version",
    "python3 --version",
    "uv --version",
    "git --version",
)

MLPCOPILOT_EXEC_READONLY_COMMANDS = (
    "ls",
    "pwd",
    "whoami",
    "id",
    "date",
    "uname",
    "hostname",
    "df",
    "du",
    "free",
    "ps",
    "cat",
    "head",
    "tail",
    "wc",
    "grep",
    "rg",
    "stat",
    "file",
    "tree",
    "printenv",
    "which",
)

MLPCOPILOT_EXEC_BACKGROUND_COMMANDS = (
    "cmatrix",
    "top",
    "htop",
    "btop",
    "watch",
)

MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST: tuple[str, ...] = (
    "ask_user",
    "message",
    "workstate",
    "read_file",
    "file_info",
    "list_dir",
    "grep",
    "glob",
    "web_search",
    "web_fetch",
)

MLPCOPILOT_WRITE_ALLOWLIST: tuple[str, ...] = ()

MLPCOPILOT_DISABLED_BUILTIN_SKILLS = (
    "clawhub",
    "github",
    "skill-creator",
    "summarize",
    "update-setup",
)

MLPCOPILOT_TRAINING_CONTROLLER_MCP = {
    "type": "stdio",
    "command": "uv",
    "args": [
        "--directory",
        "mlpcopilot/mcps/mlp_training_controller_mcp",
        "run",
        "mlp-training-controller-mcp",
    ],
    "env": {
        "UV_CACHE_DIR": "/tmp/uv-cache",
        "UV_LINK_MODE": "copy",
    },
    "toolTimeout": 600,
    "enabledTools": [
        "inspect_training_project",
        "generate_training_param",
        "generate_training_machine",
        "validate_training_inputs",
        "validate_machine_runtime",
        "get_training_status",
        "list_training_iterations",
        "inspect_training_iteration",
        "collect_training_logs",
        "analyze_training_failure",
        "build_training_run_report",
        "get_controller_state",
        "start_training_run",
        "stop_training_run",
        "plan_training_rewind",
        "apply_training_rewind",
        "list_dispatcher_jobs",
        "inspect_dispatcher_job",
        "cancel_scheduler_jobs",
        "snapshot_training_state",
        "collect_iteration_evidence",
        "plan_config_update",
        "apply_config_update",
    ],
}


def _copy_mcp_config(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


def _source_tree_stdio_mcp_config(
    pyproject: Path,
    script_name: str,
    *,
    tool_timeout: int,
    enabled_tools: list[str],
) -> dict[str, Any]:
    return {
        "type": "stdio",
        "command": "uv",
        "args": [
            "--directory",
            str(pyproject.parent.resolve()),
            "run",
            script_name,
        ],
        "env": {
            "UV_CACHE_DIR": "/tmp/uv-cache",
            "UV_LINK_MODE": "copy",
        },
        "toolTimeout": tool_timeout,
        "enabledTools": list(enabled_tools),
    }


def _choose_source_mcp_script(scripts: dict[str, Any]) -> str | None:
    candidates = [name for name in scripts if isinstance(name, str) and "mcp" in name]
    if not candidates:
        return None
    stdio_candidates = [name for name in candidates if "http" not in name and "sse" not in name]
    candidates = stdio_candidates or candidates
    exact_mcp = [name for name in candidates if name.endswith("-mcp")]
    if exact_mcp:
        return sorted(exact_mcp)[0]
    stdio = [name for name in candidates if name.endswith("-mcp-stdio")]
    if stdio:
        return sorted(stdio)[0]
    return sorted(candidates)[0]


def _source_mcp_server_name(project_name: str, script_name: str, directory_name: str) -> str:
    if project_name == "mlp-training-controller-mcp" or directory_name == "mlp_training_controller_mcp":
        return "trainingController"
    base = project_name or script_name or directory_name
    for suffix in ("-mcp", "_mcp"):
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base.replace("_", "-")


def discover_source_mcp_servers(mcps_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Discover MCP server packages shipped in the local source tree."""
    root = mcps_dir or (Path(__file__).resolve().parents[1] / "mcps")
    if not root.is_dir():
        return {}
    discovered: dict[str, dict[str, Any]] = {}
    for pyproject in sorted(root.glob("*/pyproject.toml")):
        try:
            payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = payload.get("project")
        if not isinstance(project, dict):
            continue
        scripts = project.get("scripts")
        if not isinstance(scripts, dict):
            continue
        script_name = _choose_source_mcp_script(scripts)
        if not script_name:
            continue
        project_name = str(project.get("name") or pyproject.parent.name)
        server_name = _source_mcp_server_name(project_name, script_name, pyproject.parent.name)
        if server_name == "trainingController":
            source_config = _copy_mcp_config(MLPCOPILOT_TRAINING_CONTROLLER_MCP)
            source_config["args"] = [
                "--directory",
                str(pyproject.parent.resolve()),
                "run",
                script_name,
            ]
            discovered[server_name] = source_config
            continue
        discovered[server_name] = _source_tree_stdio_mcp_config(
            pyproject,
            script_name,
            tool_timeout=120,
            enabled_tools=["*"],
        )
    return discovered


def is_mlpcopilot_profile(profile: str | None) -> bool:
    """Return whether *profile* is the MLP Copilot runtime profile."""
    return profile == MLPCOPILOT_PROFILE


def channel_allowed_for_profile(profile: str | None, channel_name: str) -> bool:
    """Return whether a channel may be loaded for the selected profile."""
    if is_mlpcopilot_profile(profile):
        return channel_name in MLPCOPILOT_CHANNEL_ALLOWLIST
    return True


def _field_was_set(model: Any, field_name: str) -> bool:
    return field_name in getattr(model, "model_fields_set", set())


def apply_runtime_profile_defaults(config: Any) -> Any:
    """Apply runtime profile defaults in place and return *config*.

    The function intentionally accepts Any to avoid coupling profile constants
    to the Pydantic schema module.
    """
    if not is_mlpcopilot_profile(getattr(config, "runtime_profile", None)):
        return config

    tools = config.tools
    if not _field_was_set(tools, "restrict_to_workspace"):
        tools.restrict_to_workspace = True
    if not _field_was_set(tools.web, "enable"):
        tools.web.enable = False
    if not _field_was_set(tools.exec, "enable"):
        tools.exec.enable = False
    if not _field_was_set(tools.exec, "require_allowlist"):
        tools.exec.require_allowlist = True
    if not _field_was_set(tools.exec, "approval_required"):
        tools.exec.approval_required = True
    if not _field_was_set(tools.exec, "allow_commands"):
        tools.exec.allow_commands = list(MLPCOPILOT_EXEC_ALLOW_COMMANDS)
    if not _field_was_set(tools.exec, "readonly_commands"):
        tools.exec.readonly_commands = list(MLPCOPILOT_EXEC_READONLY_COMMANDS)
    if not _field_was_set(tools.exec, "background_commands"):
        tools.exec.background_commands = list(MLPCOPILOT_EXEC_BACKGROUND_COMMANDS)
    if not _field_was_set(tools.my, "enable"):
        tools.my.enable = True
    if not _field_was_set(tools, "enabled_builtin_tools"):
        tools.enabled_builtin_tools = list(MLPCOPILOT_ENABLED_BUILTIN_TOOLS)
    if not _field_was_set(tools, "write_allowlist"):
        tools.write_allowlist = list(MLPCOPILOT_WRITE_ALLOWLIST)
    if not _field_was_set(tools, "approval_allowlist"):
        tools.approval_allowlist = list(MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST)
    if not _field_was_set(tools, "approval_gated_writes"):
        tools.approval_gated_writes = True
    if not _field_was_set(tools, "approval_required_for_tools"):
        tools.approval_required_for_tools = True

    defaults = config.agents.defaults
    if not _field_was_set(defaults, "disabled_skills"):
        defaults.disabled_skills = list(MLPCOPILOT_DISABLED_BUILTIN_SKILLS)
    if not _field_was_set(defaults.dream, "approval_required"):
        defaults.dream.approval_required = True

    if not _field_was_set(tools, "mcp_servers"):
        source_servers = discover_source_mcp_servers()
        try:
            from mlpcopilot.config.schema import MCPServerConfig

            training_controller = source_servers.pop(
                "trainingController",
                _copy_mcp_config(MLPCOPILOT_TRAINING_CONTROLLER_MCP),
            )
            tools.mcp_servers["trainingController"] = MCPServerConfig.model_validate(
                training_controller
            )
            for name, source_server in source_servers.items():
                if name == "trainingController" or name in tools.mcp_servers:
                    continue
                tools.mcp_servers[name] = MCPServerConfig.model_validate(source_server)
        except Exception:
            training_controller = source_servers.pop(
                "trainingController",
                _copy_mcp_config(MLPCOPILOT_TRAINING_CONTROLLER_MCP),
            )
            tools.mcp_servers["trainingController"] = training_controller
            for name, source_server in source_servers.items():
                if name == "trainingController" or name in tools.mcp_servers:
                    continue
                tools.mcp_servers[name] = _copy_mcp_config(source_server)
    return config
