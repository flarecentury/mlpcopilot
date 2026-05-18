"""Tests for the single-tool FastMCP-backed MCP server."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client
from fs_explorer import mcp_server, openai_compatible_file_agent


async def _call_tool(name: str, arguments: dict):
    async with Client(mcp_server.mcp) as client:
        return await client.call_tool(name, arguments, raise_on_error=False)


def _text_result(result) -> str:
    if result.data is not None:
        return str(result.data)
    return result.content[0].text


@pytest.mark.asyncio
async def test_fastmcp_lists_only_agentic_explore() -> None:
    async with Client(mcp_server.mcp) as client:
        await client.ping()
        tools = await client.list_tools()

    assert [tool.name for tool in tools] == ["agentic_explore"]
    schema = tools[0].inputSchema
    assert sorted(schema["properties"].keys()) == ["task"]
    assert "root" not in schema["properties"]
    assert "base_url" not in schema["properties"]
    assert "model" not in schema["properties"]
    assert "api_key" not in schema["properties"]
    description = tools[0].description or ""
    assert "focused question" in description
    assert "follow-up tasks" in description
    assert "shell script" in description
    assert "Do not" in description
    assert "concrete installation steps" in description


def test_task_policy_classifies_procedure_followup() -> None:
    policy = openai_compatible_file_agent._infer_task_policy("test.txt 的具体安装方法")

    assert policy.intent == "procedure"
    assert "ordered steps" in policy.output_focus
    assert policy.target_hints == ("test.txt",)


def test_task_policy_classifies_bare_topic_read() -> None:
    policy = openai_compatible_file_agent._infer_task_policy("read natfrp")

    assert policy.intent == "read_or_summarize"
    assert "bare topic" in policy.recommended_start


def test_initial_prompt_includes_internal_task_policy(tmp_path: Path) -> None:
    agent = openai_compatible_file_agent.OpenAICompatibleFileSearchAgent(
        task="from test.txt, extract concrete natfrp installation steps",
        folder=str(tmp_path),
        base_url="https://local.test",
        model="local-model",
        db_path=None,
        use_index=False,
        allow_indexing=False,
        allow_embeddings=False,
        allow_metadata=False,
        max_steps=3,
        max_tool_chars=1000,
        temperature=0.1,
        timeout=120,
        api_key=None,
    )

    messages = agent._initial_messages()

    assert "Classified intent: procedure" in messages[1]["content"]
    assert "Internal task policy" in messages[1]["content"]
    assert "Exploration policy" in messages[0]["content"]


@pytest.mark.asyncio
async def test_agentic_explore_uses_configured_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FS_EXPLORER_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL", "https://local.test")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_MODEL", "local-model")
    monkeypatch.setenv("FS_EXPLORER_AGENT_USE_INDEX", "0")
    calls: list[dict] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return json.dumps({"action": "final", "answer": "ok"})

    monkeypatch.setattr(openai_compatible_file_agent, "_chat_completion", fake_chat_completion)

    result = await _call_tool("agentic_explore", {"task": "what is here?"})

    assert result.is_error is False
    assert str(tmp_path) in calls[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_agentic_explore_runs_agent_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FS_EXPLORER_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL", "https://s14.test.digauto.org")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_MODEL", "local-model")
    monkeypatch.setenv("FS_EXPLORER_AGENT_MAX_STEPS", "3")
    monkeypatch.setenv("FS_EXPLORER_AGENT_USE_INDEX", "0")
    note = tmp_path / "note.txt"
    note.write_text("The answer is in this file.")
    calls: list[dict] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return json.dumps(
                {
                    "action": "tool",
                    "tool_name": "read",
                    "arguments": {"file_path": str(note)},
                    "reason": "Read the likely source file.",
                }
            )
        return json.dumps(
            {
                "action": "final",
                "answer": "The answer is in this file [Source: note.txt].",
            }
        )

    monkeypatch.setattr(openai_compatible_file_agent, "_chat_completion", fake_chat_completion)

    result = await _call_tool(
        "agentic_explore",
        {"task": "What is the answer?"},
    )

    assert result.is_error is False
    payload = json.loads(_text_result(result))
    assert payload["answer"] == "The answer is in this file [Source: note.txt]."
    assert payload["agent"]["base_url"] == "https://s14.test.digauto.org"
    assert payload["agent"]["model"] == "local-model"
    assert payload["trace"][0]["tool"] == "read"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_agentic_explore_auto_refreshes_missing_index(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FS_EXPLORER_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("FS_EXPLORER_DB_PATH", str(tmp_path / "fs-explorer.duckdb"))
    monkeypatch.setenv("FS_EXPLORER_AGENT_USE_INDEX", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_INDEXING", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_EMBEDDINGS", "0")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_METADATA", "0")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL", "https://local.test")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_MODEL", "local-model")
    (tmp_path / "note.txt").write_text("hello indexed world")
    calls: list[dict] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return json.dumps({"action": "final", "answer": "ok"})

    monkeypatch.setattr(openai_compatible_file_agent, "_chat_completion", fake_chat_completion)

    result = await _call_tool("agentic_explore", {"task": "find hello"})

    assert result.is_error is False
    payload = json.loads(_text_result(result))
    assert payload["agent"]["use_index"] is True
    prompt = calls[0]["messages"][1]["content"]
    assert '"refreshed": true' in prompt
    assert '"reason": "missing_db"' in prompt
    staleness = mcp_server._index_staleness(str(tmp_path), str(tmp_path / "fs-explorer.duckdb"))
    assert staleness["stale"] is False
    assert staleness["live_files"] == 1
    assert staleness["indexed_files"] == 1


@pytest.mark.asyncio
async def test_agentic_explore_auto_refreshes_new_files(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "fs-explorer.duckdb"
    monkeypatch.setenv("FS_EXPLORER_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("FS_EXPLORER_DB_PATH", str(db_path))
    monkeypatch.setenv("FS_EXPLORER_AGENT_USE_INDEX", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_INDEXING", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_EMBEDDINGS", "0")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_METADATA", "0")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL", "https://local.test")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_MODEL", "local-model")
    (tmp_path / "first.txt").write_text("first")
    mcp_server._auto_refresh_index_if_needed(str(tmp_path))
    (tmp_path / "second.sh").write_text("second")
    calls: list[dict] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return json.dumps({"action": "final", "answer": "ok"})

    monkeypatch.setattr(openai_compatible_file_agent, "_chat_completion", fake_chat_completion)

    result = await _call_tool("agentic_explore", {"task": "find second"})

    assert result.is_error is False
    prompt = calls[0]["messages"][1]["content"]
    assert '"refreshed": true' in prompt
    assert '"new_files": [\n      "second.sh"\n    ]' in prompt
    assert mcp_server._index_staleness(str(tmp_path), str(db_path))["stale"] is False


def test_index_staleness_uses_extra_indexable_extensions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FS_EXPLORER_EXTRA_INDEXABLE_EXTENSIONS", "custom")
    (tmp_path / "config.custom").write_text("custom input")

    staleness = mcp_server._index_staleness(
        str(tmp_path),
        str(tmp_path / "missing.duckdb"),
    )

    assert staleness["live_files"] == 1
    assert staleness["new_files"] == ["config.custom"]


@pytest.mark.asyncio
async def test_agentic_explore_respects_auto_refresh_disabled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FS_EXPLORER_MCP_ROOT", str(tmp_path))
    monkeypatch.setenv("FS_EXPLORER_DB_PATH", str(tmp_path / "fs-explorer.duckdb"))
    monkeypatch.setenv("FS_EXPLORER_AGENT_USE_INDEX", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_ALLOW_INDEXING", "1")
    monkeypatch.setenv("FS_EXPLORER_MCP_AUTO_REFRESH_INDEX", "0")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_BASE_URL", "https://local.test")
    monkeypatch.setenv("FS_EXPLORER_OPENAI_COMPAT_MODEL", "local-model")
    (tmp_path / "note.txt").write_text("hello")
    calls: list[dict] = []

    def fake_chat_completion(**kwargs):
        calls.append(kwargs)
        return json.dumps({"action": "final", "answer": "ok"})

    monkeypatch.setattr(openai_compatible_file_agent, "_chat_completion", fake_chat_completion)

    result = await _call_tool("agentic_explore", {"task": "find hello"})

    assert result.is_error is False
    assert "Server-side index freshness check" not in calls[0]["messages"][1]["content"]
    assert not (tmp_path / "fs-explorer.duckdb").exists()
