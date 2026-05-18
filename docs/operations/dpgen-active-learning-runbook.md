# DP-GEN Active-Learning Runbook

This runbook is for scientists and operators using MLP Copilot with an existing
or new DP-GEN active-learning project. It focuses on stable operation,
evidence, and human-approved state changes.

## Scope

MLP Copilot should help with:

- understanding the active project and target use case;
- inspecting DP-GEN state, iterations, logs, and artifacts;
- preparing or reviewing `param.json` and `machine.json`;
- planning safe rewind/restart actions;
- recording evidence and approval decisions.

MLP Copilot should not invent scientific metrics or silently mutate a DP-GEN
project. Metrics must come from MCP tool artifacts, DP-GEN files, or user
provided reference data.

## Default Paths

The runtime root is `~/.mlpcopilot`.

| Item | Default Path |
| --- | --- |
| Config | `~/.mlpcopilot/config.json` |
| Workspace | `~/.mlpcopilot/workspace` |
| Scratch outputs | `~/.mlpcopilot/scratch` |
| Project runs | `~/.mlpcopilot/workspace/projects/<project_id>/runs/<run_id>` |
| DP-GEN backend workdir inside a run | `backend/dpgen` |

## Quick Attach Existing DP-GEN Project

For local inspection, prefer the helper script:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir
```

By default this creates or refreshes the MLP workspace, creates a project/run if
needed, symlinks the DP-GEN workdir into `backend/dpgen`, syncs TUI read models,
and opens the TUI.

Use a copy instead of a symlink when you want an isolated snapshot:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --copy-dpgen
```

Prepare the workspace without opening the TUI:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

Render a read-only snapshot:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --once
```

## Manual Attach Workflow

Use this when you need explicit project IDs or want to inspect each step.

```bash
uv run mlpcopilot mlp init \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace

uv run mlpcopilot mlp projects create "Local DP-GEN" \
  --project-id local_dpgen \
  --target-use-case "inspect and operate an existing DP-GEN active-learning run" \
  --config ~/.mlpcopilot/config.json

uv run mlpcopilot mlp runs create local_dpgen \
  --run-id run_local \
  --config ~/.mlpcopilot/config.json
```

Then place the DP-GEN workdir at:

```text
~/.mlpcopilot/workspace/projects/local_dpgen/runs/run_local/backend/dpgen
```

For a symlink, replace only the generated empty `backend/dpgen` directory:

```bash
backend=~/.mlpcopilot/workspace/projects/local_dpgen/runs/run_local/backend/dpgen
mv "$backend" "${backend}.empty"
ln -s "$(realpath /path/to/dpgen/workdir)" "$backend"
```

Project the DP-GEN state into run manifests and UI read models:

```bash
uv run mlpcopilot mlp runs sync-dpgen local_dpgen run_local \
  --config ~/.mlpcopilot/config.json
```

Open the workbench:

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

## Start Of A New Task

At the start of a new MLP task, provide or let the agent ask for:

- target use case and material/system scope;
- active project ID, run ID, and DP-GEN workdir path;
- current concern: status, failure, restart, config review, validation, or report;
- relevant datasets, checkpoints, reference data, and acceptance criteria;
- compute budget and scheduler constraints;
- approval preference for state-changing operations.

The agent should persist the agreed goal, plan, and active project/run pointer
with `workstate`. Live DP-GEN status should still come from MCP tools in the
current turn.

## Routine Status Loop

Use CLI/TUI views for quick checks:

```bash
uv run mlpcopilot mlp status --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp capabilities --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp runs list --config ~/.mlpcopilot/config.json
uv run mlpcopilot mlp runs show run_local --config ~/.mlpcopilot/config.json
```

In the agent, status answers should be based on fresh MCP evidence such as:

- `inspect_training_project`
- `get_training_status`
- `list_training_iterations`
- `inspect_training_iteration`
- `collect_training_logs`
- `analyze_training_failure`
- `get_controller_state`
- `list_dispatcher_jobs`
- `inspect_dispatcher_job`

Do not answer current iteration, phase, failure state, or queue status only from
chat history or long-term memory.

## Config Review And Generation

For DP-GEN config work:

1. Read existing `param*.json`, `run_param*.json`, and `machine*.json` files
   before proposing changes.
2. Keep generated files backend-native. Do not add non-DP-GEN fields to
   `machine.json`.
3. Use `generate_training_param` and `generate_training_machine` when profile
   files are available.
4. Run `validate_training_inputs` before proposing a start or resume.
5. Use `plan_config_update`, `plan_machine_update`, or `plan_param_update`
   before applying changes.

State-changing config tools must be approved through the runtime approval flow
when invoked by the agent.

## Start, Stop, Resume

Before starting or resuming DP-GEN, the agent should summarize:

- project path and backend workdir;
- command, `param.json`, and `machine.json`;
- file hashes when available;
- scheduler/resource risk;
- expected artifacts and logs;
- approval request ID when approval is pending.

Relevant tools:

- `start_training_run`
- `run_training_controller`
- `resume_training_run`
- `stop_training_run`
- `cancel_scheduler_jobs`

`stop_training_run` signals the local controller process. Remote scheduler jobs
may need explicit cancellation by scheduler job ID.

## Safe Rewind Policy

For rewind/restart requests, preserve more files than strictly necessary.

Required sequence:

1. Collect fresh evidence with `get_training_status`.
2. Use `snapshot_training_state` when state may change or the run is expensive.
3. Call `plan_training_rewind` or `plan_training_reset`.
4. Present the plan and choices to the user.
5. Apply only after approval.

Available modes:

| Mode | Behavior |
| --- | --- |
| `soft` | Change DP-GEN record pointer and preserve iteration directories |
| `hard` / archive | Archive later iteration directories under the MCP backup directory; do not delete them |

Ask the user before cleanup, moving, overwriting, or disk-space tradeoffs. Do not
hand-edit `record.dpgen` when the MCP rewind tool can produce a reversible plan.

## Evidence To Keep

Useful evidence artifacts include:

- `record.dpgen` hash and parsed current pointer;
- iteration directory inventory;
- selected log tails with paths and hashes;
- `param.json` and `machine.json` hashes;
- controller state and process logs;
- dispatcher job IDs and inspected job files;
- pre-rewind snapshots;
- approval decisions.

Large trajectories, structures, and datasets should stay as files referenced by
path or artifact ID.
