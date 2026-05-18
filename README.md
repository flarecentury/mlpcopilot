<p align="center">
  <strong>MLP Copilot</strong><br>
  Evidence-oriented agent runtime for machine-learning-potential workflows
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">中文</a> |
  <a href="./README.fr.md">Français</a> |
  <a href="./README.ja.md">日本語</a>
</p>

# MLP Copilot

MLP Copilot is a vertical agent runtime for machine-learning-potential work. It
originated from the general-purpose
[`HKUDS/nanobot`](https://github.com/HKUDS/nanobot) agent runtime and is now
narrowed toward local and remote scientific workflows where evidence, artifacts,
human approvals, and traceable decisions matter.

The current product focus is DeepMD-kit / DP-GEN active-learning operations:
workspace initialization, configuration checks, run-state projection, artifact
tracking, log inspection, and human-approved control actions.

## What It Provides

| Area | Capability |
| --- | --- |
| Runtime host | Agent loop, sessions, memory, TUI, Telegram/API gateways, MCP client, workspace, approvals, artifact index |
| MLP plugins | DP-GEN control, dataset validation, model evaluation, reporting, local document search |
| Evidence model | Run manifests, artifact hashes, approval decisions, tool logs, status projections |
| Human control | Blocking approvals for high-cost or destructive actions |

The runtime must stay at the host layer. Scientific algorithms, DP-GEN
semantics, checkpoint inference, benchmark execution, and dataset-validation
logic belong in MCP servers or skills, not in core runtime code.

## Requirements

- Git with access to the private repository.
- SSH key added to GitHub for the `flarecentury/mlpcopilot` repository.
- Python 3.11 or newer.
- `uv` for dependency management.

Install `uv` if needed:

```bash
python -m pip install --user uv
```

Check GitHub SSH access:

```bash
ssh -T git@github.com
```

## Install From Source

Clone the private repository:

```bash
git clone git@github.com:flarecentury/mlpcopilot.git
cd mlpcopilot
```

Install runtime and development dependencies:

```bash
uv sync --extra dev
```

Verify the CLI:

```bash
uv run mlpcopilot --help
uv run mlpcopilot mlp capabilities
```

## First Run

Create or update the local config and default workspace:

```bash
uv run mlpcopilot onboard
```

The default workspace is:

```text
~/.mlpcopilot/workspace
```

You can also initialize a workspace directly:

```bash
uv run mlpcopilot mlp init --workspace ~/.mlpcopilot/workspace
```

Open the local terminal workbench:

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

## Work With An Existing DP-GEN Directory

Project an existing DP-GEN working directory into the MLP Copilot workspace:

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

Then open the workbench:

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

## Common Commands

Runtime status and workspace commands:

```bash
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

Telegram gateway:

```bash
uv run mlpcopilot gateway
```

Update an existing checkout:

```bash
git pull --ff-only
uv sync --extra dev
```

## Project Documents

Before changing product behavior or implementation, start with:

1. [`AGENTS.md`](./AGENTS.md)
2. [`PROJECT.md`](./PROJECT.md)
3. [`prd/MLPCOPILOT_RUNTIME_PRD.md`](./prd/MLPCOPILOT_RUNTIME_PRD.md)
4. [`prd/MLPCOPILOT_MCP_SKILL_PRD.md`](./prd/MLPCOPILOT_MCP_SKILL_PRD.md)
5. [`prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`](./prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md)

Operational and implementation docs live under [`docs/`](./docs/README.md).
Documentation update and review rules live in
[`docs/MAINTENANCE.md`](./docs/MAINTENANCE.md).

## Development Checks

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

The codebase may still contain inherited general-purpose capabilities. For MLP
Copilot work, keep changes scoped to the current PRD and preserve the
runtime/plugin boundary.

## License And Acknowledgements

MLP Copilot is released under the MIT License. See [`LICENSE`](./LICENSE).
Third-party component notices are listed in
[`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). Security guidance is in
[`SECURITY.md`](./SECURITY.md).

MLP Copilot builds on and adapts work from the following projects and products:

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot), the MIT-licensed
  general-purpose agent runtime that provided the original runtime foundation.
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search),
  the MIT-licensed document-search project adapted as the bundled
  `agentic-file-search` MCP package.
- [OpenAI Codex](https://openai.com/codex), whose developer-workflow
  interaction design influenced MLP Copilot's TUI, command entrypoints,
  tool-call visibility, and human approval experience.
