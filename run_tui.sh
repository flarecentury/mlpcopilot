#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_root"

workspace="${MLPCOPILOT_TUI_WORKSPACE:-$HOME/.mlpcopilot/workspace}"
config="${MLPCOPILOT_TUI_CONFIG:-$HOME/.mlpcopilot/config.json}"
project_id="${MLPCOPILOT_TUI_PROJECT_ID:-local_dpgen}"
run_id="${MLPCOPILOT_TUI_RUN_ID:-run_local}"
dpgen_dir="${MLPCOPILOT_TUI_DPGEN_DIR:-}"
dpgen_mode="${MLPCOPILOT_TUI_DPGEN_MODE:-symlink}"
session_id="${MLPCOPILOT_TUI_SESSION:-tui:local}"
start_tui=1
once=0

usage() {
  cat <<'EOF'
Usage: bash run_tui.sh [--dpgen-dir PATH] [--copy-dpgen] [--workspace PATH] [--config PATH] [--project-id ID] [--run-id ID] [--once] [--no-tui]

Environment:
  MLPCOPILOT_TUI_WORKSPACE   Workspace path. Default: ~/.mlpcopilot/workspace
  MLPCOPILOT_TUI_CONFIG      Config path. Default: ~/.mlpcopilot/config.json
  MLPCOPILOT_TUI_DPGEN_DIR   Existing DP-GEN workdir to link into the workspace run.
  MLPCOPILOT_TUI_DPGEN_MODE  symlink or copy. Default: symlink
  MLPCOPILOT_TUI_PROJECT_ID  Project id. Default: local_dpgen
  MLPCOPILOT_TUI_RUN_ID      Run id. Default: run_local
  MLPCOPILOT_TUI_SESSION     TUI session id. Default: tui:local

Examples:
  bash run_tui.sh
  bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir
  bash run_tui.sh --dpgen-dir /path/to/dpgen --copy-dpgen
  bash run_tui.sh --once
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dpgen-dir)
      dpgen_dir="${2:?missing path for --dpgen-dir}"
      shift
      ;;
    --copy-dpgen)
      dpgen_mode="copy"
      ;;
    --workspace|-w)
      workspace="${2:?missing path for --workspace}"
      shift
      ;;
    --config|-c)
      config="${2:?missing path for --config}"
      shift
      ;;
    --project-id)
      project_id="${2:?missing id for --project-id}"
      shift
      ;;
    --run-id)
      run_id="${2:?missing id for --run-id}"
      shift
      ;;
    --once)
      once=1
      ;;
    --no-tui)
      start_tui=0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

run_mlpcopilot() {
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot "$@"
}

activate_run() {
  python3 - "$workspace" "$project_id" "$run_id" <<'PY'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

workspace = Path(sys.argv[1])
project_id = sys.argv[2]
run_id = sys.argv[3]
project_path = workspace / "projects" / project_id / "project.json"
project = json.loads(project_path.read_text(encoding="utf-8"))
project["active_run_id"] = run_id
project["updated_at"] = datetime.now(tz=UTC).isoformat()
project_path.write_text(json.dumps(project, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
PY
}

mkdir -p "$(dirname "$config")" "$workspace"

echo "MLP Copilot TUI"
echo "workspace=$workspace"
echo "config=$config"

run_mlpcopilot mlp init -c "$config" -w "$workspace"

if [[ -n "$dpgen_dir" ]]; then
  if [[ ! -d "$dpgen_dir" ]]; then
    echo "DP-GEN directory not found: $dpgen_dir" >&2
    exit 1
  fi
  if [[ "$dpgen_mode" != "symlink" && "$dpgen_mode" != "copy" ]]; then
    echo "Invalid DP-GEN mode: $dpgen_mode (expected symlink or copy)" >&2
    exit 2
  fi
  if [[ ! -f "$workspace/projects/$project_id/project.json" ]]; then
    run_mlpcopilot mlp projects create "Local DP-GEN" \
      --project-id "$project_id" \
      --target-use-case "inspect local DP-GEN run state" \
      -c "$config"
  fi
  if [[ ! -f "$workspace/projects/$project_id/runs/$run_id/run.json" ]]; then
    run_mlpcopilot mlp runs create "$project_id" \
      --run-id "$run_id" \
      -c "$config"
  fi
  activate_run
  backend="$workspace/projects/$project_id/runs/$run_id/backend/dpgen"
  rm -rf "$backend"
  mkdir -p "$(dirname "$backend")"
  if [[ "$dpgen_mode" == "copy" ]]; then
    echo "copying DP-GEN workdir; this can be slow for large runs"
    cp -a "$dpgen_dir" "$backend"
  else
    ln -s "$(realpath "$dpgen_dir")" "$backend"
  fi
  if [[ ! -f "$backend/record.dpgen" ]]; then
    if [[ "$dpgen_mode" == "copy" ]]; then
      printf '0 0\n' > "$backend/record.dpgen"
    else
      echo "warning: linked DP-GEN workdir has no record.dpgen; projection will report it missing" >&2
    fi
  fi
  run_mlpcopilot mlp runs sync-dpgen "$project_id" "$run_id" -c "$config"
  echo "synced DP-GEN workdir ($dpgen_mode) at $backend"
fi

if [[ "$start_tui" != "1" ]]; then
  echo "Prepared workspace only."
  exit 0
fi

if [[ "$once" == "1" ]]; then
  run_mlpcopilot tui -c "$config" --session "$session_id" --once
else
  run_mlpcopilot tui -c "$config" --session "$session_id"
fi
