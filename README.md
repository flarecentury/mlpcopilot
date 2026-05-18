# MLP Copilot

MLP Copilot is a vertical agent runtime for machine-learning-potential work. It
originated from the general-purpose
[`HKUDS/nanobot`](https://github.com/HKUDS/nanobot) agent runtime and is now
narrowed toward local and remote scientific workflows where evidence, artifacts,
human approvals, and traceable decisions matter.

The current product focus is DeepMD-kit / DP-GEN active-learning operations:
workspace initialization, configuration checks, run-state projection, artifact
tracking, log inspection, and human-approved control actions.

## Architecture

MLP Copilot is split into two layers:

| Layer | Responsibility |
| --- | --- |
| Runtime host | Agent loop, sessions, memory, TUI, Telegram/API gateways, MCP client, workspace, approvals, artifact index |
| MCP / skill plugins | DP-GEN control, dataset validation, model evaluation, coverage analysis, reporting, domain workflows |

The runtime must stay at the host layer. Scientific algorithms, DP-GEN semantics,
benchmark execution, checkpoint inference, and dataset validation logic belong in
MCP servers or skills, not in the core runtime.

## Current Status

Implemented runtime capabilities:

- `runtimeProfile = "mlpcopilot"` config policy and defaults.
- MLP workspace initializer, defaulting to `~/.mlpcopilot/workspace`.
- Modular terminal workbench available through `mlpcopilot tui`.
- ApprovalManager with persistent approval decisions.
- ArtifactIndex and run manifest support.
- OpenAI-compatible API approval handlers.
- Shared runtime slash-command registry for the TUI and gateways.
- Runtime-level DP-GEN status projection through
  `mlpcopilot.plugins.dpgen_adapter`.

Implemented plugin capabilities:

- `mlpcopilot/mcps/mlp_training_controller_mcp`.
- DP-GEN backend provider for training-controller tools.
- Runtime-approved `run`, `stop`, and `rewind` controls when called through the
  agent.
- `mlp-active-learning` skill.
- `dpgen-machine-writer` skill with Apptainer/SIF examples and wrappers.
- Bundled `agentic-file-search` MCP package for local document search.

Planned plugin capabilities:

- Dataset validation MCP and skill.
- Model / checkpoint evaluation MCP.
- Coverage MCP.
- Job and report MCP servers.

## Quick Start

Install from the current checkout:

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

Use an explicit config and workspace:

```bash
uv run mlpcopilot tui \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace
```

Project an existing DP-GEN working directory into the TUI workspace:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

Then open the workbench:

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

## Common Commands

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

## Product And Implementation Sources

Before changing product behavior or implementation, start with:

1. [`AGENTS.md`](./AGENTS.md)
2. [`PROJECT.md`](./PROJECT.md)
3. [`prd/MLPCOPILOT_RUNTIME_PRD.md`](./prd/MLPCOPILOT_RUNTIME_PRD.md)
4. [`prd/MLPCOPILOT_MCP_SKILL_PRD.md`](./prd/MLPCOPILOT_MCP_SKILL_PRD.md)
5. [`prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`](./prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md)

Operational and implementation docs live under [`docs/`](./docs/README.md).
Documentation update and review rules live in
[`docs/MAINTENANCE.md`](./docs/MAINTENANCE.md).

## Development

Run focused checks:

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

The codebase may still contain inherited general-purpose capabilities. For MLP
Copilot work, keep changes scoped to the current PRD and preserve the
runtime/plugin boundary.

## License And Notices

MLP Copilot is released under the MIT License. See [`LICENSE`](./LICENSE).

Third-party component notices are listed in
[`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). Security guidance is in
[`SECURITY.md`](./SECURITY.md).

## Acknowledgements

MLP Copilot builds on and adapts work from the following projects and products:

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot), the MIT-licensed
  general-purpose agent runtime that provided the original runtime foundation.
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search),
  the MIT-licensed document-search project adapted as the bundled
  `agentic-file-search` MCP package.
- [OpenAI Codex](https://openai.com/codex), whose developer-workflow
  interaction design influenced MLP Copilot's TUI, command entrypoints,
  tool-call visibility, and human approval experience.
