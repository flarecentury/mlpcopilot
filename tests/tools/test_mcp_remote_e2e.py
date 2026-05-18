"""End-to-end MCP remote transport tests with a real local server."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp.server.fastmcp")
pytest.importorskip("uvicorn")

from mlpcopilot.agent.tools.mcp import connect_mcp_servers
from mlpcopilot.agent.tools.registry import ToolRegistry
from mlpcopilot.config.schema import MCPServerConfig


@pytest.mark.asyncio
async def test_streamable_http_connects_to_real_fastmcp_server(tmp_path: Path) -> None:
    port = _free_port()
    server_script = _write_fastmcp_server(tmp_path)
    process = subprocess.Popen(
        [sys.executable, str(server_script)],
        env={**os.environ, "MLPCOPILOT_TEST_MCP_PORT": str(port)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        await _wait_for_tcp("127.0.0.1", port, process)
        registry = ToolRegistry()
        stacks = await connect_mcp_servers(
            {
                "remote": MCPServerConfig(
                    type="streamableHttp",
                    url=f"http://127.0.0.1:{port}/mcp",
                )
            },
            registry,
        )
        try:
            assert set(stacks) == {"remote"}
            assert registry.tool_names == ["mcp_remote_ping"]
            assert await registry.execute("mcp_remote_ping", {"name": "codex"}) == "pong codex"
        finally:
            for stack in stacks.values():
                await stack.aclose()
    finally:
        _terminate_process(process)


def _write_fastmcp_server(tmp_path: Path) -> Path:
    path = tmp_path / "remote_mcp_server.py"
    path.write_text(
        textwrap.dedent(
            """
            import os

            import uvicorn
            from mcp.server.fastmcp import FastMCP

            mcp = FastMCP("remote-e2e")


            @mcp.tool()
            def ping(name: str = "world") -> str:
                return f"pong {name}"


            if __name__ == "__main__":
                uvicorn.run(
                    mcp.streamable_http_app(),
                    host="127.0.0.1",
                    port=int(os.environ["MLPCOPILOT_TEST_MCP_PORT"]),
                    log_level="warning",
                )
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"local TCP sockets are not available: {exc}")


async def _wait_for_tcp(
    host: str,
    port: int,
    process: subprocess.Popen[str],
    *,
    timeout: float = 10.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(
                f"MCP server exited early with code {process.returncode}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            )
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except OSError as exc:
            last_error = exc
            await asyncio.sleep(0.05)
            continue
        writer.close()
        await writer.wait_closed()
        return
    raise AssertionError(f"MCP server did not open {host}:{port}: {last_error}")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
