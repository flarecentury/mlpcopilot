---
name: mlp-dataset-validation
description: Use this skill when inspecting or validating machine-learning-potential datasets before training, active learning, checkpoint evaluation, or reporting. It guides use of mlp_dataset_mcp tools for dataset inventory, schema checks, integrity checks, and validation reports without inventing scientific metrics.
---

# MLP Dataset Validation

Use this skill when the user wants to check MLP dataset quality, prepare evidence before training, or understand whether a dataset is structurally usable for downstream tools.

Core boundary:

- Dataset validation tools inspect files and produce artifacts.
- The skill decides workflow order and communicates risk.
- Do not claim a model is ready, accurate, transferable, or production-safe.
- Do not invent energy/force/stress metrics. Metrics must come from tool artifacts.
- Move structures, trajectories, and large arrays by file path or artifact reference, not pasted payloads.

## Workflow

1. Identify dataset scope.

Ask for dataset path, expected format, target use case, and whether the dataset is initial training data, validation data, exploration candidates, or reference benchmark data.

2. Inspect inventory.

Call `inspect_dataset` first. Use the result to identify dataset kind, file count, recognized layouts, DeepMD raw systems, hashes, and sampled files.

3. Validate declared schema.

If the user has a schema or checklist file, call `validate_dataset_schema`. If none exists, continue with integrity checks and state that schema validation was skipped.

4. Validate integrity.

Call `validate_dataset_integrity`. Treat missing paths, malformed extxyz frames, DeepMD raw frame-count mismatches, and missing required DeepMD files as blocking until fixed or explicitly accepted by the user.
State clearly that this is a lightweight file-layout and basic integrity check. It does not cover unit consistency, structure sanity, duplicate detection, split leakage, label consistency, label outliers, OOD coverage, or local-environment coverage.

5. Report.

Call `build_dataset_validation_report` when the user needs a durable report or when results will feed a later training or evaluation decision.

6. Escalate advanced checks.

For unit consistency, structure sanity, duplicate detection, split leakage, label consistency, label outliers, and coverage analysis, explain that the current minimal dataset MCP does not yet implement those specialized checks unless matching tools are available in the active MCP inventory.
For OOD testing requests, use `mlp-ood-test-advisor` when available to propose project-specific validation slices and evidence requirements instead of applying a fixed chemistry-agnostic checklist.

## Tool Selection

- Dataset inventory: `inspect_dataset`
- Schema/checklist file validation: `validate_dataset_schema`
- Lightweight integrity checks: `validate_dataset_integrity`
- Markdown evidence report: `build_dataset_validation_report`

## Expected Evidence

Useful evidence includes:

- Dataset path.
- Dataset kind or recognized format.
- File count and sampled hashes.
- DeepMD raw systems, atom counts, frame counts, and present files.
- Integrity errors and warnings.
- Report artifact path and SHA256.

## Response Rules

- Separate facts from recommendations.
- Cite artifact paths and hashes when available.
- If checks pass, say only that the performed checks passed.
- If checks are incomplete, name the missing tool or missing input.
- Do not summarize large coordinate payloads in chat.
