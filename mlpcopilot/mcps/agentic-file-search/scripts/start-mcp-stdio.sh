#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${AGENTIC_FILE_SEARCH_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"

exec uv --directory "$PROJECT_DIR" run agentic-file-search-mcp
