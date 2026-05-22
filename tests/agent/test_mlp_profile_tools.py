from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mlpcopilot.agent.loop import AgentLoop
from mlpcopilot.bus.queue import MessageBus
from mlpcopilot.config.schema import Config
from mlpcopilot.runtime.approval import ApprovalManager


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 1024
    return provider


def test_mlpcopilot_profile_registers_minimal_builtin_tools(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    assert set(loop.tools.tool_names) == {
        "ask_user",
        "my",
        "file_info",
        "read_file",
        "list_dir",
        "grep",
        "glob",
        "write_file",
        "edit_file",
        "message",
        "workstate",
    }
    assert loop.tools.get("my").read_only is True


def test_mlpcopilot_profile_registers_web_tools_when_web_is_enabled(tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {"web": {"enable": True}},
        }
    )

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    assert "web_search" in loop.tools.tool_names
    assert "web_fetch" in loop.tools.tool_names


@pytest.mark.asyncio
async def test_mlpcopilot_read_allowlist_extends_restricted_file_tools(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "Deep_MD"
    external.mkdir()
    log = external / "error.log"
    log.write_text("socket.gaierror", encoding="utf-8")
    config = Config.model_validate(
        {
            "runtimeProfile": "mlpcopilot",
            "tools": {"readAllowlist": [str(external)]},
        }
    )
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=workspace,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    result = await loop.tools.execute("read_file", {"path": str(log)})

    assert "socket.gaierror" in result
    assert "outside allowed directory" not in result


def test_mlpcopilot_runtime_config_enables_dream_approval(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
        runtime_config=config,
    )

    assert loop.dream.approval_required is True


def test_mlpcopilot_exec_can_be_explicitly_enabled_with_policy(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})
    config.tools.exec.enable = True
    config.tools.exec.allow_commands = ["ls -al"]
    config.tools.enabled_builtin_tools = [*config.tools.enabled_builtin_tools, "exec"]

    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    exec_tool = loop.tools.get("exec")
    assert exec_tool is not None
    assert exec_tool.require_allowlist is True
    assert exec_tool.approval_required is True
    assert exec_tool.allow_commands == ["ls -al"]


@pytest.mark.asyncio
async def test_mlpcopilot_write_tool_respects_workspace_allowlist(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})
    config.tools.write_allowlist = ["reports/"]
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    approval_required = await loop.tools.execute(
        "write_file",
        {"path": "reports/summary.md", "content": "ok\n"},
    )
    manager = ApprovalManager(tmp_path)
    pending = manager.list_pending()
    assert "Approval required" in approval_required
    assert len(pending) == 1

    manager.approve(pending[0].approval_id, decided_by="test")
    ok = await loop.tools.execute(
        "write_file",
        {
            "path": "reports/summary.md",
            "content": "ok\n",
            "approval_id": pending[0].approval_id,
        },
    )
    blocked = await loop.tools.execute(
        "write_file",
        {"path": "datasets/raw.txt", "content": "blocked\n"},
    )

    assert "Successfully wrote" in ok
    assert "outside the write allowlist" in blocked
    assert not (tmp_path / "datasets" / "raw.txt").exists()


@pytest.mark.asyncio
async def test_mlpcopilot_new_file_write_requires_approval(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    written = await loop.tools.execute(
        "write_file",
        {"path": "reports/new.md", "content": "new\n"},
    )

    pending = ApprovalManager(tmp_path).list_pending()
    assert "Approval required" in written
    assert len(pending) == 1
    assert pending[0].action_type == "file_update"
    assert not (tmp_path / "reports" / "new.md").exists()


@pytest.mark.asyncio
async def test_mlpcopilot_existing_file_write_requires_approval(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})
    target = tmp_path / "memory" / "MEMORY.md"
    target.parent.mkdir(parents=True)
    target.write_text("old\n", encoding="utf-8")
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    blocked = await loop.tools.execute(
        "write_file",
        {"path": "memory/MEMORY.md", "content": "confirmed fact\n"},
    )

    manager = ApprovalManager(tmp_path)
    pending = manager.list_pending()
    assert "Approval required" in blocked
    assert len(pending) == 1
    assert pending[0].action_type == "memory_update"
    assert target.read_text(encoding="utf-8") == "old\n"

    manager.approve(pending[0].approval_id, decided_by="test")
    written = await loop.tools.execute(
        "write_file",
        {
            "path": "memory/MEMORY.md",
            "content": "confirmed fact\n",
            "approval_id": pending[0].approval_id,
        },
    )

    assert "Successfully wrote" in written
    assert (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8") == "confirmed fact\n"


@pytest.mark.asyncio
async def test_mlpcopilot_existing_run_artifact_edit_requires_approval(tmp_path: Path) -> None:
    config = Config.model_validate({"runtimeProfile": "mlpcopilot"})
    run_artifact = tmp_path / "runs" / "run_1" / "manifest.json"
    run_artifact.parent.mkdir(parents=True)
    run_artifact.write_text('{"status": "old"}\n', encoding="utf-8")
    loop = AgentLoop(
        bus=MessageBus(),
        provider=_provider(),
        workspace=tmp_path,
        model="test-model",
        web_config=config.tools.web,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        tools_config=config.tools,
    )

    blocked = await loop.tools.execute(
        "edit_file",
        {
            "path": "runs/run_1/manifest.json",
            "old_text": "old",
            "new_text": "new",
        },
    )

    pending = ApprovalManager(tmp_path).list_pending()
    assert "Approval required" in blocked
    assert pending[0].action_type == "run_artifact_overwrite"
    assert run_artifact.read_text(encoding="utf-8") == '{"status": "old"}\n'
