---
name: mlp-active-learning
description: Use this skill when planning or operating machine-learning-potential active-learning training workflows, especially DeepMD-kit with a DP-GEN backend, including collecting system/resource profiles, generating training parameter and machine configs, validating inputs, checking training status, planning conservative rewinds/restarts, and analyzing failures through the mlp_training_controller_mcp tools.
---

# MLP Active Learning

Use this skill for MLP training workflows where the user wants to plan, generate, validate, monitor, or diagnose an active-learning run.

Core boundary:

- The runtime hosts conversation, approval, artifacts, and MCP access.
- `mlp_training_controller_mcp` controls training workflow files and status.
- DP-GEN is the first backend, but keep language generic unless a DP-GEN file or command is involved.
- Do not invent metrics, coverage claims, or model-readiness conclusions.
- Move structures, trajectories, logs, and datasets by path or artifact reference, not pasted payloads.

## Workflow

1. Collect a `system_profile`:

Ask for elements, system type, initial data paths, exploration structure paths, target temperature/pressure/ensemble ranges, and intended use case.

2. Collect a `strategy_config`:

Ask for number of models, backend, trust thresholds, FP task min/max, exploration schedule, train backend, and any template assets such as LAMMPS or CP2K input files.

3. Collect a `machine_profile`:

Ask for train/model_devi/fp commands, local or SSH context, remote roots, CPU/GPU resources, source scripts, queue settings, and wrapper scripts. Do not ask the user to paste passwords; prefer SSH config, environment variables, or external secret references.

4. Generate backend-native config:

Call `generate_training_param` and `generate_training_machine` if profile files exist or after writing them to workspace paths.
When an existing DP-GEN project, example, or reference config is available, read the full reference `param*.json`/`run_param*.json` and `machine*.json` first, then adapt it into a complete backend-native JSON file. Do not produce partial snippets, abbreviated JSON, or placeholder-only configs unless the user explicitly asks for a draft sketch.

5. Validate before execution:

Always call `validate_training_inputs` before proposing a run start. Treat warnings about missing data paths, missing templates, `sys_idx`, batch-size mismatches, and secret-like fields as blocking until the user accepts or fixes them.

6. Approval gate:

Before `start_training_run`, summarize command, project path, param hash, machine hash, backend, resource risk, remote roots, and expected artifacts. The run start must be approved by the runtime ApprovalManager.

7. Monitor and diagnose:

Use `get_training_status`, `list_training_iterations`, `inspect_training_iteration`, `collect_training_logs`, and `analyze_training_failure`.
When answering current run status, next stage, queue counts, or failure state, call a fresh status/evidence tool in the current turn unless a fresh tool result is already present. Do not answer these from chat history or durable memory.

8. Rewind or restart safely:

For DP-GEN rewind/restart requests, default to preserving more files than strictly necessary.

- First collect fresh evidence with `get_training_status` and, when a state change is plausible, `snapshot_training_state`.
- Use `plan_training_rewind` before any apply/reset tool. Do not hand-edit `record.dpgen` in chat or with ad hoc file tools when the MCP tool can make a reversible plan.
- Present choices before action:
  - `soft`: change only the DP-GEN record pointer and preserve all `iter.??????` directories.
  - `hard/archive`: move later iteration directories into the MCP backup/archive directory; do not delete them.
- Ask the user which choice they want whenever cleanup, moving, overwriting, or disk-space tradeoffs are involved.
- If the execution path depends on that choice, use the blocking `ask_user` tool with clear options such as `soft preserve` and `archive later iterations`.
- Never recommend deleting iteration directories as a default. If the user explicitly wants deletion, suggest archive/move first and require explicit confirmation plus runtime approval.
- Do not claim DP-GEN will safely overwrite old iteration directories unless the active backend/tool evidence confirms that behavior for this project.
- A rewind plan should name the target record, affected iteration directories, backup/archive path, evidence snapshot path, and recovery path.

9. Report:

Use tool artifacts and paths. Do not claim checkpoint reliability unless a model-evaluation MCP has produced metrics.

## Tool selection

- Project discovery: `inspect_training_project`
- Generate param config: `generate_training_param`
- Generate machine config: `generate_training_machine`
- Validate config: `validate_training_inputs`
- Current state: `get_training_status`
- Iteration overview: `list_training_iterations`
- One iteration: `inspect_training_iteration`
- Log collection: `collect_training_logs`
- Failure diagnosis: `analyze_training_failure`
- Rewind planning: `snapshot_training_state`, then `plan_training_rewind`
- Start/stop/rewind/reset: only after explicit approval, and only if those tools are implemented for the active backend

## DP-GEN backend notes

DP-GEN state is normally derived from:

- `param.json`
- `machine.json`
- `record.dpgen`
- `dpgen.log`
- `iter.??????/00.train`
- `iter.??????/01.model_devi`
- `iter.??????/02.fp`

DP-GEN stage map:

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

Common DP-GEN checks:

- `type_map` and `mass_map` length/order.
- `init_data_sys` and `init_batch_size` length.
- `sys_configs` and `sys_batch_size` length.
- `model_devi_jobs[*].sys_idx` within `sys_configs`.
- LAMMPS template variables match `rev_mat`.
- CP2K/VASP/ABACUS template paths exist.
- Machine config does not expose plaintext secrets.
- Existing reference configs are preferred over from-scratch templates when adapting a real DP-GEN project.
- Final generated `param.json` and `machine.json` must be complete JSON files, not chat-only fragments.

## Response rules

- Be explicit about what is generated, validated, pending approval, or blocked.
- For failures, cite log artifact paths and short redacted evidence snippets.
- For config suggestions, label them as proposals until validated.
- For scientific conclusions, require metrics from MCP artifacts.
- For current DP-GEN state, cite `status_source`, `queried_at`, and relevant artifact paths or hashes when the tool provides them.
- For DP-GEN rewinds, prefer conservative soft or archive plans, ask before cleanup choices, and cite the MCP backup/archive path rather than implying files were deleted.
