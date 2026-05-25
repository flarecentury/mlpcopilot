---
name: mlp-ood-test-advisor
description: Use this skill when the user needs project-specific OOD or dataset-gap testing advice for MLP workflows. It defines validation slices, evidence artifacts, and decision gates.
---

# MLP OOD Test Advisor

Use this skill when the user asks how to test out-of-distribution behavior, dataset gaps, reviewer-requested challenge structures, finite clusters, phase or composition extrapolation, or deployment-boundary risks for a machine-learning potential.

## Core Boundary

- This skill defines a project-specific OOD test plan and evidence contract.
- It does not execute descriptor coverage algorithms or declare a model robust.
- Do not apply a fixed universal chemistry checklist. Useful OOD slices depend on chemistry, phase space, boundary conditions, and deployment workflow.
- Metrics must come from MCP artifacts such as dataset reports, checkpoint benchmark reports, `dp test` outputs, ASE or DeepMD predictions, or user-provided reference calculations.
- Large structures, trajectories, descriptors, and logs must stay in files or artifact references.
- If the user needs automated coverage scoring, candidate ranking, or descriptor-space gap analysis, raise the need for a future coverage MCP or project-specific tooling.

## When This Skill Is Strongest

This skill is especially useful for domain-shift questions such as:

- `bulk` and `surface` training data, but deployment on finite `cluster` systems.
- Low-temperature training data, but deployment in high-temperature AIMD windows.
- Periodic cell training data, but deployment on non-periodic or weakly confined structures.
- Near-equilibrium training data, but deployment on reactive, high-force, or bond-breaking frames.
- Nominal stoichiometries in training, but edge compositions, adsorption states, or dissociation intermediates in testing.

## Required Inputs

Collect these inputs or mark them missing:

- Target use case: composition, phases, temperature or pressure or strain window, ensemble, property of interest, and deployment workflow.
- In-domain evidence: training and validation dataset paths, DP-GEN run id, current iteration, and any dataset validation reports.
- Candidate checkpoint: checkpoint path, model family or backend, existing benchmark metrics, and acceptance criteria.
- Suspected OOD sources: reviewer structures, finite clusters, surfaces or interfaces, defects, high-energy states, reaction paths, unusual stoichiometries, failed DP-GEN clusters, or production failures.
- Reference budget: available DFT or ab initio calculations, CPU or GPU or HPC limits, walltime, and maximum number of new labels.
- Decision owner: who approves extra labeling, checkpoint promotion, or deployment.

## OOD Slice Patterns

Choose only slices that matter for the project. Common patterns include:

- Composition or stoichiometry edges.
- Phase or state changes, melt or liquid boundaries, or cluster or bulk mismatch.
- Temperature, pressure, strain, density, or volume extremes near the intended deployment boundary.
- Defects, surfaces, interfaces, vacancies, interstitials, charge or spin states, or coordination changes when relevant.
- Reactive or dissociation paths, close contacts, high-force or high-energy frames, and failed MD states.
- DP-GEN model-deviation candidate pools, failed pools, and reviewer-specified challenge sets.
- Finite-size, boundary-condition, and cell-shape shifts.

For `bulk/surface -> finite cluster` projects, explicitly consider:

- periodic to finite boundary-condition shift;
- coordination shift from terrace-like environments to edge, corner, and vertex sites;
- curvature shift from flat surfaces to highly curved clusters;
- size extrapolation across cluster families;
- adsorbate dynamics such as `O2` approach, bond stretch, reorientation, and dissociation-prone frames.

## Workflow

1. Define the OOD question.

Convert the request into a decision statement, for example whether a checkpoint is usable for a stated high-temperature NVT window, a finite cluster family, or a composition boundary.

2. Inventory evidence.

Use available tools when present:

- Dataset: `inspect_dataset`, `validate_dataset_integrity`, `build_dataset_validation_report`
- Training: `inspect_training_project`, `get_training_status`, `list_training_iterations`, `collect_training_logs`
- Checkpoint: `inspect_checkpoint`, `run_deepmd_test`, `validate_checkpoint_on_dataset`, `build_checkpoint_benchmark_report`

For current DP-GEN state, call a fresh training-controller status or evidence tool in the current turn unless a fresh result is already present.

3. Propose OOD slices.

Translate the target risk into a small set of test slices. Each slice should answer one deployment-boundary question.

4. Map each slice to evidence.

For each proposed OOD slice, specify:

- input path or missing input to create;
- reference calculation needed, if any;
- checkpoint evaluation tool or manual step;
- expected artifact format;
- acceptance criterion, or why the result remains qualitative;
- approval gate if it starts expensive labels or long MD.

5. Define the minimum viable validation set.

When the compute budget is tight, recommend the smallest slice set that still tests the boundary that actually matters for the deployment claim.

6. Keep the conclusion conservative.

State whether evidence is present, missing, or insufficient. Do not say the model is OOD-safe, transferable, or deployable without benchmark artifacts and human approval.

## Evidence Contract

Every useful answer should leave behind a compact evidence contract:

- decision question;
- in-domain training scope;
- target OOD scope;
- checkpoint identity;
- reference method or data source;
- metrics or qualitative checks to run;
- artifact locations;
- approval owner and gate;
- remaining risk if evidence is missing.

## Worked Example

Representative case: `bulk/surface trained Al-O model -> larger finite Al cluster + O2 AIMD validation`.

Typical decision question:

- Is the checkpoint acceptable for `Al_n + mO2` finite-cluster AIMD at `700 K` and `1200 K` when the training domain is dominated by periodic bulk and surface data?

Useful OOD slices for this case:

- boundary-condition shift: periodic bulk or surface to non-periodic finite cluster;
- coordination shift: terrace-like sites to low-coordination edge or vertex sites;
- size shift: larger cluster family than seen in training;
- thermodynamic shift: higher-temperature AIMD windows;
- reactive adsorbate shift: `O2` approach, stretch, reorientation, and near-dissociation configurations.

This repository includes a worked example asset pack under:

- `assets/examples/al-o2-cluster-ood/`

That asset pack contains:

- a case schema;
- slice definitions;
- evidence and artifact checklists;
- a sample OOD plan;
- a CP2K no-PBC template for finite clusters;
- example scripts for task setup and postprocessing.

## Output Shape

Prefer a compact plan:

- Decision question.
- Available evidence.
- Recommended OOD slices.
- Minimal validation slice under current budget.
- Missing evidence and risk.
- Tool or artifact plan.
- Approval gates.

## Response Rules

- Separate facts, assumptions, recommendations, and decisions.
- Cite paths, hashes, run ids, and artifact ids when available.
- Do not paste coordinate payloads.
- Do not invent model errors, coverage scores, or OOD labels.
- If the user asks for a universal OOD recipe, explain why the plan must be tied to the target chemistry and deployment envelope.
