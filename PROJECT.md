# Project: MLP Copilot

## Summary

MLP Copilot is a direct MLP-focused product line derived from mlpcopilot.

The project goal is to support MLP dataset validation, checkpoint validation, validation planning, artifact provenance, and human-approved model-readiness decisions.

## Current Source Of Truth

Read these files first:

1. `AGENTS.md`
2. `prd/MLPCOPILOT_RUNTIME_PRD.md`
3. `prd/MLPCOPILOT_MCP_SKILL_PRD.md`
4. `prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`
5. `docs/README.md`
6. `docs/MAINTENANCE.md`

## Product Direction

The project is split into two deliverables:

- MLP Copilot Runtime: a modified host runtime for MLP work.
- MCP/Skill Pack: scientific tools and workflows exposed as plugins.

The runtime should stay generic enough to host other scientific plugins later. The MLP-specific knowledge should live in MCP servers and skills.

## First Milestone

Build the MLP Copilot Runtime first:

- `mlpcopilot` runtime profile.
- Telegram-only default gateway.
- TUI workbench.
- ApprovalManager.
- ArtifactIndex.
- Workspace initializer.
- MCP/skill capability status.

Then build the first plugin milestone:

- `mlp_training_controller_mcp` with a DP-GEN backend provider.
- `mlp-active-learning` skill.
- `dpgen-machine-writer` skill.

Then build the validation plugin milestone:

- `mlp_dataset_mcp`.
- `mlp-dataset-validation` skill.

## Non-Goals

- No external narrative-specific product text.
- No fixed validation gap hard-coded for one material system.
- No scientific metric generated only by the LLM.
- No unrestricted shell by default.
- No unnecessary multi-agent packaging.
