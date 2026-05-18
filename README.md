# MLP Copilot

MLP Copilot is a vertical agent runtime for machine-learning-potential work. It
originated from the general-purpose [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot)
agent runtime and is narrowed toward local and remote scientific workflows where
evidence, artifacts, and human approvals matter.

The current product focus is DeepMD-kit / DP-GEN active-learning operation:
workspace setup, configuration review, run status projection, artifact tracking,
log inspection, and approval-gated control actions.

## Architecture

MLP Copilot is split into two layers:

| Layer | Responsibility |
| --- | --- |
| Runtime host | agent loop, session, memory, TUI, Telegram/API gateway, MCP client, workspace, approvals, artifact index |
| MCP / skill plugins | DP-GEN control, dataset validation, model evaluation, coverage analysis, reports, domain workflows |

The runtime must stay a host. Scientific algorithms, DP-GEN semantics, benchmark
execution, checkpoint inference, and dataset validation logic belong in MCP
servers or skills.

## Current Status

Implemented runtime pieces:

- `runtimeProfile = "mlpcopilot"` policy and defaults.
- MLP workspace initializer under `~/.mlpcopilot/workspace` by default.
- Modular terminal workbench via `mlpcopilot tui`.
- ApprovalManager and persisted approval decisions.
- ArtifactIndex and run manifest support.
- OpenAI-compatible API approval handlers.
- Runtime slash command registry shared by TUI and gateway.
- Runtime-only DP-GEN adapter projection through `mlpcopilot.plugins.dpgen_adapter`.

Implemented plugin pieces:

- `mlpcopilot/mcps/mlp_training_controller_mcp`
- DP-GEN backend provider for training-controller tools.
- Run/stop/rewind control tools gated by runtime approval when called through the agent.
- `mlp-active-learning` skill.
- `dpgen-machine-writer` skill with Apptainer/SIF examples and wrappers.
- `agentic-file-search` MCP package for local document search.

Planned plugin pieces:

- dataset validation MCP and skill
- model/checkpoint evaluation MCP
- coverage MCP
- job/report MCPs

## Quick Start

Install from this checkout:

```bash
uv sync --extra dev
```

Initialize the default profile and workspace:

```bash
uv run mlpcopilot onboard
```

Open the local workbench:

```bash
uv run mlpcopilot tui
```

Render a one-shot TUI snapshot:

```bash
uv run mlpcopilot tui --once
```

Use a specific config/workspace:

```bash
uv run mlpcopilot tui \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace
```

Project an existing DP-GEN work directory into the TUI workspace:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

Then open the workbench:

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

## Important Commands

Runtime commands:

```bash
uv run mlpcopilot mlp init --workspace ~/.mlpcopilot/workspace
uv run mlpcopilot mlp status
uv run mlpcopilot mlp capabilities
uv run mlpcopilot mlp approvals
uv run mlpcopilot mlp runs list
uv run mlpcopilot mlp runs show <run_id>
```

TUI entrypoints:

```bash
uv run mlpcopilot tui
uv run mlpcopilot tui --once
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir
```

OpenAI-compatible API:

```bash
uv run mlpcopilot serve
```

Gateway:

```bash
uv run mlpcopilot gateway
```

## Source Of Truth

Read these first when changing the product:

1. [`AGENTS.md`](./AGENTS.md)
2. [`PROJECT.md`](./PROJECT.md)
3. [`prd/MLPCOPILOT_RUNTIME_PRD.md`](./prd/MLPCOPILOT_RUNTIME_PRD.md)
4. [`prd/MLPCOPILOT_MCP_SKILL_PRD.md`](./prd/MLPCOPILOT_MCP_SKILL_PRD.md)
5. [`prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`](./prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md)

Operational and implementation-facing docs live under [`docs/`](./docs/README.md),
with update and review rules in [`docs/MAINTENANCE.md`](./docs/MAINTENANCE.md).

## Development

Run focused checks:

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

The codebase may contain inherited upstream capabilities. For MLP Copilot work,
keep changes scoped to the active PRD and preserve the runtime/plugin boundary.

## License And Notices

MLP Copilot is released under the MIT License. See [`LICENSE`](./LICENSE).

See [`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md) for bundled third-party
notices. Security guidance is in [`SECURITY.md`](./SECURITY.md).

## Acknowledgements

MLP Copilot builds on and adapts work from:

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot), the MIT-licensed
  general-purpose agent runtime that provided the original runtime foundation.
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search),
  the MIT-licensed document-search project adapted as the bundled
  `agentic-file-search` MCP package.
