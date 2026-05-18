#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tmpdir="${MLPCOPILOT_TUI_TEST_TMPDIR:-$(mktemp -d /tmp/mlpcopilot-tui.XXXXXX)}"
config="$tmpdir/config.json"
ws="$tmpdir/workspace"
template_config="${MLPCOPILOT_TUI_TEMPLATE_CONFIG:-$HOME/.mlpcopilot/config.json}"

echo "tmpdir=$tmpdir"
echo "config=$config"
echo "workspace=$ws"
echo "template_config=$template_config"

mkdir -p "$(dirname "$config")"
if [[ -f "$template_config" ]]; then
  cp "$template_config" "$config"
  echo "copied template config"
else
  echo "template config not found; using built-in defaults"
fi

uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp init \
  -c "$config" \
  -w "$ws"

if [[ -n "${MLPCOPILOT_TUI_MODEL:-}" || -n "${MLPCOPILOT_TUI_PROVIDER:-}" ]]; then
  python3 - <<'PY' "$config" "${MLPCOPILOT_TUI_MODEL:-}" "${MLPCOPILOT_TUI_PROVIDER:-}"
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
  echo "overrode model/provider from environment"
fi

python3 - <<'PY' "$config"
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
defaults = data.get("agents", {}).get("defaults", {})
print("model=" + str(defaults.get("model")))
print("provider=" + str(defaults.get("provider")))
PY

uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp projects create FeCH \
  --project-id proj_tui \
  --target-use-case "compressed liquid" \
  -c "$config"

uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp runs create proj_tui \
  --run-id run_tui \
  -c "$config"

backend="$ws/projects/proj_tui/runs/run_tui/backend/dpgen"

mkdir -p "$backend/iter.000000/00.train/000"
mkdir -p "$backend/iter.000000/01.model_devi"
mkdir -p "$backend/iter.000000/02.fp/task.000.000000"

printf '{}\n' > "$backend/param.json"
printf '{}\n' > "$backend/machine.json"
printf '0 0\n0 1\n0 5\n' > "$backend/record.dpgen"
printf 'step loss\n' > "$backend/iter.000000/00.train/000/lcurve.out"
printf '1\n' > "$backend/iter.000000/02.fp/candidate.out"

uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp runs sync-dpgen proj_tui run_tui \
  -c "$config"

cat <<EOF

TUI test workspace ready.

Expected TUI:
- Companion shows proj_tui / run_tui.
- Companion stage is iter_000000 / label.prepare / projected.
- Artifacts shows MLP run artifacts instead of workspace files.

To test refresh in another shell:
  backend="$backend"
  config="$config"
  printf '0 0\\n0 1\\n0 5\\n0 6\\n' > "\$backend/record.dpgen"
  uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot mlp runs sync-dpgen proj_tui run_tui -c "\$config"

Starting TUI...
EOF

uv --cache-dir /tmp/uv-cache run --extra dev python -m mlpcopilot tui -c "$config"
