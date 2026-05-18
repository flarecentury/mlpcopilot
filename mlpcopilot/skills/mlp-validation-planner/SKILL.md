---
name: mlp-validation-planner
description: Use this skill when creating or reviewing a project-specific validation plan for machine-learning-potential datasets, checkpoints, active-learning runs, or deployment decisions. It turns target use case, dataset inventory, reference data, checkpoint artifacts, acceptance criteria, and compute budget into an evidence-driven validation plan without executing scientific algorithms directly.
---

# MLP Validation Planner

Use this skill when the user wants a validation plan before training, before checkpoint selection, after an active-learning iteration, or before using an MLP model in production calculations.

Core boundary:

- The skill structures the plan, evidence requirements, and decision gates.
- MCP tools produce dataset, model, coverage, job, and report artifacts.
- Do not invent validation metrics or declare a model ready without tool-produced evidence.
- Keep large structures, trajectories, descriptors, and logs in files or artifact references.
- Tailor the plan to the target use case; do not hard-code a fixed validation gap or material-specific benchmark.

## Required Inputs

Collect these before writing a concrete plan:

- Target use case: property, composition/phase space, temperature/pressure/strain range, ensembles, and expected deployment workflow.
- Dataset inventory: paths, formats, labels, source methods, train/validation/test split, and any existing dataset reports.
- Candidate checkpoint or training run: checkpoint paths, run id, model family, and training manifest if available.
- Reference data: DFT/experiment/benchmark paths, accepted calculators, and known limitations.
- Acceptance criteria: required energy/force/stress/property tolerances, stability checks, uncertainty thresholds, and human decision owner.
- Compute budget: available GPUs/CPUs, scheduler constraints, walltime limits, and maximum reference calculations.

If an input is missing, mark it as missing in the plan instead of filling it in.

## Workflow

1. Define the validation question.

Convert the user's goal into a short decision statement, for example: whether a checkpoint is acceptable for NVT sampling of a stated composition and temperature window.

2. Inventory existing evidence.

Use available tools such as `inspect_dataset`, `validate_dataset_integrity`, `inspect_training_project`, `build_training_run_report`, or artifact index views. Cite paths and hashes when present.
For active-learning status, next DP-GEN stage, failure state, or queue/task counts, use a fresh training-controller status/evidence tool in the current turn unless a fresh result is already present.

3. Identify required checks.

Separate checks into:

- Dataset checks: schema, integrity, units, label consistency, splits, duplicates, outliers, and domain coverage.
- Model checks: checkpoint hash, independent benchmark metrics, energy/force/stress errors, stability tests, and comparison to prior checkpoints.
- Workflow checks: reproducibility, runtime command provenance, job logs, failed tasks, and approval decisions.
- Deployment checks: domain boundaries, extrapolation triggers, fallback policy, and monitoring artifacts.

Only include checks that match the target use case and available budget.

4. Map checks to tools.

For each check, name the MCP tool if it exists. If no tool exists yet, label the check as manual or future-tool and specify the expected artifact format.

5. Add approval gates.

Create explicit decision points for expensive jobs, destructive rewinds, checkpoint promotion, and production use. Each gate should name the evidence needed before approval.

6. Produce the plan.

The plan should be actionable and compact:

- Scope and assumptions.
- Evidence already available.
- Validation tasks ordered by dependency.
- Required artifacts and owners.
- Acceptance criteria.
- Blockers and risks.
- Final decision gate.

## Tool Selection

Use these tools when present in the active MCP inventory:

- Dataset evidence: `inspect_dataset`, `validate_dataset_schema`, `validate_dataset_integrity`, `build_dataset_validation_report`
- Training evidence: `inspect_training_project`, `get_training_status`, `list_training_iterations`, `inspect_training_iteration`, `collect_training_logs`, `build_training_run_report`
- Model evidence: `inspect_checkpoint`, `validate_checkpoint_on_dataset`, `compare_checkpoints`, `build_checkpoint_metrics`
- Coverage evidence: `build_structure_descriptors`, `analyze_local_environment_coverage`, `find_coverage_gaps`, `build_coverage_report`
- Report evidence: `build_mlp_validation_report` or the active report MCP equivalent

If a named tool is unavailable, do not pretend it ran. Mark it as unavailable and keep the plan explicit about the gap.

## Response Rules

- Keep facts, assumptions, proposed checks, and approval decisions separate.
- Use tool artifacts as evidence; use LLM reasoning only to organize the workflow.
- Do not use durable memory as evidence for current DP-GEN iteration, stage, failures, or job counts.
- Never paste large coordinate blocks or trajectory contents.
- Do not claim readiness; say what evidence would support or block the decision.
- When budget is tight, propose a minimal validation slice and name what risk remains.
