"""Tests for MCP connection lifecycle in AgentLoop."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mlpcopilot.agent.loop import AgentLoop
from mlpcopilot.bus.queue import MessageBus


def _make_loop(tmp_path, *, mcp_servers: dict | None = None) -> AgentLoop:
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.generation.max_tokens = 4096
    return AgentLoop(
        bus=bus,
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        mcp_servers=mcp_servers or {"test": object()},
    )


@pytest.mark.asyncio
async def test_connect_mcp_retries_when_no_servers_connect(tmp_path, monkeypatch: pytest.MonkeyPatch):
    loop = _make_loop(tmp_path)
    attempts = 0

    async def _fake_connect(_servers, _registry):
        nonlocal attempts
        attempts += 1
        return {}

    monkeypatch.setattr("mlpcopilot.agent.tools.mcp.connect_mcp_servers", _fake_connect)

    await loop._connect_mcp()
    await loop._connect_mcp()

    assert attempts == 2
    assert loop._mcp_connected is False
    assert loop._mcp_stacks == {}


def test_mcp_status_reports_configured_and_connected_servers(tmp_path):
    loop = _make_loop(tmp_path, mcp_servers={"a": object(), "b": object()})
    loop._mcp_stacks = {"a": object()}
    loop._mcp_errors = {"b": "b failed"}
    loop._mcp_connected = True

    status = loop.mcp_status()

    assert status["state"] == "partial"
    assert status["configured"] == ["a", "b"]
    assert status["connected"] == ["a"]
    assert status["configured_count"] == 2
    assert status["connected_count"] == 1
    assert status["errors"] == [{"server": "b", "message": "b failed"}]


@pytest.mark.asyncio
async def test_connect_mcp_records_failed_servers_in_status(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    loop = _make_loop(
        tmp_path,
        mcp_servers={
            "local": SimpleNamespace(type="stdio", command="mlp-local-mcp"),
            "remote": SimpleNamespace(type="streamableHttp", url="http://mcp.example.test/mcp"),
        },
    )

    async def _fake_connect(_servers, _registry):
        return {"local": object()}

    monkeypatch.setattr("mlpcopilot.agent.tools.mcp.connect_mcp_servers", _fake_connect)

    await loop._connect_mcp()

    status = loop.mcp_status()
    assert status["state"] == "partial"
    assert status["connected"] == ["local"]
    assert status["errors"][0]["server"] == "remote"
    assert "streamableHttp connection failed" in status["errors"][0]["message"]
    assert "http://mcp.example.test/mcp" in status["errors"][0]["message"]
