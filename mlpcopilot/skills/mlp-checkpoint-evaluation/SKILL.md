---
name: mlp-checkpoint-evaluation
description: Use this skill when inspecting MLP checkpoints, running DeePMD-kit v3 dp test, normalizing checkpoint metrics, comparing checkpoints, or checking checkpoint metrics against acceptance criteria. It guides use of mlp_model_eval_mcp tools and requires explicit evidence artifacts for all model-quality claims.
---

# MLP Checkpoint Evaluation

Use this skill when the user asks whether an MLP checkpoint is acceptable, wants to compare checkpoints, needs a checkpoint metrics report, or wants energy/force predictions for ASE-readable structures.

Core boundary:

- Model-evaluation MCP tools produce or ingest checkpoint evidence.
- This skill organizes the evaluation workflow and communicates risk.
- Do not invent energy, force, stress, stability, or transferability metrics.
- Do not say inference or benchmark evaluation ran unless the active MCP tool actually ran it.
- Move checkpoints, datasets, trajectories, and metrics by path or artifact reference.
- Use DeePMD-kit v3 semantics. Prefer `dp test` for benchmark sets; do not use old dpkit assumptions or obsolete model suffix rules.

## Workflow

1. Identify decision scope.

Ask for the checkpoint path, target dataset or benchmark path, target use case, acceptance criteria, and whether metrics have already been computed.

2. Inspect checkpoint identity.

Call `inspect_checkpoint` before comparison or promotion. Record path, file/directory kind, recognized checkpoint files, size, and hash.

3. Choose metrics source.

If the user has a JSON/YAML metrics artifact, call `build_checkpoint_metrics` to create a normalized evidence artifact with source hashes.

If benchmark execution is needed and approved, call `run_deepmd_test`. This uses the DeePMD-kit v3 CLI shape:

```text
dp [--backend BACKEND] test --model CHECKPOINT --system DATASET --numb-test N --detail-file PREFIX
dp [--backend BACKEND] test --model CHECKPOINT --valid-data input.json --head HEAD
```

Supported data sources are `system`, `datafile`, `train-data`, and `valid-data`. Use `backend` only when needed; v3 can auto-detect from model suffix and backend registry.

4. Predict ASE-readable structures.

For one structure file, call `predict_energy_force`. For a directory of structures, call `batch_predict`. These tools use ASE `read` plus the DeePMD-kit v3 ASE calculator:

```python
from ase.io import read
from deepmd.calculator import DP

atoms = read(path)
atoms.calc = DP(model=checkpoint_path, head=head)
energy = atoms.get_potential_energy()
forces = atoms.get_forces()
```

Use `structure_format` when ASE auto-detection is ambiguous. Use `frame_index` for multi-frame files. Full forces are written to artifacts; do not paste large force arrays in chat.

5. Check checkpoint against a dataset.

Call `validate_checkpoint_on_dataset` with a checkpoint path, dataset path, and metrics config or metrics artifact path. If metrics are missing and the user approved execution, set `run_if_metrics_missing=true` and provide the same DeePMD-kit v3 options as `run_deepmd_test`.

6. Compare checkpoints.

Call `compare_checkpoints` when two checkpoints and a metrics config are available. If no metrics config is available, treat the result as metadata-only comparison.

7. Decide next action.

Possible recommendations:

- Accept metadata only as provenance evidence, not quality evidence.
- Request or schedule benchmark inference when metrics are missing.
- Reject or hold a checkpoint when available metrics fail acceptance criteria.
- Promote only after required metrics, dataset hashes, and human approval are present.

## Tool Selection

- Checkpoint provenance: `inspect_checkpoint`
- DeePMD-kit v3 benchmark execution: `run_deepmd_test`
- Single ASE-readable structure prediction: `predict_energy_force`
- Directory or multi-file ASE-readable prediction: `batch_predict`
- Metrics artifact normalization: `build_checkpoint_metrics`
- Criteria check with existing or freshly executed metrics: `validate_checkpoint_on_dataset`
- Two-checkpoint comparison: `compare_checkpoints`

`run_deepmd_test` defaults to a short timeout and writes log, metrics JSON, and `dp test` detail files. For GPU/container execution, pass an audited wrapper or command prefix through `dp_command`, for example a local wrapper that runs the correct DeePMD-kit 3.1.x SIF.

## Response Rules

- Separate provenance evidence from quality evidence.
- Mention whether `inference_executed` is true or false.
- Cite metrics artifact paths and hashes when available.
- If metrics are missing, say the result is blocked or metadata-only.
- Never claim deployment readiness without acceptance criteria, benchmark artifacts, and an approval decision.
