#!/usr/bin/env python3
"""Manual smoke test for the FsExplorer MCP agent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TASK = "请扫描这个知识库，概述里面主要有哪些文献或资料，并列出你实际查看过的来源。"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _default_folder() -> str:
    return os.getenv(
        "FS_EXPLORER_MCP_ROOT",
        "~/.mlpcopilot/workspace/knowledge",
    )


def _build_payload(task: str, folder: str, max_steps: int) -> str:
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "manual-test", "version": "1"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "explore",
                "arguments": {
                    "task": task,
                    "folder": folder,
                    "max_steps": max_steps,
                },
            },
        },
    ]
    return "\n".join(json.dumps(req, ensure_ascii=False) for req in requests) + "\n"


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", default=_default_folder(), help="Knowledge folder.")
    parser.add_argument("--task", default=DEFAULT_TASK, help="Question for the agent.")
    parser.add_argument("--max-steps", type=int, default=8, help="Agent step limit.")
    args = parser.parse_args()

    payload = _build_payload(args.task, args.folder, args.max_steps)
    cmd = ["uv", "run", "fs-explorer-mcp"]
    completed = subprocess.run(
        cmd,
        input=payload,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
