# MLP Copilot Context & Memory PRD

Status: implemented, with deferred enhancements tracked  
Owner: MLP Copilot runtime  
Last updated: 2026-05-09

Implementation progress:

- Done: template-equivalent `USER.md` is skipped from prompt injection.
- Done: MLP workspace templates include scratch policy by default.
- Done: default `SOUL.md` now matches MLP Copilot autonomy and tool-first workflow.
- Done: session workstate supports an active MLP project/run pointer.
- Done: `/project` is available on TUI/gateway to show/set/clear the active project pointer.
- Done: `workstate` tool can set/clear the active project pointer.
- Done: Dream prompts warn against promoting live DP-GEN status into durable memory.
- Done: `/memory-audit` scans durable memory for likely stale DP-GEN/runtime facts without editing files.
- Done: training-controller status/snapshot evidence exposes status source, query time, and next DP-GEN stage.
- Done: MLP skills require fresh status/evidence tools for current DP-GEN state instead of durable memory.
- Done: TUI Companion displays display-document source/update metadata when available.
- Done: TUI Companion display-doc loading prefers the session active project/run pointer.
- Done: TUI Companion marks old display-document timestamps as stale.
- Done: Companion stale threshold is configurable via `tui.companionStaleAfterSeconds`.

## 1. Background

MLP Copilot is a vertical agent for machine-learning-potential work. Its core workflows involve long-running DP-GEN active learning, DeePMD-kit checkpoints, dataset validation, model evaluation, artifacts, approvals, and reports.

DP-GEN projects are not chat-native objects. They are file-state machines driven by `param.json`, `machine.json`, `record.dpgen`, logs, iteration directories, and DPDispatcher task directories. The agent must not rely on stale chat memory for current DP-GEN state.

This PRD defines how MLP Copilot should separate:

- always-visible rules,
- durable user/project memory,
- session goal/plan state,
- active project/run pointers,
- live DP-GEN state from MCP tools,
- large scientific artifacts referenced by path/hash.

It extends the runtime PRD without adding scientific algorithms to runtime core.

## 2. DP-GEN Source Findings

DP-GEN `run_iter(param_file, machine_file)` reads `param.json` and `machine.json`, normalizes `param.json`, converts machine data, then resumes from `record.dpgen`.

The generator active-learning stages are:

```text
0 make_train
1 run_train
2 post_train
3 make_model_devi
4 run_model_devi
5 post_model_devi
6 make_fp
7 run_fp
8 post_fp
```

`record.dpgen` stores the last completed `(iteration, stage)` pair. The next stage is derived from that file and the project directory, not from chat memory.

DPDispatcher submission is stage-based:

- each stage has `command`, `machine`, `resources`;
- DP-GEN requires `machine.local_root == "./"`;
- submitted tasks forward and collect files per task;
- job/log status must be read from task directories and dispatcher logs.

Implication: DP-GEN runtime state must be tool-derived and artifact-derived. Long-term memory may store stable preferences and paths, but not current iteration truth.

## 3. Goals

1. Keep important MLP/DP-GEN operating rules visible across long conversations and compaction.
2. Prevent stale memory from overriding live project state.
3. Keep large scientific data out of LLM context.
4. Make project/run state recoverable from files, MCP tools, and artifacts.
5. Let users maintain one obvious place for durable agent rules.
6. Keep runtime generic and plugin-friendly.
7. Support scratch work without polluting DP-GEN project folders.

## 4. Non-Goals

- Do not implement dataset validation, checkpoint inference, DP-GEN parsing algorithms, or scientific metrics in runtime core.
- Do not store full trajectories, coordinate arrays, model files, or large logs in memory files.
- Do not make `memory/MEMORY.md` the source of truth for active DP-GEN progress.
- Do not add a second capabilities snapshot system for MCP or skills.
- Do not auto-migrate explicit user policy config.

## 5. Context Layers

### 5.1 Always-Visible Bootstrap

Loaded every LLM turn:

```text
AGENTS.md
SOUL.md
USER.md
TOOLS.md
```

Required role:

| File | Purpose |
|---|---|
| `AGENTS.md` | Product boundary, MLP Copilot rules, approval policy, scratch policy, high-priority standing instructions |
| `TOOLS.md` | Tool policy, write boundaries, MCP-vs-runtime responsibility |
| `SOUL.md` | Short execution style only |
| `USER.md` | Stable user preferences only |

These files must stay concise. They are not project logs.

### 5.2 Durable Memory

Loaded as `# Memory` when customized:

```text
memory/MEMORY.md
```

Allowed content:

- stable user/project facts;
- stable site-specific paths, such as SIF root or common workspace root;
- MPI/container assumptions that remain true until changed;
- approved high-level decisions;
- durable acceptance criteria references;
- stable paper/reviewer context.

Disallowed content:

- current DP-GEN iteration/stage;
- live job counts;
- transient failure status;
- generated log snippets;
- temporary benchmark results;
- unapproved scientific conclusions;
- stale DeepMD-kit versions unless pinned and confirmed.

### 5.3 Session Workstate

Session metadata stores:

- current goal;
- current plan;
- short goal/plan summaries for TUI companion;
- active project/run pointer.

Goal/plan should be visible in the runtime context and TUI. It is session-local and may change often.

### 5.4 Active Project/Run Pointer

Add a compact runtime context block for the active MLP project/run:

```text
[Active MLP Project]
project_id: local_dpgen
run_id: run_local
backend: dpgen
project_path: /path/to/backend/dpgen
param_path: /path/to/param.json
machine_path: /path/to/machine.json
[/Active MLP Project]
```

This block is a pointer, not a status report. The agent should call MCP tools for current status.

Current decision:

- The active project/run pointer is session-scoped.
- `/new` starts a fresh session and clears this pointer with other session workstate.
- The pointer does not require approval because it only changes local session context.
- The pointer must not store live DP-GEN progress.

### 5.5 Tool-Derived Live State

Current DP-GEN state is always obtained from `mlp_training_controller_mcp` tools, such as:

- `inspect_training_project`;
- `get_training_status`;
- `list_training_iterations`;
- `inspect_training_iteration`;
- `collect_training_logs`;
- `analyze_training_failure`;
- `snapshot_training_state`;
- `collect_iteration_evidence`.

The agent must prefer fresh MCP output over memory when answering current-state questions.

Companion/TUI display documents may show projected DP-GEN status, but they are UI read models. They are not durable memory and are not sufficient evidence for the agent to answer current-state questions unless the relevant fresh tool result is already in the current turn.

### 5.6 Artifacts and Reports

Metrics and evidence must be referenced by:

- path;
- hash;
- artifact id;
- manifest id;
- approval id.

The LLM may summarize artifact evidence but must not invent metrics.

## 6. Required Behavioral Rules

### 6.1 Freshness Rule

If the user asks about current run status, current failure, next DP-GEN stage, job counts, or whether a run can continue, the agent must call a status/evidence MCP tool unless a fresh tool result is already in the current turn.

### 6.2 Memory Precedence Rule

Precedence order for operational facts:

```text
current tool result
> current artifact/manifest
> active project/run pointer
> durable memory
> recent chat history
```

### 6.3 Scratch Rule

Temporary code, exploratory scripts, plots, draft reports, and one-off validation outputs should be written to:

```text
~/.mlpcopilot/scratch/
```

Project directories should receive only durable reports, approved artifacts, run manifests, config files requested by the user, or outputs from actual workflow tools.

### 6.4 Long-Context Rule

Rules that must survive 200-turn conversations belong in `AGENTS.md` or `TOOLS.md`. Project facts that must survive sessions belong in `memory/MEMORY.md`. Dynamic status belongs in MCP/project files, not memory.

### 6.5 Approval Rule

Runtime builtin tools and MCP tools use the same ApprovalManager policy. Read-only/status tools may be allowlisted. Write/run/stop/rewind/cancel tools must remain approval-gated unless explicitly allowlisted by user config.

## 7. Workspace File Design

### 7.1 `AGENTS.md`

Should contain:

- runtime/plugin boundary;
- MLP Copilot standing rules;
- evidence rules;
- scratch policy;
- no auto-migration of explicit user policy;
- current high-level development direction.

Should not contain:

- run-specific logs;
- current DP-GEN status;
- long tutorials;
- full examples that belong in skills.

### 7.2 `TOOLS.md`

Should contain:

- builtin tool policy;
- MCP tool policy;
- write policy;
- scratch boundary;
- rule that scientific execution belongs in MCP/skills.

### 7.3 `SOUL.md`

Should be rewritten from generic assistant style to MLP Copilot execution style:

- concise;
- direct;
- tool-first when facts are discoverable;
- do work after reasonable assumptions;
- ask only when blocked;
- no blanket "wait for confirmation" for multi-step tasks.

Risk: existing generic `SOUL.md` conflicts with MLP Copilot autonomy.

### 7.4 `USER.md`

Should store stable user preferences:

- preferred language;
- preferred workspace root;
- preferred shell/container conventions;
- communication style.

If empty template, it should not consume context. Runtime may skip template-equivalent `USER.md`, as already done for `MEMORY.md`.

### 7.5 `PROJECT.md`

`PROJECT.md` is not currently a bootstrap file. It should remain a human project profile unless a separate project-context loader is added.

Recommended role:

- project identity;
- target use case;
- acceptance criteria references;
- approved decisions;
- active project/run pointer references.

Do not use it as hidden always-injected instruction unless runtime explicitly supports that.

## 8. Runtime Requirements

### R1. Keep Bootstrap Injection

Continue injecting `AGENTS.md`, `SOUL.md`, `USER.md`, and `TOOLS.md` every turn.

### R2. Template-Skip Empty `USER.md`

If `USER.md` is unchanged from bundled template, skip injecting it.

Acceptance:

- empty/default `USER.md` does not appear in system prompt;
- customized `USER.md` appears.

### R3. Add Active Project/Run Runtime Context

When a session has an active MLP project/run, inject a compact metadata-only block before the user message.

Acceptance:

- the block contains pointers only;
- no large logs or metrics are injected;
- agent can know which project path to pass to MCP tools.

### R4. Harden Workstate Tool Contract

The `workstate` tool should expose:

- goal;
- plan;
- active project;
- active run;
- project path;
- stale/empty indicators.

Acceptance:

- TUI companion and agent runtime agree on goal/plan/project pointer;
- completed plans disappear from active summary.

### R5. Workspace Template Alignment

Bundled workspace templates should match the live MLP workspace policy:

- scratch boundary in `AGENTS_TEMPLATE` and `TOOLS_TEMPLATE`;
- no capabilities-folder references;
- no stale generic text.

Acceptance:

- new `mlpcopilot` workspace gets the same policy shape as the current maintained workspace.

### R6. Memory Hygiene Checks

Add a lightweight command or tool to inspect memory for likely stale runtime facts.

Examples:

- DeepMD-kit version lines without date/source;
- current iteration/status lines;
- job counts;
- transient error snippets.

Acceptance:

- tool reports warnings only;
- no automatic rewrite unless the user approves.

## 9. MCP/Skill Requirements

### M1. DP-GEN State Is MCP-Owned

`mlp_training_controller_mcp` remains the source of truth for DP-GEN project state.

It should expose enough evidence for the agent to answer:

- where is the run now;
- what is the next stage;
- which logs matter;
- what failed;
- what files/artifacts support the answer.

### M2. Skills Teach Workflow, Not Store State

Skills should describe how to use tools and what evidence is required. They should not contain user-specific current paths except bundled examples/fixtures.

### M3. Memory Update Skill Guidance

The memory skill or Dream prompt should be aware that DP-GEN current status must not be promoted to long-term memory.

## 10. Dream / Consolidation Requirements

### D1. Consolidator

The consolidator may archive old turns to `memory/history.jsonl`, but summaries should remain bounded and should not become operational truth.

### D2. Dream

Dream may update:

- `SOUL.md`;
- `USER.md`;
- `memory/MEMORY.md`.

Dream must not write current DP-GEN stage/job status to durable memory unless the user explicitly asks to preserve a historical note.

Recommended Dream instruction:

```text
Do not promote live DP-GEN status, current iteration/stage, transient queue counts,
or temporary failure signatures into durable memory. Preserve only stable project
facts, approved decisions, durable paths, and user preferences.
```

Dream writes should remain approval-gated.

## 11. TUI Requirements

### T1. Companion Display

Companion should show:

- DP-GEN live summary from project artifacts/MCP projection;
- source/update metadata for the displayed projection when available;
- goal summary;
- plan summary;
- stale indicator if project pointer exists but live status is old. Done.
- configurable stale threshold for local operating style. Done.

### T2. User Visibility

Provide commands or panels to inspect:

- current goal/plan;
- active project/run pointer;
- memory files;
- last status snapshot time;
- source of companion status.

## 12. Implementation Plan

### Phase 1: Policy Cleanup

1. Update bundled `AGENTS_TEMPLATE` and `TOOLS_TEMPLATE` with scratch rules.
2. Rewrite default `SOUL.md` template for MLP Copilot autonomy.
3. Skip template-equivalent `USER.md` injection.
4. Add tests for prompt assembly.

### Phase 2: Active Project/Run Context

1. Extend workstate metadata for active project/run pointer. Done.
2. Add slash or local command to set/show/clear active project. Done.
3. Inject compact active project metadata block. Done.
4. Add tests for prompt context and TUI companion display. Done.

### Phase 3: Memory Hygiene

1. Add stale-memory scanner. Done.
2. Add Dream prompt constraint for DP-GEN live-state exclusion.
3. Add `/memory-audit` or equivalent local command. Done.
4. Add tests with fake memory containing stale DP-GEN status. Done.

### Phase 4: MCP Coupling Check

1. Ensure training controller MCP exposes all needed DP-GEN status fields. Done.
2. Ensure agent skills instruct fresh status calls. Done.
3. Ensure reports cite artifacts/hashes/approval decisions. Done.

## 13. Acceptance Criteria

This PRD is complete when:

1. Long conversations do not lose standing rules because `AGENTS.md`/`TOOLS.md` remain injected.
2. Current DP-GEN status is always tool-derived, not memory-derived.
3. `memory/MEMORY.md` contains durable facts but not live iteration/job state.
4. A new workspace has scratch policy by default.
5. The agent can see the active project/run pointer without injecting large project files.
6. TUI and agent runtime agree on goal/plan/project pointer.
7. Dream cannot silently pollute long-term memory with transient DP-GEN status.

## 14. Open Questions

Resolved for the current implementation:

1. Active project/run pointer is session-scoped only.
2. `PROJECT.md` remains human-only and is not injected automatically.
3. Stale memory scanner is a runtime-local read-only slash command.
4. Project pointer changes are local session state and do not require approval.

Deferred enhancements:

1. Optional workspace-global default project pointer with session override.
2. Optional capped `PROJECT.md` loader if a future workflow needs project briefs in prompt context.

## 15. Recommended Defaults

Recommended near-term defaults:

- active project/run pointer is session-scoped;
- `PROJECT.md` is not injected automatically;
- stale memory scanner is a runtime-local read-only tool or slash command;
- Dream updates remain approval-gated;
- DP-GEN live status remains owned by `mlp_training_controller_mcp`;
- scratch root defaults to `~/.mlpcopilot/scratch/`.
