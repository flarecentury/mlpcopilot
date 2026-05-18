# MLP Workspace and UI Design

This document records workspace directory design for MLP active-learning
workflows, plus design conventions for the TUI `Artifacts` and `Companion`
areas.

Design boundaries:

- The `mlpcopilot` runtime owns only workspace state, sessions, approvals,
  artifact indexing, UI state, and MCP/skill integration.
- MLP, DP-GEN, and DeepMD-kit scientific workflows are implemented by MCP
  servers and skills.
- Runtime core does not directly implement dataset validation, model inference,
  benchmarks, active-learning strategy, or scientific judgment.
- Large scientific data moves through file paths, artifact ids, or object ids;
  it is not pasted into LLM context.
- Metrics and status must come from tool artifacts and artifact metadata, not
  from LLM inference over chat history.
- Backend-native working directories should remain intact. The runtime projects
  them through an adapter/projector into normalized project, run, iteration, and
  artifact state.

## 1. Workspace Structure

Recommended workspace state groups:

| Type | Cross-session | Responsibility |
| --- | --- | --- |
| runtime state | Partly | Chat, tool log, approvals, memory, TUI state |
| project state | Yes | Project, data inventory, checkpoints, plans, active run |
| run/artifact state | Yes | Active-learning runs, iterations, artifacts, evidence chain |

Recommended structure:

```text
~/.mlpcopilot/workspace/
  sessions/
  logs/
  approvals/
  memory/

  projects/
    <project_id>/
      project.json
      companion.json

      inventory/
        datasets.jsonl
        structures.jsonl
        checkpoints.jsonl
        reference_data.jsonl
        compute_resources.jsonl

      plans/
        active_learning_plan.<plan_id>.json
        validation_plan.<plan_id>.json

      runs/
        <run_id>/
          run.json
          run_state.json
          artifacts.jsonl
          approvals.jsonl

          controller/
            controller.json
            generated_param.json
            generated_machine.json
            rendered_inputs/
              param.json
              machine.json
            submit_scripts/

          backend/
            dpgen/
              param.json
              machine.json
              record.dpgen
              iter.000000/
                00.train/
                01.model_devi/
                02.fp/
              iter.000001/
              iter.000002/

          iterations/
            iter_000000.json
            iter_000001.json
            iter_000002.json

          ui/
            artifacts.state.json
            companion.state.json

          reports/
            run_report.md
            run_report.json

          logs/
            controller.log
            tool_calls.jsonl

  artifacts/
    artifacts.jsonl
    artifacts.duckdb
    blobs/
```

## 2. Project, Run, And Iteration Semantics

Recommended semantics:

| Level | Semantics | Example |
| --- | --- | --- |
| project | A long-lived MLP project or system task | Fe-C-H potential development |
| run | One concrete active-learning, training, or validation execution | A DP-GEN-style AL run with one threshold and machine configuration |
| iteration | One normalized round inside a run | `iter_000003` |
| artifact | A file, metric, report, or approval evidence produced by a step | model deviation summary, label task batch |

Normalized `iterations` records should live under
`projects/<project_id>/runs/<run_id>/iterations/`, not directly under
`projects/<project_id>/iterations/`.

Backend-native iteration directories should live under
`projects/<project_id>/runs/<run_id>/backend/<backend_name>/`. For example,
DP-GEN uses `iter.000000` and `iter.000001`; these should not be forced into a
physical `iter_000000/train/explore/label` layout.

Reasons:

- The same project can have multiple active-learning runs, and each run may
  start from `iter_000000`.
- Reset, retry, alternate experiment lines, and comparison experiments all need
  run context.
- Iterations depend on the corresponding run's controller config, selection
  thresholds, model committee, machine config, and approval records.
- Artifact lineage must trace back to a concrete run and iteration.
- Backends such as DP-GEN have native assumptions about current working
  directory, `record.dpgen`, and `iter.??????` directories. The runtime should
  not break those assumptions.

If the UI needs a project-level iteration overview, maintain an additional index
view:

```text
projects/<project_id>/iteration_index.jsonl
```

Example:

```json
{
  "run_id": "run_20260505_1330",
  "iteration_id": "iter_000003",
  "stage": "label_pending",
  "status": "blocked",
  "path": "runs/run_20260505_1330/iterations/iter_000003"
}
```

Conclusion:

- Normalized iteration metadata belongs under the run.
- Backend-native iteration workdirs belong under
  `runs/<run_id>/backend/<backend_name>/`.
- Iteration views may aggregate by project.

## 3. Runtime State

### 3.1 sessions

`sessions/` stores TUI/API session history.

Requirements:

- `/new` creates a new session.
- Chat history belongs to the current session by default.
- Re-entering the same root session should restore the latest active session.
- Current skills, MCP state, and project state must not be inferred from old
  session history.

### 3.2 logs

`logs/` stores runtime tool-call logs.

Requirements:

- Tool logs are session-scoped.
- New sessions get new tool logs.
- Runtime tool logs are separate from MLP training logs.
- Training logs are registered as project/run/iteration artifacts.

### 3.3 approvals

`approvals/` stores human approval state.

Requirements:

- Approvals are session-scoped or run-scoped depending on the approval object.
- Dangerous operations must block while waiting for approval.
- Approval decisions are persisted and can be referenced as artifact evidence.

Typical approval objects:

- Start a training run.
- Stop or reset a run.
- Submit label or DFT tasks.
- Overwrite existing controller config.
- Delete or archive run artifacts.

### 3.4 memory

`memory/` stores long-term preferences and stable facts.

Requirements:

- Memory may be shared across sessions.
- Memory is not authoritative for current skill inventory, MCP inventory, active
  project, or active run.
- Current state must come from workspace state, runtime config, and loader
  inventory.

## 4. Project State

### 4.1 project.json

`project.json` stores stable project-level information.

Example:

```json
{
  "project_id": "proj_fech_001",
  "name": "Fe-C-H active learning",
  "domain": "machine_learning_potential",
  "target_use_case": "compressed liquid and defect environments",
  "created_at": "2026-05-05T13:30:00+08:00",
  "active_run_id": "run_20260505_1330",
  "status": "active"
}
```

### 4.2 inventory

`inventory/` stores project-level resource inventories.

Recommended files:

| File | Contents |
| --- | --- |
| `datasets.jsonl` | Existing training, validation, and labeled datasets |
| `structures.jsonl` | Structure pools, candidate configurations, unlabeled configurations |
| `checkpoints.jsonl` | Model checkpoints, frozen models, committee members |
| `reference_data.jsonl` | DFT/reference data and calculation settings |
| `compute_resources.jsonl` | Local, cluster, queue, and container resources |

Inventory stores metadata and paths only. It does not store large coordinate
payloads.

### 4.3 plans

`plans/` stores active-learning plans and validation plans.

Requirements:

- A plan is intent and execution design, not run state.
- A skill may generate or modify a plan.
- At execution time, the plan should be copied or referenced into the concrete
  run so later plan edits do not contaminate run history.

## 5. Run State

### 5.1 run.json

`run.json` stores immutable or semi-stable metadata for one run.

Example:

```json
{
  "run_id": "run_20260505_1330",
  "project_id": "proj_fech_001",
  "controller_type": "active_learning_controller",
  "backend": "dpgen",
  "created_at": "2026-05-05T13:30:00+08:00",
  "plan_id": "active_learning_plan.v1",
  "status": "running"
}
```

Notes:

- `backend` may be `dpgen`, but directory and runtime interfaces should not be
  bound to DP-GEN.
- `controller_type` uses a generic name so future active-learning controllers
  can be supported.
- The backend-native run directory is located through `backend_workdir` or a
  convention such as `backend/dpgen`.

### 5.2 run_state.json

`run_state.json` stores current run state.

Example:

```json
{
  "stage": "explore",
  "iteration_id": "iter_000003",
  "status": "blocked",
  "blocking_reason": "label_approval_required",
  "updated_at": "2026-05-05T14:20:00+08:00"
}
```

### 5.3 controller

`controller/` stores controller inputs and rendered results.

Recommended contents:

- `controller.json`: runtime/MCP generic controller config.
- `generated_param.json`: training or active-learning parameters generated by a
  tool.
- `generated_machine.json`: machine or queue configuration generated by a tool.
- `rendered_inputs/`: input files actually consumed by the backend.
- `submit_scripts/`: backend submit scripts.

Naming principles:

- Use `controller` for the runtime directory name.
- Backend-specific files may keep their native names, such as DP-GEN
  `param.json` and `machine.json`.
- Do not name the top-level directory `dpgen`; that would make future migration
  harder.

### 5.4 backend

`backend/` stores the backend-native working directory. This directory is the
execution root for backend tools and does not need to follow MLP Copilot's
normalized iteration naming.

Recommended DP-GEN structure:

```text
projects/<project_id>/runs/<run_id>/backend/dpgen/
  param.json
  machine.json
  record.dpgen
  iter.000000/
    00.train/
    01.model_devi/
    02.fp/
  iter.000001/
  iter.000002/
```

Design requirements:

- DP-GEN should run with `backend/dpgen/` as cwd.
- `param.json` and `machine.json` keep DP-GEN native names.
- `record.dpgen` is an important input for DP-GEN resume and state parsing.
- `iter.??????/00.train`, `iter.??????/01.model_devi`, and
  `iter.??????/02.fp` remain unchanged.
- Runtime does not directly rewrite DP-GEN iteration directories.
- A projector/adapter maps DP-GEN native directories into normalized iteration,
  artifact, and companion state.

### 5.5 DP-GEN Phase Mapping

DP-GEN `run_iter(param_file, machine_file)` contains nine tasks per round. The
normalized phase should be a projected view and should not change physical
DP-GEN directories.

| MLP Copilot phase | DP-GEN task | DP-GEN directory |
| --- | ---: | --- |
| `train.prepare` | 0 `make_train` | `iter.??????/00.train` |
| `train.run` | 1 `run_train` | `iter.??????/00.train` |
| `train.collect` | 2 `post_train` | `iter.??????/00.train` |
| `explore.prepare` | 3 `make_model_devi` | `iter.??????/01.model_devi` |
| `explore.run` | 4 `run_model_devi` | `iter.??????/01.model_devi` |
| `explore.collect` | 5 `post_model_devi` | `iter.??????/01.model_devi` |
| `label.prepare` | 6 `make_fp` | `iter.??????/02.fp` |
| `label.run` | 7 `run_fp` | `iter.??????/02.fp` |
| `label.collect` | 8 `post_fp` | `iter.??????/02.fp` |

Suggested state parsing:

```text
read backend/dpgen/record.dpgen
  -> last_completed_iter, last_completed_task
  -> map to normalized phase
  -> scan backend/dpgen/iter.?????? for artifacts and diagnostics
  -> write run_state.json, artifacts.jsonl, ui/*.state.json
```

The DP-GEN adapter should only parse directories, map state, and register
artifacts/events. It must not make scientific judgments.

## 6. Artifact Design

An artifact is an evidence object in the workspace, not a plain file-list entry.

Recommended schema:

```json
{
  "artifact_id": "art_...",
  "project_id": "proj_...",
  "run_id": "run_...",
  "iteration_id": "iter_000003",
  "kind": "model_deviation",
  "role": "evidence",
  "name": "iter_000003 model deviation summary",
  "path": "/abs/path/to/file.json",
  "producer": "trainingController",
  "tool_call_id": "call_...",
  "status": "ready",
  "created_at": "2026-05-05T13:30:00+08:00",
  "size_bytes": 123456,
  "sha256": "...",
  "parents": ["art_..."],
  "metrics": {
    "max_deviation": 0.42,
    "selected_frames": 128
  },
  "tags": ["active_learning", "explore", "needs_review"],
  "summary": "High deviation found in compressed-volume structures."
}
```

Recommended `kind` values:

| kind | Example |
| --- | --- |
| `config` | controller config, param, machine |
| `dataset` | DeepMD npy data, raw labeled data |
| `structure_pool` | exploration candidate structures |
| `model_checkpoint` | frozen model, checkpoint |
| `training_metric` | loss curve, validation metric |
| `model_deviation` | committee deviation results |
| `label_task` | DFT labeling input tasks |
| `reference_result` | DFT/reference output |
| `report` | run report, failure report |
| `log` | controller, training, or labeling logs |
| `decision` | human approval and accept/reject reason |
| `run_record` | backend resume and phase record, such as `record.dpgen` |
| `diagnostic` | diagnostic output from failure analyzer or backend adapter |

Recommended `role` values:

| role | Meaning |
| --- | --- |
| `input` | Input to a run or iteration |
| `output` | Output generated by a tool |
| `evidence` | Decision evidence |
| `decision` | Human approval or selected outcome |
| `diagnostic` | Logs, error analysis, health checks |
| `report` | Summary report |

## 7. Artifacts Pane Design

The Artifacts pane should not be a plain file browser. It should be the evidence
chain view for the current project/run.

Core questions:

- What key artifacts exist for the current run?
- Which artifacts are inputs?
- Which artifacts were newly generated?
- Which artifacts determine the next step?
- Which artifacts require approval?
- Which artifacts are abnormal, missing, or stale?

Recommended table:

```text
Kind        Scope          Status     Name                         Metrics
config      run            ready      generated_param.json          -
model       iter_000002    ready      model committee               4 models
deviation   iter_000003    warning    high deviation candidates     max=0.42
label       iter_000003    pending    DFT label batch               128 tasks
report      run            ready      failure analysis              3 issues
```

Recommended operations:

| Operation | Meaning |
| --- | --- |
| filter | Filter by project, run, iteration, kind, status |
| inspect | Expand metadata, paths, parent/child links, and metric summaries |
| attach | Add artifact summary and path to current chat context |
| lineage | View artifact inputs and derived artifacts |
| approval | Link dangerous operations to approvals |
| open path | Show path or small-file summary without loading large file contents |
| health flags | Show missing files, checksum changes, metric anomalies, unapproved state, stale state |

Data sources for the Artifacts pane:

- `projects/<project_id>/runs/<run_id>/artifacts.jsonl`
- `projects/<project_id>/runs/<run_id>/iterations/<iteration_id>.json`
- Global `artifacts/artifacts.jsonl` or `artifacts/artifacts.duckdb`
- Artifact records registered by a projector from backend-native directories

Priority:

1. Current active project.
2. Current active run.
3. Current active iteration.
4. User filters.

The Artifacts pane must not infer artifacts from chat history or memory.

## 8. Companion Pane Design

The Companion pane is a deterministic project/run side panel, not a second
agent.

It should render from workspace state, not infer from chat history.

It may replace or extend the current TUI `Campaign` area.

Recommended display:

```text
Project
  Fe-C-H active learning

Goal
  Improve coverage for compressed liquid/defect environments

Active Run
  run_20260505_1330

Stage
  iter_000003 / explore -> label approval pending

Blocking Item
  128 DFT label tasks need approval

Health
  training: ok
  exploration: warning, high deviation cluster found
  labeling: pending
  artifact index: ok

Suggested Next
  1. inspect high-deviation candidates
  2. approve label batch
  3. generate iteration report
```

Recommended fields:

| Field | Source |
| --- | --- |
| project | `project.json` |
| goal | `project.json` or active plan |
| active run | `project.json.active_run_id` |
| stage | `run_state.json` |
| blocking item | `approvals.jsonl`, controller status, artifact status |
| health | MCP status, artifact index, run state, latest diagnostics |
| suggested next | Skill-generated from state/artifacts, with traceable source |

Companion must distinguish two suggestion types:

| Type | Meaning |
| --- | --- |
| deterministic next action | Derived directly from state machine, such as pending approval |
| advisory suggestion | Generated by a skill from artifact summaries and plans, with source labels |

Companion must not:

- Infer current skills from memory/history.
- Infer current active run from memory/history.
- Judge scientific conclusions directly.
- Invent coverage, error, or convergence state.
- Automatically run dangerous operations.

## 9. UI And Workspace State Relationship

Recommended state sources:

| UI area | Authoritative source |
| --- | --- |
| Chat | Current session history |
| Tool Log | Current session tool log |
| Artifacts | Active project/run artifact index |
| Approvals | Current session approvals plus run approvals |
| Companion | `project.json` plus `run_state.json` plus artifacts plus approvals |
| Skills/MCP status | Current loader inventory and MCP registry |

Important rules:

- `memory` may be shared.
- `session/log` should be isolated.
- `approval` is session-scoped or run-scoped depending on the object.
- `project/run/artifact` should be durable and shared.
- Current skills, MCP, active project, and active run must come from current
  inventory/state.
- UI must not restore runtime truth from historical answers.

## 10. UI Read Model And Auto-Refresh

`Artifacts` and `Companion` panes should use auto-refresh, but the UI should not
directly read backend run directories, DP-GEN directories, or training-program
logs.

Recommended architecture:

```text
MCP / backend tools
  -> artifact records / run events / approval events
  -> projector / reducer
  -> artifacts.state.json
  -> companion.state.json
  -> TUI panes auto-refresh
```

Core rules:

- Backend/MCP tools do not directly drive the UI.
- Backend/MCP tools only produce factual records such as artifacts, run events,
  approval events, and diagnostic events.
- A separate `projector` or `reducer` projects factual records into UI read
  models.
- `Artifacts` and `Companion` panes consume only UI read-model state files.
- UI read models are rebuildable caches, not the only source of truth.
- UI does not infer current project, run, artifact, skill, or MCP state from
  chat history or memory.

Recommended state-file location:

```text
projects/<project_id>/runs/<run_id>/ui/
  artifacts.state.json
  companion.state.json
```

For project-level overviews, add:

```text
projects/<project_id>/ui/
  artifacts.state.json
  companion.state.json
```

### 10.1 artifacts.state.json

`artifacts.state.json` is a read model for UI tables. It is not the complete
artifact ledger.

Example:

```json
{
  "schema_version": 1,
  "project_id": "proj_fech_001",
  "run_id": "run_20260505_1330",
  "revision": 42,
  "updated_at": "2026-05-05T14:30:00+08:00",
  "source": {
    "artifact_index_revision": 128,
    "run_state_revision": 31,
    "approval_revision": 7
  },
  "rows": [
    {
      "artifact_id": "art_001",
      "kind": "model_deviation",
      "scope": "iter_000003",
      "status": "warning",
      "name": "high deviation candidates",
      "metrics": {
        "max_deviation": 0.42,
        "selected_frames": 128
      },
      "path": "/abs/path/to/file.json",
      "health_flags": ["needs_review"]
    }
  ]
}
```

Design requirements:

- `revision` increases monotonically so the UI can decide whether to refresh.
- `schema_version` is required for future migration.
- `source` records projection sources so stale UI state can be diagnosed.
- `rows` contains only summary fields needed by the UI.
- Large file contents, full logs, and full coordinate data do not enter this
  file.

### 10.2 companion.state.json

`companion.state.json` is the status summary consumed by the Companion pane.

Example:

```json
{
  "schema_version": 1,
  "project_id": "proj_fech_001",
  "run_id": "run_20260505_1330",
  "revision": 42,
  "updated_at": "2026-05-05T14:30:00+08:00",
  "source": {
    "project_revision": 5,
    "run_state_revision": 31,
    "artifact_index_revision": 128,
    "approval_revision": 7
  },
  "project": {
    "name": "Fe-C-H active learning",
    "goal": "Improve compressed liquid and defect coverage"
  },
  "stage": {
    "iteration_id": "iter_000003",
    "phase": "explore",
    "status": "blocked"
  },
  "blocking_items": [
    {
      "kind": "approval",
      "message": "128 DFT label tasks need approval",
      "approval_id": "appr_001"
    }
  ],
  "health": [
    {
      "component": "exploration",
      "status": "warning",
      "message": "high deviation cluster found"
    }
  ],
  "suggested_next": [
    {
      "label": "inspect high-deviation candidates",
      "source_artifact_id": "art_001",
      "action": "inspect_artifact"
    }
  ]
}
```

Design requirements:

- Companion is a deterministic side panel, not a second agent.
- `blocking_items` must trace to an approval, artifact, run event, or diagnostic
  event.
- `health` must come from tool status, artifact metadata, or run state.
- `suggested_next` may come from a skill, but must include `source_artifact_id`,
  `approval_id`, `event_id`, or another traceable source.
- Companion does not directly judge scientific conclusions or invent coverage,
  error, or convergence state.

### 10.3 Projector / Reducer

The `projector` converts backend factual records into UI read models.

Inputs:

- `project.json`
- `run.json`
- `run_state.json`
- run-level `artifacts.jsonl`
- normalized iteration records
- approval records
- diagnostic records
- MCP status records
- backend-native status files, such as DP-GEN `record.dpgen`
- backend-native iteration directories, such as DP-GEN `iter.??????`

Outputs:

- `artifacts.state.json`
- `companion.state.json`

Implementation requirements:

- The projector does not execute scientific computation.
- The projector does not access DP-GEN/DeepMD-kit internal semantics unless those
  semantics have already been converted into generic artifact metadata by an MCP
  server.
- The projector may read backend-native directory structure and state anchors
  such as `record.dpgen`, `iter.??????/00.train`,
  `iter.??????/01.model_devi`, and `iter.??????/02.fp`.
- The projector can be rerun and rebuild UI state from source-of-truth records.
- The projector keeps schemas stable so TUI, Web UI, and API consumers can reuse
  them.

### 10.4 Auto-Refresh

TUI auto-refresh should use `mtime` polling or a file watcher.

Requirements:

- UI reads state files only.
- UI uses `revision` to decide whether redraw is needed.
- Projectors write files atomically.

Recommended write pattern:

```text
write artifacts.state.json.tmp
fsync
rename artifacts.state.json.tmp -> artifacts.state.json
```

This avoids the UI reading partial JSON.

Module boundaries:

| Module | Responsibility |
| --- | --- |
| MCP/backend | Produce factual records and file artifacts |
| ArtifactIndex | Store artifact ledger and query index |
| ApprovalManager | Store approval requests and decisions |
| projector/reducer | Generate UI read models |
| TUI panes | Read read models and render |
| skills | Generate plans, explain workflows, and provide traceable suggestions |

Benefits:

- Backend can be replaced.
- Projector can be replaced.
- TUI, Web UI, and API can share state files.
- UI is not coupled to DP-GEN, DeepMD-kit, Slurm, or a local runner.
- Read models are versioned, rebuildable, and easy to debug.

## 11. Follow-Up Implementation Advice

Suggested phases:

1. Define workspace schema and project/run initialization logic.
2. Implement the JSONL backend for ArtifactIndex.
3. Define backend workdir conventions, such as `runs/<run_id>/backend/dpgen/`.
4. Define minimal schemas for run events, approval events, and diagnostic events.
5. Make the existing training-controller MCP output artifact records and event
   records.
6. Implement a DP-GEN adapter/projector that reads `record.dpgen` and
   `iter.??????`, then generates normalized state.
7. Implement a generic projector/reducer that generates `artifacts.state.json`
   and `companion.state.json`.
8. Change the Artifacts pane from a file list into an artifact evidence table.
9. Replace the Campaign pane with the Companion pane.
10. Add project/run selector.
11. Add artifact inspect/attach/lineage operations.

Implementation boundaries:

- Runtime may implement `ArtifactIndex`, workspace schema, UI rendering, and
  approval binding.
- MCP servers generate MLP-domain artifacts and metrics.
- Skills explain workflows, generate plans, and suggest actions.
- Runtime does not implement MLP scientific algorithms.
