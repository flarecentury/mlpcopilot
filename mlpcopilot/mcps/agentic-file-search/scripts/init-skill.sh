#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

KNOWLEDGE_ROOT="${FS_EXPLORER_MCP_ROOT:-$HOME/.mlpcopilot/workspace/knowledge}"
DB_PATH="${FS_EXPLORER_DB_PATH:-$KNOWLEDGE_ROOT/fs-explorer.duckdb}"
BASE_URL="${FS_EXPLORER_OPENAI_COMPAT_BASE_URL:-http://127.0.0.1:8000/v1}"
MODEL="${FS_EXPLORER_OPENAI_COMPAT_MODEL:-local-model}"
API_KEY="${FS_EXPLORER_OPENAI_COMPAT_API_KEY:-}"
ENV_FILE="${FS_EXPLORER_SKILL_ENV_FILE:-$PROJECT_DIR/.env}"

mkdir -p "$KNOWLEDGE_ROOT"

if [[ -e "$ENV_FILE" ]]; then
  echo "Keeping existing $ENV_FILE"
else
  cat > "$ENV_FILE" <<EOF
FS_EXPLORER_MCP_ROOT=$KNOWLEDGE_ROOT
FS_EXPLORER_DB_PATH=$DB_PATH
FS_EXPLORER_OPENAI_COMPAT_BASE_URL=$BASE_URL
FS_EXPLORER_OPENAI_COMPAT_MODEL=$MODEL
FS_EXPLORER_OPENAI_COMPAT_API_KEY=$API_KEY
FS_EXPLORER_AGENT_USE_INDEX=1
FS_EXPLORER_MCP_ALLOW_INDEXING=1
FS_EXPLORER_MCP_AUTO_REFRESH_INDEX=1
FS_EXPLORER_MCP_ALLOW_EMBEDDINGS=0
FS_EXPLORER_MCP_ALLOW_METADATA=0
FS_EXPLORER_MCP_DISCOVER_SCHEMA=0
FS_EXPLORER_MCP_INDEX_WORKERS=4
FS_EXPLORER_AGENT_TIMEOUT=120
FS_EXPLORER_MCP_TRANSPORT=streamable-http
FS_EXPLORER_MCP_HTTP_HOST=127.0.0.1
FS_EXPLORER_MCP_HTTP_PORT=8765
FS_EXPLORER_MCP_HTTP_PATH=/mcp
EOF
  echo "Wrote $ENV_FILE"
fi

cat <<EOF
Agentic File Search MCP initialized.

Knowledge root:
  $KNOWLEDGE_ROOT

Stdio MCP command:
  uv --directory "$PROJECT_DIR" run agentic-file-search-mcp

Streamable HTTP MCP command:
  $PROJECT_DIR/scripts/start-mcp-http.sh

MLP Copilot MCP config snippet:
{
  "tools": {
    "mcpServers": {
      "agentic-file-search": {
        "command": "uv",
        "args": ["--directory", "$PROJECT_DIR", "run", "agentic-file-search-mcp"],
        "enabledTools": ["agentic_explore"],
        "toolTimeout": 120
      }
    }
  }
}
EOF
