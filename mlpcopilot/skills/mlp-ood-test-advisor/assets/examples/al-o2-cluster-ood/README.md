# Al/O2 Cluster OOD Example

This example package shows how to use `mlp-ood-test-advisor` for a concrete
domain-shift question:

- training domain: mostly periodic `bulk` and `surface` Al/O data
- target domain: larger finite `Al_n + mO2` clusters
- validation mode: CP2K AIMD reference trajectories plus MLP postprocessing

The package is intentionally small. It provides a worked example structure,
not a full benchmark dataset.

Included:

- `case.yaml`: structured project inputs for the OOD planning step
- `decision-question.md`: the decision statement the OOD test should answer
- `ood-slices.yaml`: recommended slice definitions for this case
- `evidence-checklist.md`: minimum evidence needed before making claims
- `expected-artifacts.md`: artifact expectations and naming suggestions
- `sample-ood-plan.md`: example output shape for the advisor skill
- `cp2k/Al_cluster_aimd_no_pbc_template.inp`: isolated finite-cluster CP2K MD template
- `scripts/setup_tasks.py`: example task generator for finite-cluster AIMD cases
- `scripts/postprocess.py`: example postprocessing script for force and energy-fluctuation comparison

Default example scope:

- temperatures: `700 K` and `1200 K`
- cluster families: `Al13`, `Al55`, `Al79`, `Al147`, `Al309`
- adsorbate counts: `1`, `2`, `4`, `6` `O2`

Generated helper outputs from the example scripts:

- `task_manifest.json` from `setup_tasks.py`
- `metrics/force_metrics.json` from `postprocess.py`
- `metrics/energy_fluctuation_metrics.json` from `postprocess.py`
- `metrics/metrics_summary.txt` from `postprocess.py`
- `plots/force_parity.png` and `plots/energy_delta.png` from `postprocess.py`
- `reports/ood_summary.md` from `postprocess.py`

Not included:

- large trajectories
- precomputed pickle caches
- project-private absolute paths
- cluster geometries generated from local-only data

Use this asset pack as a starting point when you need to:

- show how `bulk/surface -> cluster` is an OOD question
- explain which validation slices matter for finite-cluster deployment
- define the minimum evidence contract before claiming transferability
