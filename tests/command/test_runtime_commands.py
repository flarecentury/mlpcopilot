from types import SimpleNamespace

import pytest

from mlpcopilot.bus.events import InboundMessage
from mlpcopilot.command.builtin import cmd_approvals, cmd_approve, cmd_artifacts, cmd_runs
from mlpcopilot.command.router import CommandContext
from mlpcopilot.runtime.approval import ApprovalManager
from mlpcopilot.runtime.artifacts import ArtifactIndex


def _ctx(tmp_path, raw: str, *, args: str = "") -> CommandContext:
    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="123", content=raw)
    loop = SimpleNamespace(workspace=tmp_path)
    return CommandContext(msg=msg, session=None, key=msg.session_key, raw=raw, args=args, loop=loop)


class _ExecTool:
    def __init__(self):
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return "Exit code: 0"


class _Tools:
    def __init__(self, exec_tool):
        self.exec_tool = exec_tool

    def get(self, name: str):
        if name == "exec":
            return self.exec_tool
        return None


@pytest.mark.asyncio
async def test_approvals_and_approve_commands_use_workspace_manager(tmp_path) -> None:
    record = ApprovalManager(tmp_path).create(
        action_type="memory_update",
        title="Remember fact",
        request="Add confirmed fact to memory",
    )

    listed = await cmd_approvals(_ctx(tmp_path, "/approvals"))
    assert record.approval_id in listed.content
    assert "Pending approvals" in listed.content

    approved = await cmd_approve(
        _ctx(tmp_path, f"/approve {record.approval_id}", args=f"{record.approval_id} ok")
    )
    assert "marked approved" in approved.content
    assert ApprovalManager(tmp_path).list_pending() == []


@pytest.mark.asyncio
async def test_approve_command_resumes_exec_action(tmp_path) -> None:
    record = ApprovalManager(tmp_path).create(
        action_type="destructive_exec",
        title="Delete file",
        request="Delete file",
        metadata={
            "tool": "exec",
            "command": "rm to.txt",
            "working_dir": str(tmp_path),
            "destructive": True,
        },
    )
    exec_tool = _ExecTool()
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="123",
        content=f"/approve {record.approval_id}",
    )
    loop = SimpleNamespace(workspace=tmp_path, tools=_Tools(exec_tool))
    ctx = CommandContext(
        msg=msg,
        session=None,
        key=msg.session_key,
        raw=msg.content,
        args=record.approval_id,
        loop=loop,
    )

    approved = await cmd_approve(ctx)

    assert "marked approved" in approved.content
    assert "Resumed exec after approval" in approved.content
    assert exec_tool.calls == [
        {
            "command": "rm to.txt",
            "working_dir": str(tmp_path),
            "approval_id": record.approval_id,
        }
    ]


@pytest.mark.asyncio
async def test_runs_and_artifacts_commands_use_artifact_index(tmp_path) -> None:
    manifest = ArtifactIndex(tmp_path).create_run(
        source="mcp:test:tool",
        artifacts=["runs/a/output.json"],
        outputs=["reports/a.md"],
    )

    runs = await cmd_runs(_ctx(tmp_path, "/runs"))
    assert manifest.run_id in runs.content
    assert "mcp:test:tool" in runs.content

    artifacts = await cmd_artifacts(
        _ctx(tmp_path, f"/artifacts {manifest.run_id}", args=manifest.run_id)
    )
    assert "runs/a/output.json" in artifacts.content
    assert "reports/a.md" in artifacts.content
