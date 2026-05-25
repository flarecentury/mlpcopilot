# Evidence Checklist

Use this checklist before claiming that the cluster OOD question is answered.

## Required Provenance

- Training-domain summary exists and states that the dominant data are periodic
  bulk and surface systems.
- Checkpoint path and hash are recorded.
- Target cluster family, adsorbate count, and temperature windows are recorded.
- Reference method and software version are recorded for the cluster trajectories.

## Required Benchmark Evidence

- Finite-cluster test trajectories are stored by path or artifact reference.
- Reference energies and forces are available for the scored frames.
- Postprocessing script or equivalent notebook is versioned by path.
- Output metrics are written to files, not only shown in chat.

## Minimum Metrics

- Force RMSE on the chosen OOD slices.
- Relative energy fluctuation RMSE after any justified equilibration skip.
- Per-slice or per-configuration summary so size and temperature trends are visible.

## Strongly Recommended

- Worst-frame inspection for high-force or near-dissociation frames.
- Separate summaries for `700 K` and `1200 K`.
- Separate summaries for at least two cluster sizes.
- Explicit note on what remains untested, such as other stoichiometries or
  longer trajectories.

## Do Not Claim

- Do not claim universal transferability from one cluster family.
- Do not claim coverage completeness without dedicated coverage tooling.
- Do not claim deployment readiness without approval and written acceptance criteria.
