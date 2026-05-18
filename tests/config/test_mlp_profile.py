import json
from pathlib import Path

import pytest

from mlpcopilot.config.loader import load_config
from mlpcopilot.config.schema import Config
from mlpcopilot.runtime.profiles import (
    MLPCOPILOT_DISABLED_BUILTIN_SKILLS,
    MLPCOPILOT_ENABLED_BUILTIN_TOOLS,
    MLPCOPILOT_EXEC_ALLOW_COMMANDS,
    MLPCOPILOT_EXEC_BACKGROUND_COMMANDS,
    MLPCOPILOT_EXEC_READONLY_COMMANDS,
    MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST,
    MLPCOPILOT_TRAINING_CONTROLLER_MCP,
    MLPCOPILOT_WRITE_ALLOWLIST,
    discover_source_mcp_servers,
)


def test_mlpcopilot_profile_applies_safe_runtime_defaults() -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})

    assert config.runtime_profile == "mlpcopilot"
    assert config.tools.restrict_to_workspace is True
    assert config.tools.web.enable is False
    assert config.tools.exec.enable is False
    assert config.tools.exec.require_allowlist is True
    assert config.tools.exec.approval_required is True
    assert config.tools.exec.allow_commands == list(MLPCOPILOT_EXEC_ALLOW_COMMANDS)
    assert config.tools.exec.readonly_commands == list(MLPCOPILOT_EXEC_READONLY_COMMANDS)
    assert config.tools.exec.background_commands == list(MLPCOPILOT_EXEC_BACKGROUND_COMMANDS)
    assert config.tools.my.enable is True
    assert "ask_user" in config.tools.enabled_builtin_tools
    assert "my" in config.tools.enabled_builtin_tools
    assert "my" not in config.tools.approval_allowlist
    assert config.tools.enabled_builtin_tools == list(MLPCOPILOT_ENABLED_BUILTIN_TOOLS)
    assert config.tools.write_allowlist == list(MLPCOPILOT_WRITE_ALLOWLIST)
    assert config.tools.approval_allowlist == list(MLPCOPILOT_TOOL_APPROVAL_ALLOWLIST)
    assert config.tools.approval_gated_writes is True
    assert config.tools.approval_required_for_tools is True
    assert config.agents.defaults.dream.approval_required is True
    for skill in MLPCOPILOT_DISABLED_BUILTIN_SKILLS:
        assert skill in config.agents.defaults.disabled_skills
    assert "validate_machine_runtime" in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "start_training_run" in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "snapshot_training_state" in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "run_training_controller" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "resume_training_run" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "reset_training_run" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "plan_machine_update" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "apply_machine_update" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "plan_param_update" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "apply_param_update" not in MLPCOPILOT_TRAINING_CONTROLLER_MCP["enabledTools"]
    assert "trainingController" in config.tools.mcp_servers
    assert "agentic-file-search" in config.tools.mcp_servers


def test_mlpcopilot_profile_discovers_training_controller_source_path() -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})

    server = config.tools.mcp_servers["trainingController"]

    assert server.command == "uv"
    source_dir = (
        Path(__file__).resolve().parents[2]
        / "mlpcopilot"
        / "mcps"
        / "mlp_training_controller_mcp"
    ).resolve()
    assert server.args[:2] == [
        "--directory",
        str(source_dir),
    ]
    assert server.args[2:] == ["run", "mlp-training-controller-mcp"]
    assert "start_training_run" in server.enabled_tools


def test_load_config_accepts_runtime_profile_camel_case(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"runtimeProfile": "mlpcopilot"}), encoding="utf-8")

    config = load_config(config_path)

    assert config.runtime_profile == "mlpcopilot"
    assert config.tools.web.enable is False
    assert config.tools.enabled_builtin_tools == list(MLPCOPILOT_ENABLED_BUILTIN_TOOLS)
    assert "agentic-file-search" in config.tools.mcp_servers


def test_mlpcopilot_profile_preserves_existing_training_controller_tools() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "mcpServers": {
                    "trainingController": {
                        "type": "stdio",
                        "command": "uv",
                        "args": ["old"],
                        "enabledTools": ["inspect_training_project"],
                    }
                }
            },
        }
    )

    server = config.tools.mcp_servers["trainingController"]
    assert server.args == ["old"]
    assert server.enabled_tools == ["inspect_training_project"]
    assert server.env == {}


def test_mlpcopilot_profile_preserves_existing_builtin_tool_allowlist() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [
                    "read_file",
                    "file_info",
                    "list_dir",
                    "grep",
                    "glob",
                    "write_file",
                    "edit_file",
                    "message",
                ],
            },
        }
    )

    assert config.tools.enabled_builtin_tools == [
        "read_file",
        "file_info",
        "list_dir",
        "grep",
        "glob",
        "write_file",
        "edit_file",
        "message",
    ]


def test_mlpcopilot_profile_preserves_custom_builtin_tool_allowlist() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": ["read_file"],
            },
        }
    )

    assert config.tools.enabled_builtin_tools == ["read_file"]


def test_mlpcopilot_profile_preserves_legacy_training_controller_aliases() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "mcpServers": {
                    "trainingController": {
                        "type": "stdio",
                        "command": "uv",
                        "args": ["old"],
                        "enabledTools": [
                            "start_training_run",
                            "resume_training_run",
                            "plan_machine_update",
                            "apply_param_update",
                        ],
                    }
                }
            },
        }
    )

    tools = config.tools.mcp_servers["trainingController"].enabled_tools
    assert tools == [
        "start_training_run",
        "resume_training_run",
        "plan_machine_update",
        "apply_param_update",
    ]


def test_mlpcopilot_profile_preserves_explicit_extra_mcp_server_env() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "mcpServers": {
                    "agentic-file-search": {
                        "type": "stdio",
                        "command": "uv",
                        "args": ["run", "agentic-file-search-mcp"],
                        "enabledTools": ["agentic_explore"],
                    }
                }
            },
        }
    )

    server = config.tools.mcp_servers["agentic-file-search"]
    assert server.env == {}
    assert server.enabled_tools == ["agentic_explore"]


def test_mlpcopilot_profile_discovers_source_mcp_servers() -> None:
    discovered = discover_source_mcp_servers()

    assert "trainingController" in discovered
    assert "agentic-file-search" in discovered
    assert "mlp-dataset" in discovered
    assert "mlp-model-eval" in discovered
    assert "mlp-report" in discovered
    assert discovered["trainingController"]["command"] == "uv"
    assert discovered["trainingController"]["args"][1].endswith("mlp_training_controller_mcp")
    assert discovered["trainingController"]["enabledTools"] == MLPCOPILOT_TRAINING_CONTROLLER_MCP[
        "enabledTools"
    ]
    assert discovered["agentic-file-search"]["command"] == "uv"
    assert discovered["agentic-file-search"]["enabledTools"] == ["*"]
    assert discovered["mlp-dataset"]["command"] == "uv"
    assert discovered["mlp-dataset"]["enabledTools"] == ["*"]
    assert discovered["mlp-model-eval"]["command"] == "uv"
    assert discovered["mlp-model-eval"]["enabledTools"] == ["*"]
    assert discovered["mlp-report"]["command"] == "uv"
    assert discovered["mlp-report"]["enabledTools"] == ["*"]


def test_mlpcopilot_profile_preserves_existing_source_mcp_config() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "mcpServers": {
                    "agentic-file-search": {
                        "type": "stdio",
                        "command": "custom-agentic",
                        "enabledTools": ["agentic_explore"],
                    }
                }
            },
        }
    )

    server = config.tools.mcp_servers["agentic-file-search"]
    assert server.command == "custom-agentic"
    assert server.enabled_tools == ["agentic_explore"]


def test_mlpcopilot_profile_preserves_explicit_empty_mcp_servers() -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot", "tools": {"mcpServers": {}}})

    assert config.tools.mcp_servers == {}


def test_mlpcopilot_profile_preserves_explicit_empty_disabled_skills() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"disabledSkills": []}},
        }
    )

    assert config.agents.defaults.disabled_skills == []


def test_mlpcopilot_profile_preserves_explicit_dream_approval_policy() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "agents": {"defaults": {"dream": {"approvalRequired": False}}},
        }
    )

    assert config.agents.defaults.dream.approval_required is False


def test_mlp_profile_rejects_public_api_bind_without_auth() -> None:
    with pytest.raises(ValueError, match="apiKey"):
        Config.model_validate(
            {
                "runtimeProfile": "mlpcopilot",
                "api": {"host": "0.0.0.0"},
            }
        )


def test_mlp_profile_allows_public_api_bind_with_api_key_or_proxy_auth() -> None:
    with_key = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "api": {"host": "0.0.0.0", "apiKey": "secret"},
        }
    )
    with_proxy = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "api": {"host": "::", "trustProxyAuth": True},
        }
    )

    assert with_key.api.api_key == "secret"
    assert with_proxy.api.trust_proxy_auth is True


def test_mlp_profile_requires_telegram_allow_from_when_enabled() -> None:
    with pytest.raises(ValueError, match="allowFrom"):
        Config.model_validate(
            {
                "runtimeProfile": "mlpcopilot",
                "channels": {"telegram": {"enabled": True, "token": "123:abc"}},
            }
        )

    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "channels": {
                "telegram": {"enabled": True, "token": "123:abc", "allowFrom": ["12345"]},
            },
        }
    )
    assert config.channels.telegram["allowFrom"] == ["12345"]


def test_tools_accept_custom_exact_approval_allowlist() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {"approvalAllowlist": ["mcp_custom_server_safe_tool"]},
        }
    )

    assert config.tools.approval_allowlist == ["mcp_custom_server_safe_tool"]


def test_tui_accepts_campaign_status_paths() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tui": {"campaignStatusPaths": ["campaigns/current.json"]},
        }
    )

    assert config.tui.campaign_status_paths == ["campaigns/current.json"]


def test_tui_accepts_companion_stale_threshold() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tui": {"companionStaleAfterSeconds": 900},
        }
    )

    assert config.tui.companion_stale_after_seconds == 900


def test_mlp_profile_allows_explicit_exec_only_with_allowlist() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                "exec": {"enable": True, "allowCommands": ["ls -al"]},
            },
        }
    )

    assert config.tools.exec.enable is True
    assert config.tools.exec.require_allowlist is True
    assert config.tools.exec.approval_required is True
    assert config.tools.exec.allow_commands == ["ls -al"]


def test_mlp_profile_applies_default_exec_allow_commands() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                "exec": {"enable": True},
            },
        }
    )

    assert config.tools.exec.allow_commands == list(MLPCOPILOT_EXEC_ALLOW_COMMANDS)
    assert config.tools.exec.approval_required is True


def test_mlp_profile_accepts_custom_empty_exec_allow_commands() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                "exec": {"enable": True, "allowCommands": []},
            },
        }
    )

    assert config.tools.exec.allow_commands == []


def test_mlp_profile_accepts_custom_readonly_commands() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                "exec": {"enable": True, "readonlyCommands": ["ls"]},
            },
        }
    )

    assert config.tools.exec.readonly_commands == ["ls"]


def test_mlp_profile_accepts_custom_background_commands() -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {
                "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                "exec": {"enable": True, "backgroundCommands": ["train_mlp"]},
            },
        }
    )

    assert config.tools.exec.background_commands == ["train_mlp"]


def test_mlp_profile_rejects_exec_without_approval_policy() -> None:
    with pytest.raises(ValueError, match="approvalRequired"):
        Config.model_validate(
            {
                "runtimeProfile": "mlpcopilot",
                "tools": {
                    "enabledBuiltinTools": [*MLPCOPILOT_ENABLED_BUILTIN_TOOLS, "exec"],
                    "exec": {"enable": True, "approvalRequired": False},
                },
            }
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"tools": {"restrictToWorkspace": False}}, "restrictToWorkspace"),
        ({"tools": {"approvalGatedWrites": False}}, "approvalGatedWrites"),
        ({"tools": {"approvalRequiredForTools": False}}, "approvalRequiredForTools"),
    ],
)
def test_mlp_profile_rejects_explicitly_disabled_safety_policy(payload: dict, message: str) -> None:
    payload["runtimeProfile"] = "mlpcopilot"

    with pytest.raises(ValueError, match=message):
        Config.model_validate(payload)


def test_load_config_rejects_invalid_mlpcopilot_safety_policy(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "runtimeProfile": "mlpcopilot",
                "tools": {"approvalRequiredForTools": False},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="approvalRequiredForTools"):
        load_config(config_path)
