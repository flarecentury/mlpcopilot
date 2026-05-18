#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd "$script_dir/../.." && pwd)"
repo_root="$(cd "$skill_dir/../../.." && pwd)"

source_project="${SOURCE_PROJECT:-}"
workdir="${WORKDIR:-$(mktemp -d /tmp/mlpcopilot-dpgen-machine-smoke.XXXXXX)}"
timeout_seconds="${TIMEOUT_SECONDS:-60}"
max_log_chars="${MAX_LOG_CHARS:-4000}"

bundle="$skill_dir/assets/bundles/local-gpu-cp2k"
fixture="$skill_dir/assets/fixtures/dsh-soap"

mkdir -p "$workdir"
cp "$bundle/machine.json" "$workdir/machine.json"
cp -a "$bundle/wrappers" "$workdir/wrappers"
cp "$fixture/param.json" "$workdir/param.json"
cp "$fixture/lmp_NVT.in" "$fixture/lmp_tfMC.in" "$fixture/template_d3.inp" "$workdir/"
mkdir -p "$workdir/remote/train" "$workdir/remote/model_devi" "$workdir/remote/fp"

if [[ -n "$source_project" ]]; then
  for path in init_data export export1 export_mix export1_mix; do
    if [[ -e "$source_project/$path" && ! -e "$workdir/$path" ]]; then
      ln -s "$source_project/$path" "$workdir/$path"
    fi
  done
fi

export PYTHONPATH="$repo_root/mlpcopilot/mcps/mlp_training_controller_mcp/src${PYTHONPATH:+:$PYTHONPATH}"

python - "$workdir" "$timeout_seconds" "$max_log_chars" <<'PY'
import json
import sys
from pathlib import Path

from mlp_training_controller_mcp.backends.dpgen import DPGenBackend

workdir = Path(sys.argv[1]).resolve()
timeout_seconds = int(sys.argv[2])
max_log_chars = int(sys.argv[3])

payload = json.loads(
    DPGenBackend().validate_machine_runtime(
        machine_path=str(workdir / "machine.json"),
        project_path=str(workdir),
        timeout_seconds=timeout_seconds,
        max_log_chars=max_log_chars,
        output_path=str(workdir / "machine_runtime_validation.json"),
    )
)
print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
print(f"\nworkdir: {workdir}")
print(f"report: {workdir / 'machine_runtime_validation.json'}")
raise SystemExit(0 if payload.get("status") == "success" else 1)
PY
