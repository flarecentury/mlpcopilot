#!/usr/bin/env bash
set -euo pipefail

MPI_RUN="${VASP_MPI_RUN:-/usr/bin/mpirun}"
VASP_BIN="${VASP_BIN:-vasp_std}"
VASP_NP="${VASP_NP:-8}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"

[[ -x "$MPI_RUN" ]] || { echo "missing or non-executable MPI launcher: $MPI_RUN" >&2; exit 127; }

exec "$MPI_RUN" -np "$VASP_NP" "$VASP_BIN"
