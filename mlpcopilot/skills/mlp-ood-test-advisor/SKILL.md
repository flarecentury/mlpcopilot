---
name: mlp-ood-test-advisor
description: Use this skill when the user wants project-specific out-of-domain or dataset-gap testing advice for machine-learning-potential workflows. It proposes OOD validation slices, evidence artifacts, and decision gates without pretending that one fixed chemistry checklist can cover every case.
---

# MLP OOD Test Advisor

Use this skill when the user asks how to test OOD behavior, dataset gaps, reviewer-requested challenge structures, finite clusters, phase/composition extrapolation, or deployment-boundary risks for an MLP.

Core boundary:

- This skill gives project-specific OOD test advice and evidence requirements.
- It does not execute coverage algorithms or declare a model robust.
- Do not apply a fixed universal validation checklist; chemistry, phase space, and deployment workflow decide the useful OOD slices.
- Metrics must come from MCP artifacts such as dataset reports, checkpoint benchmark reports, `dp test` outputs, ASE/DeepMD predictions, or user-provided reference calculations.
- Large structures, trajectories, descriptors, and logs must stay in files or artifact references.

## Required Inputs

Collect or mark missing:

- Target use case: composition, phases, temperature/pressure/strain window, ensemble, property of interest, and deployment workflow.
- In-domain evidence: training/validation dataset paths, DP-GEN run id, current iteration, and any dataset validation reports.
- Candidate checkpoint: checkpoint path, model family/backend, existing benchmark metrics, and acceptance criteria.
- Suspected OOD sources: reviewer structures, finite clusters, surfaces/interfaces, defects, high-energy states, reaction paths, unusual stoichiometries, failed DP-GEN clusters, or production failures.
- Reference budget: available DFT/ab initio calculations, CPU/GPU/HPC limits, walltime, and maximum number of new labels.
- Decision owner: who approves extra labeling, checkpoint promotion, or deployment.

## Workflow

1. Define the OOD question.

Convert the request into a decision statement, for example: whether the checkpoint is usable for a stated high-temperature NVT window, a finite cluster family, or a composition boundary.

2. Inventory evidence.

Use available tools when present:

- Dataset: `inspect_dataset`, `validate_dataset_integrity`, `build_dataset_validation_report`
- Training: `inspect_training_project`, `get_training_status`, `list_training_iterations`, `collect_training_logs`
- Checkpoint: `inspect_checkpoint`, `run_deepmd_test`, `validate_checkpoint_on_dataset`, `build_checkpoint_benchmark_report`

For current DP-GEN state, call a fresh training-controller status/evidence tool in the current turn unless a fresh result is already present.

3. Propose OOD slices.

Choose only slices relevant to the project. Possible categories include:

- Composition or stoichiometry edges.
- Phase/state changes, melt/solid/liquid/vapor boundaries, or cluster/bulk mismatch.
- Temperature, pressure, strain, density, or volume extremes near the intended deployment boundary.
- Defects, surfaces, interfaces, vacancies, interstitials, charge/spin states, or coordination changes when relevant.
- Reactive or dissociation paths, close contacts, high-force/high-energy frames, and failed MD states.
- DP-GEN model-deviation candidate/failed pools and reviewer-specified challenge sets.
- Finite-size, boundary-condition, and cell-shape shifts.

4. Map each slice to evidence.

For each proposed OOD slice, specify:

- input path or missing input to create;
- reference calculation needed, if any;
- checkpoint evaluation tool or manual step;
- expected artifact format;
- acceptance criterion or reason it remains qualitative;
- approval gate if it starts expensive labels or long MD.

5. Keep the conclusion conservative.

State whether evidence is present, missing, or insufficient. Do not say the model is OOD-safe, transferable, or deployable without benchmark artifacts and human approval.

## Output Shape

Prefer a compact plan:

- Decision question.
- Available evidence.
- Recommended OOD slices.
- Minimal validation slice under current budget.
- Missing evidence and risk.
- Tool/artifact plan.
- Approval gates.

## Response Rules

- Separate facts, assumptions, recommendations, and decisions.
- Cite paths, hashes, run ids, and artifact ids when available.
- Do not paste coordinate payloads.
- Do not invent model errors, coverage scores, or OOD labels.
- If the user asks for a universal OOD recipe, explain why the plan must be tied to the target chemistry and deployment envelope.
