# MCP And Skill Index

This index describes the MCP servers and skills shipped in the current source
tree. Use `mlpcopilot mlp capabilities` for the active runtime inventory because
explicit user config can override defaults.

## Runtime Rules

- MCP servers execute tools and produce artifacts.
- Skills provide workflow guidance and tool-use policy.
- Runtime approval policy applies to built-in tools and MCP tools together.
- MCP tools must not implement their own `approval_hint`, `requires_approval`,
  or `approved=true` bypass.
- Scientific data should move by path, object ID, or artifact reference.
- Metrics and readiness claims must cite tool artifacts.

## Capability Command

```bash
uv run mlpcopilot mlp capabilities --config ~/.mlpcopilot/config.json
```

This shows configured MCP servers, enabled tools, tool timeouts, and discoverable
skills after disabled-skill policy is applied.

## MCP Servers

| Server | Package | Script | Purpose |
| --- | --- | --- | --- |
| `trainingController` | `mlp_training_controller_mcp` | `mlp-training-controller-mcp` | DP-GEN active-learning inspection, config generation/review, status, logs, start/stop, rewind, scheduler job controls |
| `mlp-dataset` | `mlp_dataset_mcp` | `mlp-dataset-mcp` | Lightweight dataset inventory, schema checks, integrity checks, dataset validation reports |
| `mlp-model-eval` | `mlp_model_eval_mcp` | `mlp-model-eval-mcp` | Checkpoint inspection, DeePMD-kit test execution, prediction artifacts, benchmark reports and plots |
| `mlp-report` | `mlp_report_mcp` | `mlp-report-mcp` | Evidence report generation from existing workspace artifacts, run manifests, and approval records |
| `agentic-file-search` | `agentic-file-search-mcp` | `agentic-file-search-mcp` | Agentic local knowledge-base search through one focused MCP tool |

When `runtimeProfile = "mlpcopilot"` and `tools.mcpServers` is absent, the
profile discovers MCP packages from the source tree. If a user explicitly sets
`tools.mcpServers`, preserve that exact user list.

## Training Controller Tools

Read-only inspection:

- `inspect_training_project`
- `validate_training_inputs`
- `get_training_status`
- `list_training_iterations`
- `inspect_training_iteration`
- `collect_training_logs`
- `analyze_training_failure`
- `get_controller_state`
- `plan_training_rewind`
- `plan_training_reset`
- `list_dispatcher_jobs`
- `inspect_dispatcher_job`
- `plan_config_update`
- `plan_machine_update`
- `plan_param_update`

State-changing or artifact-writing tools:

- `validate_machine_runtime`
- `generate_training_param`
- `generate_training_machine`
- `build_training_run_report`
- `run_training_controller`
- `start_training_run`
- `stop_training_run`
- `resume_training_run`
- `apply_training_rewind`
- `reset_training_run`
- `rerun_failed_stage`
- `cancel_scheduler_jobs`
- `cancel_remote_jobs`
- `snapshot_training_state`
- `collect_iteration_evidence`
- `apply_config_update`
- `apply_machine_update`
- `apply_param_update`

Default enabled tools for `trainingController` are narrower than the full server
surface. Check `mlpcopilot mlp capabilities` before assuming a tool is active.

## Dataset MCP Tools

- `inspect_dataset`
- `validate_dataset_schema`
- `validate_dataset_integrity`
- `build_dataset_validation_report`

These are lightweight file/layout checks. They do not currently implement full
unit consistency, duplicate detection, split leakage, label outlier detection,
or coverage analysis.

## Model Evaluation MCP Tools

- `inspect_checkpoint`
- `validate_checkpoint_on_dataset`
- `run_deepmd_test`
- `predict_energy_force`
- `batch_predict`
- `compare_checkpoints`
- `build_checkpoint_metrics`
- `build_checkpoint_benchmark_report`
- `build_benchmark_plots`

Do not claim a checkpoint passed evaluation unless a tool artifact records the
metric source, checkpoint path/hash, dataset path/hash, and command context.

## Report MCP Tools

- `build_evidence_report`

This builds reports from existing evidence. It should not invent missing
metrics.

## Agentic File Search Tools

The `agentic-file-search` skill calls the configured MCP tool for local
knowledge-base exploration. Use it for user knowledge-base questions, not for
repository source search.

## MLP Skills

| Skill | Use When |
| --- | --- |
| `mlp-active-learning` | Planning or operating MLP active-learning workflows, especially DeepMD-kit/DP-GEN |
| `dpgen-machine-writer` | Writing or reviewing DP-GEN `machine.json`, wrappers, and scheduler resources |
| `mlp-dataset-validation` | Inspecting or validating MLP datasets before training/evaluation/reporting |
| `mlp-checkpoint-evaluation` | Inspecting checkpoints, running DeePMD-kit tests, comparing metrics |
| `mlp-validation-planner` | Creating a project-specific validation plan and evidence gates |
| `mlp-ood-test-advisor` | Planning project-specific OOD or dataset-gap tests |
| `agentic-file-search` | Searching the configured local knowledge base |
| `memory` | Using Dream-managed long-term memory and history safely |
| `my` | Inspecting or adjusting session runtime state when diagnosing agent limits |

Generic inherited skills may also exist. In the MLP profile, some generic skills
are disabled by default to keep the product focused.

## Which Tool Or Skill To Use

| User Goal | First Skill | Typical MCP Tools |
| --- | --- | --- |
| Inspect current DP-GEN state | `mlp-active-learning` | `get_training_status`, `list_training_iterations`, `collect_training_logs` |
| Diagnose DP-GEN failure | `mlp-active-learning` | `collect_training_logs`, `analyze_training_failure`, `inspect_dispatcher_job` |
| Rewind to an earlier DP-GEN point | `mlp-active-learning` | `snapshot_training_state`, `plan_training_rewind`, `apply_training_rewind` |
| Write or review `machine.json` | `dpgen-machine-writer` | `validate_training_inputs`, `validate_machine_runtime`, config update tools |
| Validate dataset layout | `mlp-dataset-validation` | `inspect_dataset`, `validate_dataset_integrity`, `build_dataset_validation_report` |
| Evaluate checkpoint metrics | `mlp-checkpoint-evaluation` | `inspect_checkpoint`, `run_deepmd_test`, `build_checkpoint_benchmark_report` |
| Make a validation plan | `mlp-validation-planner` | Dataset, training, model, and report tools as available |
| Produce an evidence report | `mlp-validation-planner` or report workflow | `build_evidence_report` |
