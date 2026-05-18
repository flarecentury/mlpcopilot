# Troubleshooting

This guide covers common MLP Copilot runtime, workspace, MCP, TUI, and DP-GEN
operation problems.

## First Checks

Run:

```bash
uv run mlpcopilot mlp status --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp capabilities --config ~/.mlpcopilot/config.json
```

Confirm:

- `runtimeProfile` is `mlpcopilot`;
- workspace is `~/.mlpcopilot/workspace` unless you intentionally passed another
  path;
- missing schema dirs are `none`;
- MCP servers are configured;
- skills are discoverable;
- pending approvals are expected.

## Config Or Workspace Looks Wrong

Symptoms:

- TUI shows an empty workspace.
- Project/run files are missing.
- The agent does not see MLP workspace instructions.

Actions:

```bash
uv run mlpcopilot mlp init \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace
```

This refreshes defaults and workspace schema without overwriting existing files.
Do not assume explicit user config fields will be migrated; defaults apply when a
field is absent.

## MCP Server Fails To Start

Symptoms:

- Tool Log shows an MCP connection error.
- `mlpcopilot mlp capabilities` lists a server but the agent cannot call it.
- A tool call fails before reaching the tool body.

Actions:

1. Check the configured target with `mlpcopilot mlp capabilities`.
2. Run the MCP server directly from the repo root:

```bash
uv --directory mlpcopilot/mcps/mlp_training_controller_mcp run mlp-training-controller-mcp --help
uv --directory mlpcopilot/mcps/mlp_dataset_mcp run mlp-dataset-mcp --help
uv --directory mlpcopilot/mcps/mlp_model_eval_mcp run mlp-model-eval-mcp --help
uv --directory mlpcopilot/mcps/mlp_report_mcp run mlp-report-mcp --help
```

3. Check whether dependencies such as `dpgen`, DeePMD-kit, ASE, or scheduler
   commands are available in the environment used by the MCP.
4. Check `UV_CACHE_DIR` if dependency resolution fails on a restricted system.

Nested `.venv` directories under MCP packages are not required for source-tree
operation; `uv --directory ... run ...` recreates environments as needed.

## Agent Does Not Understand The Task

Symptoms:

- The agent answers from memory instead of checking current DP-GEN state.
- The agent misses active project/run context.
- The answer is generic and not tied to the user's scientific goal.

Actions:

- Provide the target use case, active project/run, DP-GEN path, relevant dataset
  or checkpoint paths, acceptance criteria, and compute constraints.
- Use `/goal` and `/plan` in the TUI, or ask the agent to persist them with the
  `workstate` tool.
- For current DP-GEN status, ask the agent to call fresh training-controller MCP
  tools in the current turn.

Durable memory should not be treated as live run status.

## DP-GEN Projection Is Empty

Symptoms:

- TUI Campaign or Artifacts panels show little or no DP-GEN state.
- `sync-dpgen` reports missing backend workdir.

Actions:

1. Confirm the run exists:

```bash
uv run mlpcopilot mlp projects show local_dpgen --config ~/.mlpcopilot/config.json
```

2. Confirm the DP-GEN workdir is at:

```text
~/.mlpcopilot/workspace/projects/<project_id>/runs/<run_id>/backend/dpgen
```

3. Sync again:

```bash
uv run mlpcopilot mlp runs sync-dpgen <project_id> <run_id> \
  --config ~/.mlpcopilot/config.json
```

The helper `bash run_tui.sh --dpgen-dir /path/to/dpgen` performs these steps for
local inspection.

## Approval Is Pending Or Stuck

Symptoms:

- A state-changing tool call does not run.
- TUI or Telegram shows a pending approval.

Actions:

```bash
uv run mlpcopilot mlp approvals --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp approve <approval_id> --reason "reason" --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp reject <approval_id> --reason "reason" --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp changes <approval_id> --reason "request" --config ~/.mlpcopilot/config.json
```

In the TUI, use `/approvals`, `/approve`, `/reject`, or `/changes`.

MCP tools are governed by runtime approval policy. The MCP server itself should
not implement approval bypass parameters.

## Rewind Or Reset Looks Risky

Symptoms:

- The user wants to go back to an earlier iteration.
- The run is expensive or partially complete.
- Disk cleanup may delete useful evidence.

Actions:

1. Ask for the intended target iteration/stage.
2. Collect fresh status and a snapshot.
3. Plan first; apply only after approval.
4. Prefer `soft` mode unless the user chooses archive cleanup.
5. Archive later iteration directories instead of deleting them.

Relevant tools:

- `get_training_status`
- `snapshot_training_state`
- `plan_training_rewind`
- `apply_training_rewind`

## Tool Claims A Metric But No Artifact Exists

Symptoms:

- A response says a checkpoint or dataset is acceptable without a report.
- A metric appears only in chat text.

Actions:

- Ask for the artifact path or run manifest entry.
- Use dataset/model/report MCP tools to produce or inspect the evidence.
- Treat missing metric artifacts as missing evidence, not as a pass.

## TUI Does Not Render As Expected

Actions:

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --once
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

If using an existing DP-GEN project:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen --once
```

Check terminal size and whether stdout is a terminal. Non-terminal output uses a
line fallback.

## Web Or Exec Tools Are Disabled

In the MLP profile, web and shell execution are intentionally narrow. Check:

```bash
uv run mlpcopilot mlp status --config ~/.mlpcopilot/config.json
```

If you explicitly change tool policy, preserve user allowlists exactly. Do not
rely on profile defaults to override explicit user values.
