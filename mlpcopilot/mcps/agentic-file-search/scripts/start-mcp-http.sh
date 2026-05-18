#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${AGENTIC_FILE_SEARCH_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HOST="${FS_EXPLORER_MCP_HTTP_HOST:-127.0.0.1}"
PORT="${FS_EXPLORER_MCP_HTTP_PORT:-8765}"
PATH_PREFIX="${FS_EXPLORER_MCP_HTTP_PATH:-/mcp}"

exec uv --directory "$PROJECT_DIR" run agentic-file-search-mcp-http \
  --host "$HOST" \
  --port "$PORT" \
  --path "$PATH_PREFIX"
