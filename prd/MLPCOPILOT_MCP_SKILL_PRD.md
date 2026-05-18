# PRD: MLP Copilot MCP And Skill Pack

## 1. Product Positioning

**MLP Copilot MCP And Skill Pack** is the machine-learning-potential plugin
capability layer that runs on top of MLP Copilot Runtime.

The plugin layer contains two capability types:

- **MCP servers**: executable, testable, remotely deployable tools such as
  DP-GEN control, dataset checks, model evaluation, coverage analysis, and report
  generation.
- **Skills**: methodology, workflow guidance, and human-collaboration strategy,
  such as active-learning strategy generation, training failure analysis, and
  validation-plan design.

This PRD does not define the `mlpcopilot` runtime TUI, Telegram gateway,
approvals, sessions, memory, or OpenAI-compatible API. Those are defined in
`MLPCOPILOT_RUNTIME_PRD.md`.

## 2. Background

The current MLP training flow uses **DeepMD-kit** as the training framework and
**DP-GEN** as the active-learning controller.

DP-GEN already handles:

- Running `dpgen run` from `param.json` and `machine.json`.
- Organizing active-learning iterations.
- Running training, model-deviation exploration, and first-principles labeling.
- Recording iteration and stage state through `record.dpgen`.
- Managing per-iteration artifacts through `iter.000000/00.train`,
  `01.model_devi`, and `02.fp`.
- Connecting to local, Slurm, PBS, SSH, and other compute resources through
  DPDispatcher.

MLP Copilot should not rewrite DP-GEN. It should first provide a **training-flow
controller plugin**:

- Generate an active-learning strategy from system and target information.
- Generate DP-GEN `param.json` and `machine.json`.
- Validate configuration files.
- Start, stop, reset, and inspect training runs.
- Read training state.
- Analyze DP-GEN error logs and suggest actionable fixes.

Capabilities not covered by DP-GEN, such as model-performance testing, database
coverage, local atomic-environment coverage, and configuration-gap analysis,
should be implemented later as separate MCP modules.

The first training-flow controller therefore needs a **backend/provider
abstraction**:

- The generic MCP name remains `mlp_training_controller_mcp`.
- DP-GEN is the first backend provider, not the overall plugin identity.
- Other active-learning or training-orchestration frameworks can be added later
  without changing the runtime or upper-level skills.
- Tools, artifacts, and reports use generic `training_*` names and record
  `backend: "dpgen"` in metadata.

## 3. Product Goals

1. Implement `mlp_training_controller_mcp` first, using a DP-GEN backend to bring
   the DeepMD-kit + DP-GEN main training flow into MLP Copilot.
2. Provide the `mlp-active-learning` skill to guide users from system goals to
   active-learning strategy.
3. Execute all actions through MCP tools and produce artifact paths, hashes,
   manifests, and errors.
4. Route all high-cost or destructive actions through runtime ApprovalManager as
   blocking approvals.
5. Keep DP-GEN and scientific analysis logic out of `mlpcopilot` core.
6. Support backend-specific config profiles, template files, remote resource
   config, and log diagnostics.
7. Redact, reference, and validate secrets in machine/resource configuration.
8. Maintain first-pass independent MCP modules for dataset validation, model
   evaluation, and report rendering; defer coverage analysis.
9. Pass large data, trajectories, structures, and full logs by file path,
   artifact id, or object reference instead of LLM context.

## 4. Non-Goals

1. Do not modify runtime approval, TUI, channels, session, or API internals.
2. Do not rewrite the DP-GEN main loop.
3. Do not replace DeepMD-kit, LAMMPS, VASP, ABACUS, CP2K, Gaussian, or other
   backend software.
4. Do not let the LLM directly generate scientific metrics.
5. Do not automatically declare a model reliable or ready.
6. Do not bind the training-flow controller name or interface permanently to
   DP-GEN.
7. Do not implement full model-generalization benchmarks in the training-flow
   controller.
8. Do not implement local atomic-environment coverage algorithms in the
   training-flow controller.
9. Do not cancel remote HPC queue jobs by default unless the user explicitly
   requests it and approval passes.
10. Do not expose plaintext passwords, tokens, private keys, or SSH secrets in
    artifacts, log summaries, or LLM context.

## 5. Plugin Boundaries

| Plugin type | Owns | Does not own |
|---|---|---|
| `mlp_training_controller_mcp` | Generic training-flow control; first backend is DP-GEN; config generation, validation, start, stop, reset, status read, log diagnosis, run report | Model generalization evaluation, database coverage algorithms, local environment analysis |
| `mlp_dataset_mcp` | Current dataset file layout, schema, basic integrity, hashes, and report artifacts | Training-run control; deep checks such as units, abnormal structures, duplicates, split leakage, and fixed OOD/gap detection are deferred |
| `mlp_model_eval_mcp` | Checkpoint performance evaluation, benchmarks, model comparison | DP-GEN process management |
| `mlp_coverage_mcp` | Low-priority backlog for data coverage, local atomic-environment coverage, configuration gaps | Not implemented now; DP-GEN scheduling |
| `mlp_report_mcp` | Current Markdown evidence report from existing runs, data, models, and approval evidence | Generating scientific metrics that were not produced by tools; HTML/PDF is deferred |
| Skills | Process, strategy, explanation, risk framing, tool-call order | Direct scientific computation or fabricated metrics |

Approval is owned by the runtime. MCP servers keep standard tool semantics and
standard JSON output; they must not declare `approval_hint`, `requires_approval`,
or expose bypass parameters such as `approved=true`.

## 5.1 Current Priority Adjustment

As of 2026-05-09, near-term plugin work is "stabilize implemented capabilities
and provide project-specific OOD test advice." Do not reintroduce the full
coverage/job module set, and do not make a fixed OOD validation workflow a
generic tool.

Near-term priorities:

1. P0: Maintain and harden the implemented training controller, first-pass
   dataset MCP, first-pass model-evaluation MCP, first-pass report MCP, and
   corresponding skills.
2. P0/P1: Add and maintain the `mlp-ood-test-advisor` skill so users can choose
   OOD test slices, artifacts, and approval gates based on target system,
   deployment boundary, reference budget, and existing evidence.
3. P1: For concrete projects, design minimal OOD/gap evidence artifacts based on
   the specific chemical system and reviewer questions. Do not hard-code a fixed
   OOD validation workflow as generic MCP behavior.
4. P1: Fix bugs, add documentation, and add a small number of evidence fields
   around real DP-GEN/DeePMD projects without introducing large modules.
5. P2: Keep the full coverage MCP, job MCP, deep dataset science checks, fixed
   OOD/gap audit tools, and HTML/PDF report output in backlog. They are not
   current acceptance blockers.

Do not proactively advance P2 backlog work unless the user explicitly raises its
priority.

## 6. Recommended Package Structure

```text
mlpcopilot-plugins/
├── mcp/
│   ├── mlp_training_controller_mcp/
│   │   ├── server.py
│   │   ├── controller.py
│   │   ├── config_builder.py
│   │   ├── status.py
│   │   ├── log_analyzer.py
│   │   ├── template_assets.py
│   │   ├── secret_redactor.py
│   │   ├── schemas.py
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   └── dpgen.py
│   │   └── templates/
│   ├── mlp_dataset_mcp/
│   ├── mlp_model_eval_mcp/
│   ├── mlp_coverage_mcp/
│   ├── mlp_job_mcp/
│   └── mlp_report_mcp/
├── skills/
│   ├── mlp-active-learning/
│   │   └── SKILL.md
│   ├── mlp-dataset-validation/
│   │   └── SKILL.md
│   ├── mlp-validation-planner/
│   │   └── SKILL.md
│   ├── mlp-checkpoint-auditor/
│   │   └── SKILL.md
│   └── mlp-failure-analysis/
│       └── SKILL.md
├── schemas/
├── templates/
└── examples/
```

First version must implement:

1. `mlp_training_controller_mcp`
2. `mlp-active-learning` skill

Current state has already exceeded the first-version requirement by adding
first-pass dataset, model-evaluation, and report modules. `mlp_coverage_mcp/`
and `mlp_job_mcp/` remain backlog placeholders, not current implementation
requirements.

### 6.1 MCP Organization Principle

Do not merge all MLP tools into one MCP server. That increases maintenance,
testing, permission-boundary, and reviewer-explanation complexity. Keep the
current responsibility split:

- `mlp_training_controller_mcp`: training-flow control and DP-GEN backend.
- `mlp_dataset_mcp`: dataset file-level checks.
- `mlp_model_eval_mcp`: checkpoint benchmarks, predictions, and metrics
  artifacts.
- `mlp_report_mcp`: cross-tool evidence aggregation and audit reports.

Uniformity is provided by the runtime: MCP discovery, tool approvals, tool logs,
artifact indexing, run manifests, TUI/API display, and workspace path
conventions. Plugins only need to provide standard MCP tools and reproducible
artifacts.

## 7. MCP Deployment Modes

Support three deployment modes:

| Mode | Scenario |
|---|---|
| `stdio` | Local development, workstation use, local training projects |
| `sse` | Remote service compatible with SSE MCP endpoints |
| `streamableHttp` | Recommended remote HTTP MCP endpoint |

Remote deployment is suitable for:

- HPC login nodes.
- Data servers.
- GPU workstations.
- Internal MLP tool services.

Remote security requirements:

- Support token or mTLS authentication.
- Restrict workspace root or project namespace.
- Limit resources per task.
- Limit response body size.
- Return large logs and large structure files through artifact paths.

## 8. Common MCP Output Protocol

All MCP tools return JSON text with this structure:

```json
{
  "status": "success|failed|blocked",
  "summary": "...",
  "metrics": {},
  "artifacts": [
    {
      "type": "report|metrics|figure|log|structure|manifest|config|status",
      "path": "...",
      "sha256": "..."
    }
  ],
  "warnings": [],
  "errors": []
}
```

Rules:

- Do not return natural language only.
- Generated files must have paths.
- Important inputs must have hashes.
- When cache is used, report cache key, cache source, and input hash.
- Long tasks return a job id, run id, or controller state id.
- MCP output may include summaries, but must not place large logs,
  trajectories, or full structures into LLM context.
- MCP tools do not implement runtime approval themselves. Runtime approval
  policy intercepts all agent-side MCP calls; exact allowlist entries may bypass
  approval.

## 9. MLP Training Controller MCP

The first required MCP module is `mlp_training_controller_mcp`.

### 9.1 Goals

Integrate MLP active learning and training orchestration through a generic
training-flow controller. The first backend is DP-GEN; later backends may target
other active-learning frameworks or training schedulers.

The controller provides:

- Training project inspection.
- Generation of backend-native parameter files from active-learning strategy.
- Generation of backend-native machine/resource files from machine resource
  configuration.
- Training backend config validation.
- Training run start, stop, and reset.
- Training iteration status readout.
- Training log and failure-cause analysis.
- Training run report and artifact manifest.

### 9.2 Backend Provider Model

The training-flow controller must provide a backend provider interface.

First provider:

```text
backend = "dpgen"
```

The DP-GEN provider owns:

- Detecting `param.json`, `machine.json`, `record.dpgen`, and `dpgen.log`.
- Detecting `iter.??????/00.train`, `01.model_devi`, and `02.fp`.
- Validating `param.json` and `machine.json` with DP-GEN `dargs` schema.
- Parsing DP-GEN stage.
- Starting `dpgen run param.json machine.json`.
- Diagnosing common DP-GEN, DPDispatcher, DeepMD-kit, LAMMPS, CP2K, VASP,
  ABACUS, and related errors.

Generic controller metadata must record:

```json
{
  "backend": "dpgen",
  "backend_version": "...",
  "training_engine": "deepmd-kit",
  "exploration_engine": "lammps",
  "labeling_engine": "cp2k|vasp|abacus|pwscf|gaussian|custom"
}
```

### 9.3 Existing DP-GEN Backend Conventions

DP-GEN main entrypoint:

```text
dpgen run param.json machine.json
```

DP-GEN per-round directory:

```text
iter.000000/
├── 00.train/
├── 01.model_devi/
└── 02.fp/
```

Training state file:

```text
record.dpgen
```

`record.dpgen` line format:

```text
<iteration_index> <stage_index>
```

Stage mapping:

| Stage | DP-GEN stage |
|---:|---|
| 0 | `make_train` |
| 1 | `run_train` |
| 2 | `post_train` |
| 3 | `make_model_devi` |
| 4 | `run_model_devi` |
| 5 | `post_model_devi` |
| 6 | `make_fp` |
| 7 | `run_fp` |
| 8 | `post_fp` |

### 9.4 Tool List

First-version tools:

```text
inspect_training_project(project_path, backend="auto")
generate_training_param(backend, system_profile_path, strategy_config_path, output_path)
generate_training_machine(backend, machine_profile_path, output_path)
validate_training_inputs(backend, param_path, machine_path)
start_training_run(backend, project_path, param_path, machine_path)
stop_training_run(run_id)
reset_training_run(backend, project_path, target_iteration, target_stage, mode)
get_training_status(project_path, backend="auto")
list_training_iterations(project_path, backend="auto")
inspect_training_iteration(project_path, iteration, backend="auto")
collect_training_logs(project_path, backend="auto")
analyze_training_failure(project_path, backend="auto")
build_training_run_report(project_path, backend="auto")
```

The first development slice implements only read-only and low-risk tools:

```text
inspect_training_project
validate_training_inputs
get_training_status
list_training_iterations
inspect_training_iteration
collect_training_logs
analyze_training_failure
```

### 9.5 `inspect_training_project`

Input:

```text
project_path
```

Checks:

- `param.json` exists.
- `machine.json` exists.
- `record.dpgen` exists.
- `dpgen.log` exists.
- `iter.??????` directories exist.
- `00.train`, `01.model_devi`, and `02.fp` are present.
- Controller state exists.

Output:

```json
{
  "status": "success",
  "summary": "Detected DP-GEN project with 4 iterations.",
  "metrics": {
    "iterations_found": 4,
    "has_record": true,
    "has_log": true,
    "has_param": true,
    "has_machine": true
  },
  "artifacts": []
}
```

### 9.6 `generate_training_param`

Inputs:

```text
system_profile_path
strategy_config_path
output_path
```

`system_profile.json` describes the system:

```json
{
  "elements": ["Li", "P", "S", "Cl"],
  "system_type": "bulk|surface|interface|molecule|reaction|amorphous",
  "initial_data": ["datasets/init"],
  "exploration_structures": ["structures/**/*.vasp"],
  "target_conditions": {
    "temperature_k": [300, 600, 900],
    "pressure_bar": [1, 10000],
    "ensemble": ["nvt", "npt"]
  }
}
```

`strategy_config.json` describes active-learning strategy:

```json
{
  "numb_models": 4,
  "iterations": 8,
  "model_devi_f_trust_lo": 0.05,
  "model_devi_f_trust_hi": 0.15,
  "fp_task_min": 5,
  "fp_task_max": 100,
  "fp_style": "vasp",
  "train_backend": "pytorch"
}
```

Generated files:

```text
runs/<run_id>/training_param.json
runs/<run_id>/training_param_generation_report.md
```

Requirements:

- Validate generated output with DP-GEN `dargs` schema.
- Do not hard-code one material system.
- Do not decide final high-cost strategy for the user; provide suggestions and
  approval-ready config.
- Preserve input file hashes.
- Support backend-specific template assets, such as LAMMPS input templates,
  CP2K input templates, and DFT-D3 parameter file references.
- Support DP-GEN `model_devi_jobs[*].template` and `rev_mat` parameter matrices.
- Validate that variables declared in `rev_mat` have corresponding placeholders
  in template files.
- Record template path, sha256, and purpose.
- Do not inject full template text into LLM context; return summary, path, and
  hash.

### 9.7 `generate_training_machine`

Inputs:

```text
machine_profile_path
output_path
```

`machine_profile.json` describes compute resources:

```json
{
  "train": {
    "command": "dp",
    "batch_type": "Slurm",
    "context_type": "local",
    "gpu_per_node": 1,
    "cpu_per_node": 8,
    "group_size": 1,
    "queue_name": "gpu"
  },
  "model_devi": {
    "command": "lmp",
    "batch_type": "Slurm",
    "context_type": "local",
    "gpu_per_node": 1,
    "cpu_per_node": 8,
    "group_size": 10
  },
  "fp": {
    "command": "bash /path/to/cp2k_cpu_wrapper.sh -in *.inp",
    "batch_type": "shell|PBS|Slurm",
    "context_type": "SSHContext",
    "cpu_per_node": 32,
    "gpu_per_node": 0,
    "group_size": 5,
    "remote_root": "/remote/work/path",
    "source_list": ["/path/to/env.sh"]
  }
}
```

Generated files:

```text
runs/<run_id>/training_machine.json
runs/<run_id>/training_machine_generation_report.md
```

Requirements:

- Do not store plaintext passwords.
- Remote authentication information is provided through environment variables,
  SSH config, tokens, or external secret references.
- Output must flag resource risks such as remote queues, GPU count, and FP task
  count.
- Support `SSHContext`, local context, shell wrapper command, Slurm, PBS, and
  other resource modes.
- Support common Singularity/container wrapper scripts, while recording the
  command as an auditable artifact.
- Redact `password`, `token`, `private_key`, `secret`, and similar fields in
  displays and reports.
- If an input machine file contains plaintext secrets, validation returns a
  high-priority warning and recommends moving to secret references.

### 9.8 Template Asset Handling

Training config often depends on external templates and resource files. The
training-flow controller must treat these files as artifacts.

First version should support:

```text
LAMMPS model deviation template
CP2K external_input_path
CP2K DFT-D3 parameter file reference
VASP INCAR/KPOINTS/POTCAR path references
ABACUS INPUT/KPT/STRU path references
custom wrapper command scripts
```

Template asset rules:

- All template paths must exist unless the user explicitly chooses draft mode.
- All templates must record sha256.
- All templates must record backend, stage, and consumer, such as
  `dpgen.model_devi.lammps` or `dpgen.fp.cp2k`.
- Do not copy large files into LLM context.
- For wrapper commands, record only command string, resolved executable,
  hashable script path, and resource summary.
- For CP2K `external_input_path`, validate the referenced path and actual file
  name.
- For LAMMPS `rev_mat`, validate variable names against template placeholders.

### 9.9 `validate_training_inputs`

Inputs:

```text
param_json_path
machine_json_path
```

Validation:

- JSON/YAML syntax.
- DP-GEN `run_jdata_arginfo` schema.
- DP-GEN `run_mdata_arginfo` schema.
- Basic consistency between `type_map` and `mass_map`.
- Existence of `init_data_sys` paths.
- Whether `init_batch_size` length matches `init_data_sys`.
- Two-dimensional structure and path existence for `sys_configs`.
- Whether `sys_batch_size` length matches `sys_configs`.
- Whether `model_devi_jobs[*].sys_idx` is in range.
- Whether `model_devi_jobs[*].template` files exist.
- Whether `model_devi_jobs[*].rev_mat` variables are found in corresponding
  templates.
- Whether required fields exist for the selected `fp_style`.
- Whether backend asset paths exist, including `external_input_path`, INCAR,
  POTCAR, KPT, basis, potential, and DFT-D3 files.
- Whether `machine.json` contains top-level `train`, `model_devi`, and `fp`
  objects for the current DP-GEN schema.
- Whether `api_version` should be `1.0` or above; incompatible old DPDispatcher
  key layouts or list-of-dicts stage layouts should produce migration advice,
  not silent conversion.
- Whether `machine.json` contains plaintext secrets.
- Whether `remote_root` is separated by train/model_devi/fp or explicitly
  reused.
- Whether shell wrapper commands have unauditable risks, such as no recorded
  script path or dependence on unknown environment state.

Outputs:

```text
runs/<run_id>/training_input_validation.json
runs/<run_id>/training_input_validation.md
```

### 9.10 `start_training_run`

Inputs:

```text
project_path
param_json_path
machine_json_path
```

Behavior:

- Start `dpgen run param.json machine.json` under `project_path`.
- Run it as a background process.
- Record PID, command, cwd, environment summary, param hash, and machine hash.
- Write controller state.
- Return run id and log paths.

Artifacts:

```text
runs/<run_id>/training_controller_state.json
runs/<run_id>/manifest.json
runs/<run_id>/logs/dpgen.stdout.log
runs/<run_id>/logs/dpgen.stderr.log
```

Implemented state:

- `start_training_run` / `stop_training_run` write or update
  `runs/<run_id>/manifest.json`.
- The manifest records param/machine hashes, controller state, log artifacts,
  operation events, and runtime decision references.

Approval:

- The MCP tool itself does not accept approval parameters.
- Calls through the MLP Copilot agent must be approved by runtime
  ApprovalManager.
- The approval request includes command, cwd, param hash, machine hash, and
  resource summary.

### 9.11 `stop_training_run`

Input:

```text
run_id
```

Behavior:

- First version stops only the local training-controller process.
- It does not cancel already submitted Slurm/PBS/SSH remote jobs by default.
- If remote jobs may still be running, return warnings and suggested next
  actions.

Approval:

- The MCP tool itself does not accept approval parameters.
- Calls through the MLP Copilot agent must be approved by runtime
  ApprovalManager.

Later extension:

```text
cancel_remote_jobs(run_id, scheduler, job_ids)
```

That tool must have a separate approval.

### 9.12 `reset_training_run`

Inputs:

```text
project_path
target_iteration
target_stage
mode
```

`mode`:

| Mode | Behavior |
|---|---|
| `soft` | Back up and rewrite `record.dpgen` so DP-GEN resumes from the target iteration/stage |
| `hard` | Back up and remove `iter.*` directories after the target, then rewrite `record.dpgen` |

Requirements:

- Always back up first.
- Generate a reset plan.
- Calls through the MLP Copilot agent must be approved by runtime
  ApprovalManager.
- Do not delete remote task directories by default.

Artifacts:

```text
runs/<run_id>/training_reset_plan.json
runs/<run_id>/training_reset_report.md
backups/dpgen_reset_<timestamp>/
```

### 9.13 `get_training_status`

Input:

```text
project_path
```

Reads:

- Last line of `record.dpgen`.
- Tail of `dpgen.log`.
- `iter.??????` directories.
- Current iteration `00.train`, `01.model_devi`, and `02.fp`.
- `candidate*.out`, `rest_failed*.out`, `rest_accurate*.out`.
- `02.fp/task.*`, `OUTCAR`, `vasprun.xml`, `data.*`.

Output:

```json
{
  "status": "success",
  "summary": "DP-GEN is at iter.000003 stage 4 run_model_devi.",
  "metrics": {
    "current_iteration": 3,
    "current_stage": 4,
    "stage_name": "run_model_devi",
    "iterations_found": 4,
    "candidate_frames": 120,
    "failed_frames": 18,
    "accurate_frames": 850,
    "fp_tasks": 64
  },
  "artifacts": [
    {
      "type": "status",
      "path": "runs/run_x/training_status.json",
      "sha256": "..."
    }
  ],
  "warnings": [],
  "errors": []
}
```

### 9.14 `analyze_training_failure`

Input:

```text
project_path
```

Candidate logs:

```text
dpgen.log
record.dpgen
iter.*/00.train/*/train.log
iter.*/01.model_devi/task.*/model_devi.out
iter.*/02.fp/task.*/OUTCAR
iter.*/02.fp/task.*/vasprun.xml
iter.*/02.fp/task.*/err
iter.*/02.fp/task.*/log
```

First-version rule set:

| Error pattern | Diagnostic direction |
|---|---|
| `Command not found` | Environment not activated, software missing, or machine command wrong |
| `JSONDecodeError` | JSON syntax error |
| `ArgumentKeyError` | DP-GEN strict schema rejects old or unknown fields |
| `ArgumentTypeError` | Field type error |
| `FileNotFoundError ... graph.xxx.pb` | Training did not produce a model; inspect initial data and train log |
| `cannot find valid data system` | `init_data_sys` or dataset path problem |
| `job failed 3 times` | DPDispatcher remote job failed; inspect `remote_root` and `.sub` scripts |
| `too many unsuccessfully terminated jobs` | FP failure ratio too high; inspect inputs or tune `ratio_failure` |
| `OUTCAR not convergence` | First-principles task did not converge |
| `batch_size` / `numb_test` | Too few data frames or `fp_task_min` too small |
| `sys_idx` out of range | `model_devi_jobs[*].sys_idx` does not match `sys_configs` |

Output:

```json
{
  "failure_type": "dpdispatcher_job_failed",
  "evidence": [
    "RuntimeError: job failed 3 times",
    "remote_root=/path/to/remote"
  ],
  "likely_causes": [
    "remote environment missing executable",
    "input file invalid",
    "scheduler resource mismatch"
  ],
  "recommended_actions": [
    "check train.log under remote_root",
    "verify source_list in machine.json",
    "manually run generated .sub script"
  ]
}
```

Rules:

- Full logs do not enter LLM context.
- Output must include evidence snippets and corresponding paths.
- Recommendations must be actionable.
- If no diagnosis is possible, return `unknown` and list the next artifacts to
  inspect.

### 9.15 Training Run Report

`build_training_run_report` generates:

```text
runs/<run_id>/training_run_report.md
runs/<run_id>/training_status.json
runs/<run_id>/training_iteration_metrics.json
runs/<run_id>/manifest.json
```

Report sections:

1. Project summary.
2. Param and machine hash.
3. Current status.
4. Iteration timeline.
5. Train stage summary.
6. Model deviation summary.
7. FP labeling summary.
8. Failure or warning summary.
9. Approval and action history.
10. Recommended next operational actions.

The report must not claim checkpoint reliability. Checkpoint reliability is owned
by `mlp_model_eval_mcp`.

## 10. `mlp-active-learning` Skill

The first required skill is `mlp-active-learning`.

### 10.1 Goal

Guide users from MLP training goals to active-learning configuration and
execution plan.

### 10.2 Skill Responsibilities

The skill owns:

- Asking about target system, elements, phases, temperature/pressure ranges, and
  target application.
- Asking about existing initial data, structure sources, compute resources, and
  FP backend.
- Helping the user choose active-learning strategy.
- Calling `generate_training_param`.
- Calling `generate_training_machine`.
- Calling `validate_training_inputs`.
- Asking for user approval before starting `start_training_run`.
- Explaining current state and next steps from `get_training_status` and
  `analyze_training_failure`.

The skill does not own:

- Directly executing DP-GEN.
- Directly generating scientific metrics.
- Directly judging model readiness.
- Modifying runtime internals.

### 10.3 Suggested Flow

```text
1. Collect system and target.
2. Collect existing data and exploration structures.
3. Collect compute resources and FP backend.
4. Generate system_profile.json.
5. Generate strategy_config.json.
6. Call generate_training_param.
7. Call generate_training_machine.
8. Call validate_training_inputs.
9. Show risk and resource summary.
10. Request approval.
11. Call start_training_run.
12. Periodically call get_training_status.
13. On failure, call analyze_training_failure.
14. Generate training_run_report.
```

## 11. Dataset Validation MCP

First version implemented: `mlp_dataset_mcp`.

Current scope is a lightweight file-level dataset MCP:
`inspect_dataset`, `validate_dataset_schema`, `validate_dataset_integrity`, and
`build_dataset_validation_report`. OOD testing is first handled by the
`mlp-ood-test-advisor` skill as project-specific advice. Fixed OOD/gap audit
tools are not current default capabilities.

Low-priority backlog: heavy checks such as units, structure sanity, duplicates,
split leakage, label consistency, and coverage are deferred and are not current
acceptance criteria.

### 11.1 Goal

The current goal is to inspect MLP dataset file layout, schema, basic integrity,
hashes, and report artifacts. Deep scientific checks remain backlog.

### 11.2 Tool List

Current tools:

```text
inspect_dataset(dataset_path)
validate_dataset_schema(dataset_path, schema_path)
validate_dataset_integrity(dataset_path)
build_dataset_validation_report(dataset_path, output_path, max_files)
```

Low-priority backlog:

```text
check_unit_consistency(dataset_path)
check_structure_sanity(dataset_path)
detect_duplicate_or_near_duplicate_structures(dataset_path)
detect_split_leakage(dataset_path, split_config_path)
validate_split_strategy(dataset_path, split_config_path, target_use_case)
validate_label_consistency(dataset_path, reference_config_path)
detect_label_outliers(dataset_path)
dataset_coverage_report(dataset_path, target_domain_path)
```

Dataset validation does not start DP-GEN and does not declare checkpoint
usability.

### 11.3 OOD Test Advisory

Current OOD capability is a skill, not a fixed dataset MCP tool. Chemical
systems, phase space, deployment boundaries, and reference budgets differ too
much; a single OOD/gap checklist can create false confidence.

Skill:

```text
mlp-ood-test-advisor
```

Input semantics:

- `dataset_path`: training/validation dataset root or manifest.
- `target_use_case`: target application domain and
  composition/phase/temperature/pressure/strain/ensemble boundaries.
- `suspected_ood_sources`: reviewer-raised challenge structures, finite
  clusters, surface/interface cases, failed DP-GEN clusters, production failure
  cases, and similar sources.
- `checkpoint_path`, `model_eval_report_path`, `dataset_report_path`: existing
  evidence artifacts.
- `reference_budget`: affordable DFT/ab initio label count, HPC/GPU limits, and
  walltime.

Output:

- Project-specific OOD test-slice suggestions.
- Required input paths, reference calculations, checkpoint evaluations,
  artifacts, and approval gates for each slice.
- Missing evidence and remaining risk.
- If the user explicitly needs citable evidence artifacts, define project-level
  MCP tooling or manual artifact formats afterward.

Boundaries:

- Do not claim complete local-environment coverage analysis.
- Do not generate descriptor matrices or load large coordinates into LLM
  context.
- Do not use the LLM to judge "sufficiently covered"; conclusions can only be
  evidence present, missing, or insufficient.
- If local-environment coverage, candidate ranking, or descriptor-based gap
  analysis is needed later, raise `mlp_coverage_mcp` priority.

## 12. Model Evaluation MCP

Third-stage module: `mlp_model_eval_mcp`.

Current implementation includes checkpoint metadata, precomputed metric artifact
handling, a DeePMD-kit v3 `dp test` benchmark entrypoint, and single-structure
or batch prediction through ASE + DeePMD-kit v3 `deepmd.calculator.DP`:
`inspect_checkpoint`, `run_deepmd_test`, `predict_energy_force`,
`batch_predict`, `validate_checkpoint_on_dataset`, `compare_checkpoints`,
`build_checkpoint_metrics`, `build_benchmark_plots`, and
`build_checkpoint_benchmark_report`.

Metrics must come from existing artifacts, `dp test` output, or ASE/DeepMD
prediction results. Tools own hashes, logs, detail files, normalization,
threshold checks, comparison summaries, PNG plot artifacts, and Markdown
benchmark reports. The `mlp-checkpoint-evaluation` skill constrains the agent to
state model quality only from evidence artifacts.

Goals:

- Evaluate DeepMD checkpoints on independent benchmark sets.
- Generate energy, force, stress, and related error metrics.
- Compare multiple checkpoints.
- Output artifacts and manifests.

Tools:

```text
inspect_checkpoint(checkpoint_path)
run_deepmd_test(checkpoint_path, dataset_path, data_source, dp_command, backend, ...)
predict_energy_force(structure_path, checkpoint_path)
batch_predict(structure_dir, checkpoint_path)
validate_checkpoint_on_dataset(checkpoint_path, dataset_path, metric_config_path)
compare_checkpoints(checkpoint_a, checkpoint_b, dataset_path, metric_config_path)
build_checkpoint_metrics(run_id)
build_benchmark_plots(metrics_path, detail_prefix, output_dir)
build_checkpoint_benchmark_report(metrics_path, checkpoint_path, dataset_path)
```

Requirements:

- Checkpoints must record hashes.
- Datasets must record hashes.
- Metrics must come from tool execution results.
- The LLM does not judge model readiness.

## 13. Coverage MCP

Low-priority backlog: `mlp_coverage_mcp`.

Not implemented now. Current OOD testing is project-specific advice from
`mlp-ood-test-advisor`; it is not equivalent to a full coverage MCP. Raise this
module only when the user explicitly needs descriptor-based coverage analysis,
candidate-structure ranking, or local-environment gap evidence.

Goals:

- Analyze current database coverage.
- Identify missing configuration types.
- Analyze local atomic-environment coverage.
- Provide evidence for later DP-GEN exploration strategy.

Draft tools:

```text
build_structure_descriptors(dataset_path, descriptor_config_path)
analyze_local_environment_coverage(dataset_path, target_domain_path)
find_coverage_gaps(dataset_path, target_domain_path)
rank_candidate_structures_for_labeling(candidate_pool_path, coverage_model_path)
build_coverage_report(dataset_path, target_domain_path)
```

Requirements:

- Coverage metrics must come from tool artifacts.
- Do not place large descriptor matrices into LLM context.
- Do not couple to the training-flow controller.

## 14. Job MCP

Low-priority backlog: `mlp_job_mcp`.

Not implemented now. The existing training controller and DPDispatcher evidence
readout are enough for local DP-GEN workflows. Independent HPC queue management
should be implemented only when real Slurm/PBS/LSF operational closure is
needed.

Goals:

- Query HPC queues.
- Query Slurm/PBS/LSF job state.
- Map DP-GEN remote jobs to local runs.
- Support remote job cancellation.

Requirements:

- Job cancellation must be approved.
- Do not kill jobs by default.
- Record scheduler, job id, command, and decision id.

## 15. Report MCP

Current implementation includes a lightweight `mlp_report_mcp` that generates a
Markdown evidence report from existing workspace run manifests, artifact
references, pending/decision approval records, and explicit artifact paths.
Report MCP only summarizes existing evidence. It does not generate new
scientific metrics or declare models ready. A fixed one-command
`build_mlp_audit_report` is not a current default goal. If a concrete project
needs one, `mlp-ood-test-advisor` should first define evidence inputs and
reviewer questions, then project-specific report tooling can be added.

Current goals:

- Summarize existing training runs, dataset validation, model evaluation, and
  approval decisions.
- Generate Markdown reports.
- Require every conclusion to cite artifacts.
- Summarize existing checkpoint, dataset, OOD advice/evidence artifacts, and
  human decisions. Project-specific one-command audit reports are not current
  acceptance blockers.

### 15.1 Project-Specific Audit Report Backlog

Fixed one-command audit reports are project-specific backlog. Implement a report
tool only when a project has explicit evidence inputs, OOD slices, approval
decisions, and reviewer questions.

Possible tool:

```text
build_mlp_audit_report(
  model_eval_report_path,
  checkpoint_path,
  dataset_report_path,
  ood_gap_audit_path,
  approval_id,
  approval_decision_path,
  output_dir,
  title
)
```

Input semantics:

- `model_eval_report_path`: benchmark report, metrics JSON, or manifest from
  `mlp_model_eval_mcp`.
- `checkpoint_path`: audited model/checkpoint path; hash required.
- `dataset_report_path`: dataset validation report from `mlp_dataset_mcp`; may
  be empty but must be marked missing.
- `ood_gap_audit_path`: project-specific OOD advice, OOD evidence, or gap
  evidence artifact; may be empty but must be marked missing. Do not assume a
  fixed generic tool exists.
- `approval_id`: approval ID in workspace ApprovalManager; the tool should parse
  the corresponding decision record.
- `approval_decision_path`: explicit approval decision JSON path when
  `approval_id` cannot be resolved.
- `output_dir`: report output directory.
- `title`: optional report title.

Output artifacts:

- `mlp_audit_report.md`: human-readable integrated report for manuscript
  revision and review.
- `mlp_audit_summary.json`: machine-readable summary with input artifacts,
  hashes, metrics summary, approval state, missing evidence, and warnings.

If implemented, the report must include:

- Checkpoint path, hash, tool version, and evaluation time.
- Source artifacts for model-evaluation metrics; no recomputation or fabricated
  metrics.
- Dataset validation evidence and project-specific OOD/dataset-gap
  advice/evidence.
- Approval decision: state, approver/source, time, reason, and linked tool call
  or artifact.
- Missing evidence section: all missing inputs are explicitly listed and never
  silently skipped.
- Conservative conclusion: summarize evidence state only, without deciding for
  the user whether the model is publishable or production-ready.

Low-priority backlog:

- HTML/PDF output.
- Full coverage analysis in integrated reports.
- More complex cross-run report templates.

Reports must not fabricate metrics that were not executed.

## 16. Capability Discovery

MLP Copilot does not maintain a separate workspace capability definition file.
MCP and skill sources are:

- Source-tree MCPs: auto-discovered from `mlpcopilot/mcps/*/pyproject.toml`,
  requiring an MCP entrypoint under `[project.scripts]`.
- Workspace MCPs: explicitly configured by the user under
  `tools.mcpServers`.
- Source-tree skills: auto-discovered from `mlpcopilot/skills/*/SKILL.md`.
- Workspace skills: auto-discovered from active workspace
  `skills/*/SKILL.md`.
- Enabled lists, disabled lists, allowlists, and tool timeouts are controlled by
  config. Defaults apply only when fields are absent and must not override
  explicit user config.

TUI/API may display current runtime discovery and connection state. That state
is a runtime read model, not a new configuration source.

Config example:

```json
{
  "tools": {
    "mcpServers": {
      "trainingController": {
        "type": "stdio",
        "command": "uv",
        "args": [
          "--directory",
          "mlpcopilot/mcps/mlp_training_controller_mcp",
          "run",
          "mlp-training-controller-mcp"
        ],
        "toolTimeout": 600,
        "enabledTools": [
          "inspect_training_project",
          "validate_training_inputs",
          "get_training_status",
          "analyze_training_failure"
        ]
      }
    }
  }
}
```

## 17. Approval Policy

Tools that must be approved:

```text
start_training_run
stop_training_run
reset_training_run
cancel_remote_jobs
overwrite_param
overwrite_machine
delete_iteration
hard_reset_run
submit_remote_jobs
```

Tools that may run read-only:

```text
inspect_training_project
validate_training_inputs
get_training_status
list_training_iterations
inspect_training_iteration
collect_training_logs
analyze_training_failure
build_training_run_report
```

Approval requests must include:

- Action type.
- Project path.
- Command or files to modify.
- Param hash.
- Machine hash.
- Resource summary.
- Expected artifacts.
- Rollback or backup plan.

## 18. Artifact Rules

Plugin artifacts should be written into workspace:

```text
runs/<run_id>/
reports/
logs/
approvals/
```

Training controller artifacts:

```text
runs/<run_id>/training_param.json
runs/<run_id>/training_machine.json
runs/<run_id>/training_controller_state.json
runs/<run_id>/training_status.json
runs/<run_id>/training_iteration_metrics.json
runs/<run_id>/training_failure_analysis.md
runs/<run_id>/training_run_report.md
runs/<run_id>/manifest.json
logs/<run_id>/training.stdout.log
logs/<run_id>/training.stderr.log
```

Rules:

- Important artifacts must have SHA256.
- Important inputs must record hashes.
- Run manifests must record tool, version, inputs, outputs, and errors.
- Metrics in reports must cite artifacts.

## 19. Implementation Order

### Phase 1: Training Controller Read-Only

1. Create the `mlp_training_controller_mcp` package.
2. Implement MCP server skeleton.
3. Implement the common output protocol.
4. Implement `inspect_training_project`.
5. Implement `validate_training_inputs`.
6. Implement `get_training_status`.
7. Implement `list_training_iterations`.
8. Implement `inspect_training_iteration`.
9. Implement `collect_training_logs`.
10. Implement `analyze_training_failure`.

### Phase 2: Training Backend Config Generation

1. Define `system_profile.json` schema.
2. Define `strategy_config.json` schema.
3. Define `machine_profile.json` schema.
4. Implement `generate_training_param`.
5. Implement `generate_training_machine`.
6. Generate config reports.
7. Integrate `mlp-active-learning` skill.

### Phase 3: Training Execution Control

1. `start_training_run` is implemented.
2. Controller state is implemented.
3. stdout/stderr log capture is implemented.
4. `stop_training_run` is implemented.
5. `reset_training_run` soft mode is implemented.
6. `reset_training_run` hard mode is implemented.
7. Runtime approval-gated tool policy is integrated.
8. Start/stop/reset/rewind execution evidence manifests are implemented.

### Phase 4: Dataset And Model Modules

1. First-pass `mlp_dataset_mcp` is implemented.
2. First-pass `mlp-dataset-validation` skill is implemented.
3. First-pass `mlp-validation-planner` skill is implemented.
4. First-pass `mlp_model_eval_mcp` is implemented.
5. First-pass `mlp-checkpoint-evaluation` skill is implemented.
6. DeePMD-kit v3 `dp test` checkpoint benchmark entrypoint is implemented.
7. ASE-based `predict_energy_force` and `batch_predict` are implemented.
8. Checkpoint benchmark report is implemented.
9. Benchmark parity/error PNG plot artifacts are implemented.

### Phase 5: OOD Advisory Additions

Add one near-term advice capability for manuscript revision and reviewer
response:

1. Add `mlp-ood-test-advisor` skill, which suggests OOD test slices and evidence
   artifacts based on project-specific target system, deployment boundary, and
   reference budget.
2. Update related skills so the agent first collects evidence paths, identifies
   gaps, and then suggests tools or manual steps without fabricating metrics.

Keep the following in backlog unless the user explicitly needs them:

1. Full `mlp_coverage_mcp`.
2. Descriptor-based local-environment coverage analysis.
3. Fixed OOD/gap audit tools and deep dataset science checks.
4. `mlp_job_mcp`.
5. HTML/PDF output for integrated MLP training and validation reports.

Completed: lightweight `mlp_report_mcp`, checkpoint benchmark report, and
benchmark PNG plot artifacts.

## 20. Acceptance Criteria

### Training Controller Read-Only

- DP-GEN backend projects can be detected.
- `record.dpgen` can be parsed.
- Iterations can be listed.
- Current stage can be detected.
- Basic train/model_devi/fp state can be counted from `iter.*` directories.
- Common DP-GEN errors can be analyzed and output as artifacts.

### Config Generation

- Backend-native JSON can be generated from system/strategy/machine profiles.
- Generated config passes DP-GEN schema validation.
- Param/machine hashes are output.
- Config risk summary is output.

### Execution Control

- Starting a training run triggers approval first.
- Stop/reset triggers approval.
- Controller state can be restored.
- After failure, log analysis can suggest next steps.

### Runtime Boundary

- Do not modify `mlpcopilot` core scientific logic.
- Do not place training backend logic in runtime.
- MCP/Skill plugins can be upgraded independently.

## 21. Key Design Decisions

- The training-flow controller is the first plugin milestone.
- The training-flow controller wraps CLI/process/file state; it does not rewrite
  DP-GEN or other backend main loops.
- `record.dpgen` is one primary source for state readout.
- `iter.??????` directory structure is a basis for state and artifact indexing.
- Start, stop, and reset must use blocking approval workflows.
- Model-performance testing and coverage analysis do not belong in the
  training-flow controller.
- Metrics must come from MCP tool artifacts, not LLM judgment.
