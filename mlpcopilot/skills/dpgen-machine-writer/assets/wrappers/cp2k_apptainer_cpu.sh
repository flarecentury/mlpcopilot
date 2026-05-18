#!/usr/bin/env bash
set -euo pipefail

SIF="${CP2K_SIF:-${MLPCOPILOT_SIF_ROOT:-$PWD/sifs}/cp2k/cp2k_v20261.sif}"
BIND_PATHS="${CP2K_BIND_PATHS:-$PWD:$PWD}"
CP2K_BIN="${CP2K_BIN:-cp2k.psmp}"

[[ -f "$SIF" ]] || { echo "missing SIF: $SIF" >&2; exit 127; }
command -v apptainer >/dev/null 2>&1 || { echo "apptainer not found" >&2; exit 127; }

exec apptainer exec --no-home --bind "$BIND_PATHS" --pwd "$PWD" "$SIF" "$CP2K_BIN" "$@"
