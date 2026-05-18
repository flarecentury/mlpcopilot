#!/usr/bin/env bash
set -euo pipefail

SIF="${DP_SIF:-${MLPCOPILOT_SIF_ROOT:-$PWD/sifs}/dp/deepmd-kit_3.1.3_cuda.sif}"
BIND_PATHS="${DP_BIND_PATHS:-$PWD:$PWD}"

[[ -f "$SIF" ]] || { echo "missing GPU DeePMD-kit SIF: $SIF" >&2; exit 127; }
command -v apptainer >/dev/null 2>&1 || { echo "apptainer not found" >&2; exit 127; }

exec apptainer exec --nv --no-home --bind "$BIND_PATHS" --pwd "$PWD" "$SIF" dp "$@"
