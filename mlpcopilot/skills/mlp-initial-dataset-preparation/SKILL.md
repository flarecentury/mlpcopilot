---
name: mlp-initial-dataset-preparation
description: Use this skill when helping users prepare an initial training dataset for machine-learning-potential workflows before DP-GEN or active learning. It guides target-domain scoping, seed-structure selection, AIMD/static DFT labeling plans, dataset conversion, evidence tracking, and handoff into DP-GEN `init_data_sys` without inventing metrics or hiding scientific assumptions.
---

# MLP Initial Dataset Preparation

Use this skill when the user asks how to prepare, audit, or organize an initial MLP training dataset before active learning.

The goal is not to claim the initial dataset is complete. The goal is to produce a small, traceable, chemically relevant seed dataset that can support the first model and the first active-learning loop.

## Core Rules

- Treat initial data as a seed, not as final coverage.
- Ask for target use case before proposing structures.
- Move structures, trajectories, labels, and datasets by file path or artifact reference, not pasted coordinates.
- Numerical labels must come from DFT/AIMD outputs or retained tool artifacts, not LLM judgment.
- High-cost DFT/AIMD job creation or execution must be approval-gated.
- Do not hard-code the Al/O example as universal. Use it only as a pattern for hierarchical dataset design.

## Required User Inputs

Collect these first:

1. Target chemistry and elements.
2. Intended deployment domain:
   - bulk
   - surface
   - interface
   - cluster
   - molecule/gas
   - liquid/amorphous
   - reaction or bond-breaking environment
3. Expected operating conditions:
   - temperature range
   - pressure range
   - ensemble
   - boundary condition: periodic, slab, isolated/non-periodic
4. Initial structure sources:
   - relaxed crystals
   - surfaces/slabs
   - defects
   - known intermediates
   - previous AIMD trajectories
   - user-provided POSCAR/extxyz/cif files
5. Labeling backend:
   - CP2K, VASP, Quantum ESPRESSO, ABACUS, other
6. Output format needed:
   - DeepMD raw/npy
   - extxyz
   - ASE database
   - DP-GEN `init_data_sys`
7. Compute budget:
   - number of DFT/AIMD jobs
   - max atoms per cell
   - max frames
   - walltime/queue constraints

## Recommended Workflow

### 1. Scope The Seed Dataset

Start from the target domain, then choose the simplest structures that still represent the physics.

For each system, record:

```text
system_id
composition
structure source
boundary condition
target role
labeling method
expected output path
```

Do not say "comprehensive" unless coverage evidence exists.

### 2. Choose Seed Structure Families

For a reactive material system, prefer a hierarchical seed:

1. Stable reference phases.
2. Simple molecules or gas species if relevant.
3. Low-index surfaces or interfaces.
4. Defects, vacancies, under-coordinated sites, or strained cells.
5. Early reaction/contact geometries.
6. Small finite clusters only if the deployment or validation domain needs them.

Case pattern from the Al/O reference workflow:

- Start with simple periodic bulk phases.
- Include separate simple species for pseudopotential/reference sanity.
- Add clean surface baselines.
- Add progressively harder surface or reactive configurations.
- Leave high-coverage, high-temperature, and non-periodic clusters for active learning or explicit OOD validation unless they are part of the intended initial domain.

### 3. Plan Initial AIMD Or Static DFT Labels

Use AIMD when the seed needs thermal distortions or early reaction dynamics.
Use static DFT when the seed is a curated set of relaxed/distorted structures.

For each planned trajectory or static batch, define:

```text
input_structure_path
backend
functional / basis / pseudopotential set
dispersion treatment
spin/charge if relevant
boundary condition
ensemble
temperature
timestep
number_of_steps
frame_stride
equilibration_skip
output_directory
```

Example pattern, not a default:

```text
bulk/surface seed AIMD:
  ensemble: NVT
  timestep: 0.5 fs
  temperatures: low / medium / high points spanning the intended domain
  retain: post-equilibration frames at a stride that avoids near-duplicate frames
```

For non-periodic clusters, explicitly record vacuum/cell treatment and Poisson solver settings if the backend requires them.

### 4. Parse And Convert Labels

For CP2K-like AIMD outputs, verify the numerical source files before conversion:

```text
position trajectory
force trajectory
energy file
main output/log
```

When parsing manually or through a tool, enforce:

- coordinates, forces, and energies have consistent frame counts;
- unit conversions are explicit;
- atom order is stable across frames;
- cell and PBC metadata are correct;
- failed or unconverged frames are excluded;
- any post-processing correction, such as dispersion, is recorded separately.

Preferred output:

```text
datasets/init/
  system_a/
    type.raw
    type_map.raw
    box.raw
    coord.raw
    energy.raw
    force.raw
    set.000/
  system_b/
  dataset_manifest.json
  labeling_protocol.md
  rejected_frames.jsonl
```

If using extxyz, require each frame to include energy, forces, cell, PBC, and species metadata.

### 5. Reduce Redundancy Before Training

Initial AIMD can overproduce similar frames. Avoid training the first model on many near-identical structures.

Recommended checks:

- remove duplicate frames;
- skip early equilibration frames when justified;
- thin frames by stride;
- group by source trajectory;
- use descriptor-based diversity filtering when available;
- preserve rare but relevant reactive or distorted frames.

Case pattern from the Al/O workflow:

- uncertain active-learning candidates were later filtered with SOAP-like structural similarity;
- descriptor filtering was used to reduce redundancy while retaining representative chemical environments.

Do not claim coverage from filtering alone. Filtering reduces redundancy; it does not prove domain completeness.

### 6. Split Train / Validation / Test

Create a split manifest instead of random ad hoc copying.

Minimum expectations:

```text
split_manifest.json
  train systems
  validation systems
  test systems
  split method
  random seed if used
  leakage checks performed
```

Prefer split by trajectory/source when possible. Avoid putting adjacent AIMD frames from the same trajectory into both train and test unless the user explicitly wants an interpolation-only test.

A common starting point is a train/validation/test split such as 8:1:1 or 9:1:1, but the split should be justified by dataset size and target use case.

### 7. Validate Dataset Before DP-GEN Handoff

Use dataset tools when available:

- `inspect_dataset`
- `validate_dataset_integrity`
- `build_dataset_validation_report`

Treat these as blocking until resolved:

- missing path;
- missing energy or force labels;
- inconsistent frame counts;
- wrong units;
- wrong atom order;
- missing cell/PBC metadata;
- inconsistent `type_map`;
- failed or unconverged DFT frames included as labels.

If only lightweight dataset tools are available, state that advanced checks such as unit consistency, structure sanity, duplicate detection, split leakage, and coverage analysis are not fully implemented unless another tool provides them.

### 8. Handoff To DP-GEN

For DP-GEN, prepare the initial dataset paths for `param.json`:

```json
{
  "init_data_prefix": "./",
  "init_data_sys": [
    "datasets/init/system_a",
    "datasets/init/system_b"
  ],
  "init_batch_size": ["auto", "auto"]
}
```

Also prepare exploration structures separately:

```json
{
  "sys_configs_prefix": "./",
  "sys_configs": [
    ["structures/surface/*.vasp"],
    ["structures/reactive_seed/*.vasp"]
  ],
  "sys_batch_size": ["auto", "auto"]
}
```

Before proposing a run start, validate:

- `init_data_sys` paths exist;
- `init_batch_size` length matches `init_data_sys`;
- `sys_configs` is two-dimensional;
- `sys_batch_size` length matches `sys_configs`;
- `type_map` order matches all datasets;
- backend templates and machine files exist.

## Response Pattern

When answering the user, produce:

1. A short diagnosis of what they already have.
2. A missing-input checklist.
3. A concrete initial dataset plan.
4. A directory layout.
5. A labeling/conversion plan.
6. A validation checklist.
7. A DP-GEN handoff snippet if appropriate.
8. Clear blockers and approval points.

## Do Not

- Do not invent DFT settings.
- Do not claim the initial seed covers all relevant chemistry.
- Do not use one fixed force-deviation threshold for every material system.
- Do not paste large structures or trajectory payloads into chat.
- Do not treat OOD validation trajectories as training data unless the user explicitly approves and provenance is recorded.
- Do not start expensive labeling jobs without approval.
