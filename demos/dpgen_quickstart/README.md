# DP-GEN Quickstart Demo

This demo gives a fast, local, no-HPC preview of the MLP Copilot DP-GEN workflow.
It does not run DeepMD-kit, LAMMPS, VASP, or DP-GEN. Instead, it creates a
DP-GEN-shaped run directory, projects it into the MLP workspace state files, and
opens the TUI so the user can inspect the run as if an active-learning iteration
were advancing.

## Run

```bash
bash demos/dpgen_quickstart/run_demo.sh
```

The script uses a temporary workspace by default and copies
`~/.mlpcopilot/config.json` as the config template when it exists.

Useful variants:

```bash
bash demos/dpgen_quickstart/run_demo.sh --no-tui
MLPCOPILOT_DEMO_MODEL=qwen3.5-35b bash demos/dpgen_quickstart/run_demo.sh
MLPCOPILOT_DEMO_TMPDIR=/tmp/mlpcopilot-demo bash demos/dpgen_quickstart/run_demo.sh
```

## What it demonstrates

- Create an MLP project and run.
- Populate `backend/dpgen` with mock DP-GEN inputs and outputs.
- Project `record.dpgen` into `run_state.json`.
- Project config, training, model-deviation, label, and dataset files into artifacts.
- Feed the TUI Artifacts and Companion panes from decoupled UI state files.
- Advance `record.dpgen` from task 0 to task 8 with lightweight playback.

## Demo Scope

The fixture uses mock outputs for a runtime and UX preview. Production training,
exploration, labeling, dataset validation, and model metrics are run through the
relevant MCP servers or skills.
