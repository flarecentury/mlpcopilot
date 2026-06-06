# MLP Copilot PRD Index

This directory contains the current product requirement documents for MLP
Copilot.

## Active PRDs

- `MLPCOPILOT_RUNTIME_PRD.md`: the host runtime. Covers the profile, workspace,
  approvals, artifact index, API, Telegram, TUI host behavior, MCP/skill loading,
  and tool policy.
- `MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`: the TUI interaction layer. Covers
  slash commands, overlays, layouts, jobs, tool logs, approvals, keymaps, and
  persistence.
- `MLPCOPILOT_MCP_SKILL_PRD.md`: the plugin layer. Covers MLP MCP servers and
  MLP skills.

These three files are the current PRD source of truth.

## Supporting Notes

The following files are retained for implementation context. They are not active
PRDs and should not override the three source-of-truth PRDs above:

- `MLPCOPILOT_CONTEXT_MEMORY_PRD.md`: the context and memory layer. Covers
  resident rules, long-term memory, session goal/plan state, active project/run
  pointers, live DP-GEN state, and MCP source-of-truth boundaries.
- `RUNTIME_COMPLETION_NOTES.md`: implementation status and validation notes for
  the runtime MVP.

## Current Priorities

As of 2026-05-09, near-term work focuses on stabilizing implemented
capabilities:

1. Runtime and TUI regression fixes.
2. Continued hardening of `mlp_training_controller_mcp` against real DP-GEN
   projects.
3. Maintenance of the existing `mlp_dataset_mcp`, `mlp_model_eval_mcp`, and
   `mlp_report_mcp`.
4. Maintenance of the existing skill pack and documentation.
5. OOD test advice: maintain `mlp-ood-test-advisor` so it can propose
   project-specific test slices based on the concrete chemical system,
   deployment boundary, existing evidence, and reference budget.

## MCP Organization Principle

Do not merge every MLP tool into a single MCP server just for uniformity. Keep
MCP servers separated by responsibility for now: training controller, dataset
audit, model evaluation, and report aggregation. The runtime provides unified
discovery, approvals, logs, artifact indexing, and TUI/API presentation. Each MCP
server owns its scientific or engineering tool surface.

Reviewers usually care that evidence is reproducible, inputs and outputs have
hashes, metrics come from tool artifacts, and human decisions are traceable. They
do not usually care whether every tool runs inside one MCP process.

## Deferred Backlog

The following items are lower priority. Do not treat them as near-term drivers
unless they are explicitly raised again:

- `mlp_coverage_mcp`.
- Fixed OOD/gap audit tools and deep dataset science checks: unit consistency,
  structure sanity, duplicate detection, split leakage, label consistency, label
  outliers, and general coverage analysis.
- `mlp_job_mcp`, meaning full remote Slurm/PBS/LSF management.
- HTML/PDF report rendering.
- Manual terminal visual smoke and real deployment smoke, to be done before a
  release.

## Boundary Rule

Runtime PRD work must not introduce scientific algorithms into `mlpcopilot`
core. Scientific logic must remain in MCP servers or skills.
