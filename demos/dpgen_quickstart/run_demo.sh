#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

project_id="${MLPCOPILOT_DEMO_PROJECT_ID:-demo_mlp}"
run_id="${MLPCOPILOT_DEMO_RUN_ID:-run_demo}"
tmpdir="${MLPCOPILOT_DEMO_TMPDIR:-$(mktemp -d /tmp/mlpcopilot-dpgen-demo.XXXXXX)}"
config="${MLPCOPILOT_DEMO_CONFIG:-$tmpdir/config.json}"
workspace="${MLPCOPILOT_DEMO_WORKSPACE:-$tmpdir/workspace}"
template_config="${MLPCOPILOT_DEMO_TEMPLATE_CONFIG:-$HOME/.mlpcopilot/config.json}"
playback="${MLPCOPILOT_DEMO_PLAYBACK:-1}"
playback_delay="${MLPCOPILOT_DEMO_PLAYBACK_DELAY:-1}"
start_tui="${MLPCOPILOT_DEMO_START_TUI:-1}"
if [[ "${MLPCOPILOT_DEMO_NO_TUI:-0}" == "1" ]]; then
  start_tui=0
fi

usage() {
  cat <<'EOF'
Usage: bash demos/dpgen_quickstart/run_demo.sh [--no-tui] [--no-playback]

Environment:
  MLPCOPILOT_DEMO_TEMPLATE_CONFIG  Config template to copy before mlp init.
  MLPCOPILOT_DEMO_MODEL            Optional model override.
  MLPCOPILOT_DEMO_PROVIDER         Optional provider override.
  MLPCOPILOT_DEMO_TMPDIR           Reuse a specific temporary root.
  MLPCOPILOT_DEMO_CONFIG           Use a specific config path.
  MLPCOPILOT_DEMO_WORKSPACE        Use a specific workspace path.
  MLPCOPILOT_DEMO_PLAYBACK_DELAY   Seconds between projected DP-GEN state updates.
  MLPCOPILOT_DEMO_NO_TUI           Set to 1 to prepare/sync only.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-tui)
      start_tui=0
      ;;
    --no-playback)
      playback=0
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

write_record_until() {
  local task="$1"
  local record_file="$2"
  : > "$record_file"
  local idx
  for idx in $(seq 0 "$task"); do
    printf '0 %s\n' "$idx" >> "$record_file"
  done
}

sync_dpgen() {
  run_mlpcopilot mlp runs sync-dpgen "$project_id" "$run_id" -c "$config" >/dev/null
}

activate_run() {
  python3 - <<'PY' "$workspace" "$project_id" "$run_id"
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

advance_playback() {
  local delay="$1"
  local task
  for task in 1 2 3 4 5 6 7 8; do
    sleep "$delay"
    write_record_until "$task" "$backend/record.dpgen"
    sync_dpgen 2>>"$tmpdir/playback.stderr.log" || true
  done
}

echo "MLP Copilot DP-GEN quickstart demo"
echo "tmpdir=$tmpdir"
echo "config=$config"
echo "workspace=$workspace"
echo "project_id=$project_id"
echo "run_id=$run_id"

mkdir -p "$(dirname "$config")"
if [[ -f "$template_config" && ! -f "$config" ]]; then
  cp "$template_config" "$config"
  echo "copied template config: $template_config"
fi

run_mlpcopilot mlp init -c "$config" -w "$workspace"

if [[ -n "${MLPCOPILOT_DEMO_MODEL:-}" || -n "${MLPCOPILOT_DEMO_PROVIDER:-}" ]]; then
  python3 - <<'PY' "$config" "${MLPCOPILOT_DEMO_MODEL:-}" "${MLPCOPILOT_DEMO_PROVIDER:-}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
model = sys.argv[2].strip()
provider = sys.argv[3].strip()
data = json.loads(path.read_text(encoding="utf-8"))
defaults = data.setdefault("agents", {}).setdefault("defaults", {})
if model:
    defaults["model"] = model
if provider:
    defaults["provider"] = provider
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
fi

if [[ ! -f "$workspace/projects/$project_id/project.json" ]]; then
  run_mlpcopilot mlp projects create "FeCH quickstart" \
    --project-id "$project_id" \
    --target-use-case "mock active learning loop for compressed liquid coverage" \
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
mkdir -p "$backend"
cp -a "$repo_root/demos/dpgen_quickstart/fixture/." "$backend/"

write_record_until 0 "$backend/record.dpgen"
sync_dpgen

python3 - <<'PY' "$config"
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
defaults = data.get("agents", {}).get("defaults", {})
print("model=" + str(defaults.get("model")))
print("provider=" + str(defaults.get("provider")))
PY

cat <<EOF

Demo workspace ready.

Expected TUI:
- Companion shows $project_id / $run_id.
- Artifacts shows DP-GEN-shaped config, training, model deviation, label, and dataset artifacts.
- If playback is enabled, record.dpgen advances every second and UI state revisions increase.

Useful commands:
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp artifacts inspect $project_id $run_id record.dpgen -c "$config"
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp runs sync-dpgen $project_id $run_id -c "$config"

EOF

playback_pid=""
if [[ "$playback" == "1" ]]; then
  if [[ "$start_tui" == "1" ]]; then
    advance_playback "$playback_delay" &
    playback_pid="$!"
    echo "playback_pid=$playback_pid"
  else
    advance_playback "${MLPCOPILOT_DEMO_NO_TUI_PLAYBACK_DELAY:-0}"
  fi
fi

if [[ "$start_tui" == "1" ]]; then
  trap '[[ -n "${playback_pid:-}" ]] && kill "$playback_pid" 2>/dev/null || true' EXIT
  run_mlpcopilot tui -c "$config"
else
  echo "Skipping TUI. Demo state is ready at $workspace."
fi
