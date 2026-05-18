"""Tests for runtime approval handlers exposed by the OpenAI-compatible API."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from mlpcopilot.api.server import (
    handle_approval_approve,
    handle_approval_reject,
    handle_approvals,
    handle_chat_completions,
)
from mlpcopilot.bus.events import InboundMessage
from mlpcopilot.command.builtin import register_builtin_commands
from mlpcopilot.command.router import CommandContext, CommandRouter
from mlpcopilot.runtime.approval import ApprovalManager


class _Request:
    def __init__(
        self,
        app: dict,
        *,
        body: dict | None = None,
        query: dict[str, str] | None = None,
        match_info: dict[str, str] | None = None,
    ) -> None:
        self.app = app
        self._body = body
        self.query = query or {}
        self.match_info = match_info or {}
        self.content_type = "application/json"
        self.can_read_body = body is not None

    async def json(self) -> dict | None:
        return self._body


def _agent(workspace):
    agent = MagicMock()
    agent.workspace = workspace
    agent.process_direct = AsyncMock(return_value="ok")
    agent._connect_mcp = AsyncMock()
    agent.close_mcp = AsyncMock()
    return agent


def _app(agent) -> dict:
    return {
        "agent_loop": agent,
        "model_name": "m",
        "request_timeout": 10.0,
        "session_locks": {},
    }


class _ExecTool:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return "Exit code: 0"


class _Tools:
    def __init__(self, exec_tool: _ExecTool) -> None:
        self.exec_tool = exec_tool

    def get(self, name: str):
        if name == "exec":
            return self.exec_tool
        return None


class _WorkflowAgent:
    def __init__(self, workspace, tools) -> None:
        self.workspace = workspace
        self.tools = tools
        self.calls = []
        self.router = CommandRouter()
        register_builtin_commands(self.router)

    async def process_direct(self, *, content, session_key, channel, chat_id, **_kwargs):
        self.calls.append(
            {
                "content": content,
                "session_key": session_key,
                "channel": channel,
                "chat_id": chat_id,
            }
        )
        msg = InboundMessage(
            channel=channel,
            sender_id="api",
            chat_id=chat_id,
            content=content,
            session_key_override=session_key,
        )
        ctx = CommandContext(
            msg=msg,
            session=None,
            key=session_key,
            raw=content,
            loop=self,
        )
        result = await self.router.dispatch(ctx)
        return result.content if result is not None else "unhandled"


@pytest.mark.asyncio
async def test_api_lists_and_approves_pending_approval(tmp_path) -> None:
    approval = ApprovalManager(tmp_path).create(
        action_type="exec_command",
        title="Approve exec",
        request="echo ok",
        metadata={"tool": "exec", "command": "echo ok"},
    )
    app = _app(_agent(tmp_path))

    listed = await handle_approvals(_Request(app))
    listed_body = json.loads(listed.text)
    assert listed.status == 200
    assert listed_body["data"][0]["approval_id"] == approval.approval_id

    decided = await handle_approval_approve(
        _Request(
            app,
            body={"reason": "ok", "decided_by": "api-test"},
            match_info={"approval_id": approval.approval_id},
        )
    )
    decided_body = json.loads(decided.text)

    assert decided.status == 200
    assert decided_body["data"]["status"] == "approved"
    assert decided_body["data"]["reason"] == "ok"
    assert ApprovalManager(tmp_path).list_pending() == []

    decisions = await handle_approvals(_Request(app, query={"decisions": "true"}))
    decisions_body = json.loads(decisions.text)
    assert decisions_body["data"][0]["approval_id"] == approval.approval_id


@pytest.mark.asyncio
async def test_api_rejects_unknown_approval(tmp_path) -> None:
    resp = await handle_approval_reject(
        _Request(
            _app(_agent(tmp_path)),
            body={"reason": "no"},
            match_info={"approval_id": "apr_missing"},
        )
    )
    body = json.loads(resp.text)

    assert resp.status == 404
    assert body["error"]["message"] == "Approval not found: apr_missing"


@pytest.mark.asyncio
async def test_api_chat_completion_runs_in_api_channel(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("mlpcopilot.api.server.get_media_dir", lambda _channel=None: tmp_path / "media")
    agent = _agent(tmp_path)
    resp = await handle_chat_completions(
        _Request(
            _app(agent),
            body={
                "messages": [{"role": "user", "content": "/approve apr_123"}],
                "session_id": "approval-session",
            },
        )
    )

    assert resp.status == 200
    call_kwargs = agent.process_direct.call_args.kwargs
    assert call_kwargs["channel"] == "api"
    assert call_kwargs["session_key"] == "api:approval-session"


@pytest.mark.asyncio
async def test_api_chat_completion_approval_command_resumes_action(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("mlpcopilot.api.server.get_media_dir", lambda _channel=None: tmp_path / "media")
    approval = ApprovalManager(tmp_path).create(
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
    agent = _WorkflowAgent(tmp_path, _Tools(exec_tool))

    resp = await handle_chat_completions(
        _Request(
            _app(agent),
            body={
                "messages": [{"role": "user", "content": f"/approve {approval.approval_id} ok"}],
                "session_id": "approval-session",
            },
        )
    )
    body = json.loads(resp.text)

    assert resp.status == 200
    assert "marked approved" in body["choices"][0]["message"]["content"]
    assert "Resumed exec after approval" in body["choices"][0]["message"]["content"]
    assert agent.calls == [
        {
            "content": f"/approve {approval.approval_id} ok",
            "session_key": "api:approval-session",
            "channel": "api",
            "chat_id": "default",
        }
    ]
    assert exec_tool.calls == [
        {
            "command": "rm to.txt",
            "working_dir": str(tmp_path),
            "approval_id": approval.approval_id,
        }
    ]
    assert ApprovalManager(tmp_path).list_pending() == []
