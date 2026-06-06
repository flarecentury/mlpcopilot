# MLP Copilot Development Context

This repository is the canonical `mlpcopilot` MLP-focused product line, adapted from the general-purpose `mlpcopilot` project for MLP-focused agent runtime work.

## Current Goal

Build a practical vertical agent system for machine-learning-potential work, especially dataset validation, checkpoint validation, validation planning, artifact tracking, and human-approved decisions.

The intended implementation order is:

1. First modify the inherited runtime into the MLP Copilot host runtime.
2. Then build MLP MCP servers and MLP skills as plugins.

## Product Split

There are three active PRD files:

- `prd/MLPCOPILOT_RUNTIME_PRD.md`
  - Defines the mlpcopilot runtime modifications only.
  - Covers runtime profile, TUI, Telegram-only gateway, ApprovalManager, ArtifactIndex, workspace schema, MCP/skill plugin loading, and OpenAI-compatible API.
  - Must not include MLP scientific algorithms.

- `prd/MLPCOPILOT_MCP_SKILL_PRD.md`
  - Defines the plugin layer.
  - Covers MLP MCP servers and MLP skills.
  - Includes dataset validation MCP, model MCP, validation MCP, job MCP, report MCP, and skills such as `mlp-dataset-validation`.

- `prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`
  - Defines the TUI interaction layer.
  - Covers Codex-style slash commands, overlays, jobs, model switching, approvals, and layout behavior.

## Architecture Boundary

Keep the boundary strict:

- MLP Copilot runtime is the host.
- MCP servers are executable scientific tool plugins.
- Skills are method/process plugins.

Do not put dataset validation algorithms, checkpoint inference, benchmark execution, or validation methodology directly into mlpcopilot core.

MLP Copilot core should provide:

- agent loop
- session and memory
- plugin loading
- MCP client integration
- TUI
- Telegram gateway
- OpenAI-compatible API
- ApprovalManager
- ArtifactIndex
- workspace initialization

MCP/Skill should provide:

- dataset validation
- model inference and checkpoint metrics
- validation plan execution
- job monitoring
- report rendering
- MLP-specific workflows and guidance

## Important Product Decisions

- Do not make the agent look more impressive by adding unnecessary multi-agent behavior.
- Keep the product requirements focused on runtime, plugins, workflows, and evidence; avoid external narrative goals.
- Do not hard-code a fixed validation gap for one material system.
- The agent should help users generate a project-specific validation plan based on target use case, dataset inventory, checkpoint, reference data, acceptance criteria, and compute budget.
- Human-in-the-loop must be a real blocking approval workflow, not a vague statement.
- Scientific data should move by file path, object id, or artifact reference, not by large pasted coordinate payloads in LLM context.
- Metrics must come from tool artifacts, not from LLM judgment.
- Agent-side built-in tool and MCP tool calls use one runtime approval policy. Exact `tools.approvalAllowlist` entries are the normal bypass; MCP tools must not implement `approval_hint`, `requires_approval`, or `approved=true` approval shims.
- TUI `!<cmd>` is an explicit terminal mode and does not use agent tool approval or exec allowlists.

## Current Implementation Status

As of the current implementation state:

- The runtime PRD, MCP/skill PRD, and TUI interaction PRD remain the product source of truth.
- Runtime work has moved beyond planning and is being ported into the canonical MLP Copilot codebase.
- `runtimeProfile = "mlpcopilot"` is implemented in config/profile policy.
- The MLP workspace initializer is implemented and creates runtime, project, run, artifact, approval, memory, and skill directories.
- Channel/tool whitelisting for the MLP profile is implemented.
- ApprovalManager and decision storage are implemented.
- ArtifactIndex and run manifest support are implemented.
- `mlpcopilot tui` exists as a modular terminal workbench with Chat, Tool Log, Artifacts, Campaign, and Approvals views.
- OpenAI-compatible API approval handlers exist.
- MLP MCP server packages exist for training control, dataset validation, and first-pass model metrics ingestion.
- The training controller MCP currently uses a DP-GEN backend provider and includes read/config/status/log/report tools plus run, stop, and rewind controls; approval is enforced by the runtime when these tools are called through the agent.
- Initial MLP skills exist, including `mlp-active-learning`, `dpgen-machine-writer`, `mlp-initial-dataset-preparation`, `mlp-dataset-validation`, `mlp-validation-planner`, and `mlp-checkpoint-evaluation`; model inference skill packs are not complete yet.
- The old mixed PRD was removed and replaced by the split PRDs under `prd/`.

## Inherited MLPCopilot Facts

MLPCopilot already supports:

- OpenAI-compatible API via `mlpcopilot serve`.
- MCP servers via `stdio`, `sse`, and `streamableHttp`.
- Workspace skills under `skills/`.
- Multiple channels, though the MLP Copilot runtime should default to Telegram only.

Useful existing files:

- `mlpcopilot/api/server.py`
- `mlpcopilot/agent/tools/mcp.py`
- `mlpcopilot/config/schema.py`
- `mlpcopilot/channels/telegram.py`
- `mlpcopilot/agent/loop.py`
- `mlpcopilot/agent/context.py`
- `docs/reference/openai-api.md`
- `docs/reference/configuration.md`

## Near-Term Engineering Plan

For the mlpcopilot runtime:

1. Harden `runtimeProfile = "mlpcopilot"` defaults and migration behavior.
2. Harden workspace initializer compatibility and schema evolution.
3. Complete channel/tool policy tests for the profile.
4. Harden ApprovalManager decision lifecycle, restart behavior, and API/TUI/Telegram consistency.
5. Expand ArtifactIndex/run manifest evidence fields only as runtime-level metadata.
6. Continue modularizing and testing `mlpcopilot tui`.
7. Improve MCP and skill status display without adding scientific logic to runtime core.

For MCP/Skill plugins:

1. Continue hardening `mlp_training_controller_mcp` first.
2. Continue hardening `mlp-active-learning` and `dpgen-machine-writer` skills against real DP-GEN projects.
3. Continue hardening the first-pass `mlp_dataset_mcp` and `mlp-dataset-validation` skill.
4. Continue hardening the first-pass `mlp-validation-planner` skill.
5. Continue hardening the first-pass `mlp_model_eval_mcp` without inventing metrics.
6. Add checkpoint inference execution, coverage MCP, job MCP, and report MCP later.

## Current Boundary Watch

- Keep DP-GEN-specific science and backend logic inside `mlp_training_controller_mcp` or another plugin package.
- Runtime code may project plugin outputs into workspace read models, TUI panels, artifact records, or run manifests, but should not grow DP-GEN algorithms, validation methods, model metrics, or dataset analysis logic.
- If a runtime helper becomes backend-specific or starts parsing scientific meaning beyond artifact indexing/status projection, move it behind a plugin-facing contract.

## Review Rule

When modifying this repo, keep changes scoped to the PRD currently being implemented. If working on runtime, do not implement scientific MCP logic in core. If working on MCP/Skill, do not modify mlpcopilot UI, channels, session, or approval internals unless explicitly requested.

Do not auto-migrate explicit user policy config. Defaults apply only when a field is absent. For allowlists/enabled lists, preserve user values exactly and tell the user what to edit manually.
