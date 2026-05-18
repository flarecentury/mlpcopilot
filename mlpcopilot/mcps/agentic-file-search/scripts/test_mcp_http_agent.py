#!/usr/bin/env python3
"""Manual Streamable HTTP smoke test for the FsExplorer MCP agent.

Start the server first:

    uv run fs-explorer-mcp-http

Then run this script from the project root.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASK = "请扫描这个知识库，概述里面主要有哪些文献或资料，并列出你实际查看过的来源。"
DEFAULT_URL = "http://127.0.0.1:8765/mcp"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _default_folder() -> str:
    return os.getenv(
        "FS_EXPLORER_MCP_ROOT",
        "~/.mlpcopilot/workspace/knowledge",
    )


def _parse_response(body: str, content_type: str) -> dict:
    if "text/event-stream" not in content_type:
        return json.loads(body)

    data_lines = []
    for line in body.splitlines():
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").strip())
    if not data_lines:
        return {"raw": body}
    return json.loads("\n".join(data_lines))


def _post(
    url: str,
    payload: dict,
    *,
    method: str,
    name: str | None = None,
    session_id: str | None = None,
) -> tuple[dict, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    if session_id is not None:
        headers["Mcp-Session-Id"] = session_id
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        body = response.read().decode("utf-8")
        next_session_id = response.headers.get("Mcp-Session-Id") or session_id
        if response.status == 202:
            return {"status": 202}, next_session_id
        return (
            _parse_response(body, response.headers.get("Content-Type", "")),
            next_session_id,
        )


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP HTTP endpoint.")
    parser.add_argument("--folder", default=_default_folder(), help="Knowledge folder.")
    parser.add_argument("--task", default=DEFAULT_TASK, help="Question for the agent.")
    parser.add_argument("--max-steps", type=int, default=8, help="Agent step limit.")
    args = parser.parse_args()

    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "manual-http-test", "version": "1"},
        },
    }
    explore = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "explore",
            "arguments": {
                "task": args.task,
                "folder": args.folder,
                "max_steps": args.max_steps,
            },
        },
    }
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}

    try:
        init_result, session_id = _post(args.url, initialize, method="initialize")
        print(
            json.dumps(
                init_result,
                ensure_ascii=False,
            )
        )
        _post(
            args.url,
            initialized,
            method="notifications/initialized",
            session_id=session_id,
        )
        explore_result, _ = _post(
            args.url,
            explore,
            method="tools/call",
            name="explore",
            session_id=session_id,
        )
        print(
            json.dumps(
                explore_result,
                ensure_ascii=False,
            )
        )
    except urllib.error.URLError as exc:
        print(f"HTTP MCP request failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
