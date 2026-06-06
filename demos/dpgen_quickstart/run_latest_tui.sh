#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

source_dir="${MLPCOPILOT_LATEST_DPGEN_DIR:-}"
project_id="${MLPCOPILOT_LATEST_PROJECT_ID:-latest_dpgen}"
run_id="${MLPCOPILOT_LATEST_RUN_ID:-iter0}"
tmpdir="${MLPCOPILOT_LATEST_TMPDIR:-$(mktemp -d /tmp/mlpcopilot-latest-tui.XXXXXX)}"
config="${MLPCOPILOT_LATEST_CONFIG:-$tmpdir/config.json}"
workspace="${MLPCOPILOT_LATEST_WORKSPACE:-$tmpdir/workspace}"
template_config="${MLPCOPILOT_LATEST_TEMPLATE_CONFIG:-$HOME/.mlpcopilot/config.json}"
start_tui="${MLPCOPILOT_LATEST_START_TUI:-1}"

usage() {
  cat <<'EOF'
Usage: bash demos/dpgen_quickstart/run_latest_tui.sh [--no-tui]

Environment:
  MLPCOPILOT_LATEST_DPGEN_DIR         Required DP-GEN backend directory.
  MLPCOPILOT_LATEST_TMPDIR            Temporary root to reuse.
  MLPCOPILOT_LATEST_CONFIG            Config path.
  MLPCOPILOT_LATEST_WORKSPACE         Workspace path.
  MLPCOPILOT_LATEST_TEMPLATE_CONFIG   Config template. Default: ~/.mlpcopilot/config.json
  MLPCOPILOT_LATEST_PROJECT_ID        Project id. Default: latest_dpgen
  MLPCOPILOT_LATEST_RUN_ID            Run id. Default: iter0
  MLPCOPILOT_LATEST_MODEL             Optional model override.
  MLPCOPILOT_LATEST_PROVIDER          Optional provider override.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
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

if [[ -z "$source_dir" ]]; then
  echo "Set MLPCOPILOT_LATEST_DPGEN_DIR to a DP-GEN backend directory." >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$source_dir" ]]; then
  echo "DP-GEN source directory not found: $source_dir" >&2
  exit 1
fi

run_mlpcopilot() {
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot "$@"
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

echo "MLP Copilot latest DP-GEN TUI smoke"
echo "source=$source_dir"
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

if [[ -n "${MLPCOPILOT_LATEST_MODEL:-}" || -n "${MLPCOPILOT_LATEST_PROVIDER:-}" ]]; then
  python3 - <<'PY' "$config" "${MLPCOPILOT_LATEST_MODEL:-}" "${MLPCOPILOT_LATEST_PROVIDER:-}"
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
  run_mlpcopilot mlp projects create "Latest DP-GEN" \
    --project-id "$project_id" \
    --target-use-case "inspect latest DP-GEN iteration runtime health" \
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
cp -a "$source_dir" "$backend"

if [[ ! -f "$backend/record.dpgen" ]]; then
  printf '0 8\n' > "$backend/record.dpgen"
  echo "created fallback record.dpgen: 0 8"
fi

run_mlpcopilot mlp runs sync-dpgen "$project_id" "$run_id" -c "$config"

python3 - <<'PY' "$config" "$workspace" "$project_id" "$run_id"
import json
import sys
from collections import Counter
from pathlib import Path

config = Path(sys.argv[1])
workspace = Path(sys.argv[2])
project_id = sys.argv[3]
run_id = sys.argv[4]
run_dir = workspace / "projects" / project_id / "runs" / run_id
defaults = json.loads(config.read_text(encoding="utf-8")).get("agents", {}).get("defaults", {})
rows = []
for line in (run_dir / "artifacts.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
        rows.append(json.loads(line))
companion = json.loads((run_dir / "ui" / "companion.state.json").read_text(encoding="utf-8"))
print("model=" + str(defaults.get("model")))
print("provider=" + str(defaults.get("provider")))
print("artifacts=" + str(len(rows)))
print("kind_counts=" + json.dumps(dict(sorted(Counter(row.get("kind") for row in rows).items())), ensure_ascii=False))
print("health=" + json.dumps(companion.get("health"), ensure_ascii=False))
PY

cat <<EOF

Ready.

TUI should show:
- Companion: Latest DP-GEN / $run_id
- Artifacts: config, templates, train/model-devi/fp stages, selection reports, fp outputs

Manual commands:
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp runs sync-dpgen $project_id $run_id -c "$config"
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp artifacts inspect $project_id $run_id iter.000000/02.fp -c "$config"

EOF

if [[ "$start_tui" == "1" ]]; then
  run_mlpcopilot tui -c "$config"
else
  echo "Skipping TUI. Workspace is ready at $workspace."
fi
