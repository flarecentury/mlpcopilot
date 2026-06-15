<h1 align="center">MLP Copilot</h1>

<p align="center">
  Vertical agent runtime for machine-learning-potential workflows
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">中文</a> |
  <a href="./README.fr.md">Français</a> |
  <a href="./README.ja.md">日本語</a>
</p>

MLP Copilot is a vertical agent runtime for machine-learning-potential training. It
originated from the general-purpose
[`HKUDS/nanobot`](https://github.com/HKUDS/nanobot) agent runtime and is now
narrowed toward local and remote scientific workflows where artifacts, human
approvals, and traceable decisions matter.

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">
    <img src="./data/videos/Video1_mlp_ai_agents.gif" alt="MLP Copilot AI agent workflow demo" width="640">
  </a>
</p>

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">Watch the full MP4 demo</a>
</p>

It also builds on lessons from our earlier
[`flarecentury/Auto-MLP`](https://github.com/flarecentury/Auto-MLP) research
framework for AI-assisted machine-learning-potential development, active
learning supervision, and aluminum nanoparticle oxidation analysis. MLP Copilot
extracts that workflow experience into a more general runtime-plus-plugin
architecture for broader MLP operations.

The current product focus is DeepMD-kit / DP-GEN active-learning operations:
workspace initialization, configuration checks, run-state projection, artifact
tracking, log inspection, and human-approved control actions.

## What It Provides

| Area | Capability |
| --- | --- |
| Runtime host | Agent loop, sessions, memory, TUI, Telegram/API gateways, MCP client, workspace, approvals, artifact index |
| MLP plugins | Initial dataset preparation, DP-GEN control, dataset validation, model evaluation, reporting, local document search |
| Traceability | Run manifests, artifact hashes, approval decisions, tool logs, status projections |
| Human control | Blocking approvals for high-cost or destructive actions |

## Simulation Data And DigAuto

The `data/` directory has been migrated from the earlier
[`flarecentury/Auto-MLP`](https://github.com/flarecentury/Auto-MLP) project.
It contains aluminum nanoparticle combustion molecular-dynamics trajectories in
[`data/MDtrajs/`](./data/MDtrajs/) and corresponding visualization videos in
[`data/videos/`](./data/videos/), covering bare-metal and core-shell systems at
multiple temperatures.

The AI agent, trained machine learning potential (MLP) models, and the
comprehensive dataset (containing ~90,000 atomic configurations with DFT
energies/forces) are all hosted on the Digital Automation for Scientific
Discovery platform (DigAuto): [https://www.digauto.org](https://www.digauto.org).

## Requirements

- Git.
- Python 3.11 or newer.
- `uv` for dependency management.

Install `uv` if needed:

```bash
python -m pip install --user uv
```

## Install From Source

Clone the repository:

```bash
git clone https://github.com/flarecentury/mlpcopilot.git
cd mlpcopilot
```

If you prefer SSH:

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

## Agentic File Search Configuration

The bundled `agentic-file-search` MCP package has its own environment file. Use
[`mlpcopilot/mcps/agentic-file-search/.env.example`](./mlpcopilot/mcps/agentic-file-search/.env.example)
as the template, or run its initializer:

```bash
cd mlpcopilot/mcps/agentic-file-search
scripts/init-skill.sh
```

Configure `FS_EXPLORER_MCP_ROOT`, `FS_EXPLORER_DB_PATH`, and the optional
OpenAI-compatible endpoint there. These settings are separate from the main
`~/.mlpcopilot/config.json`.

## First Run

Create or update the local config and default workspace:

```bash
uv run mlpcopilot onboard
```

Recommended model setup: log in to the OpenAI Codex provider and use the latest
Codex GPT model available to your account.

```bash
uv run mlpcopilot provider login openai-codex
```

After login, set the model during onboarding or switch from the TUI with
`/model openai-codex/gpt-5.3-codex`.

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

## Start With Initial Data

Use the `mlp-initial-dataset-preparation` skill to help plan an initial dataset
generation strategy before DP-GEN or active learning. It guides structure
selection, AIMD/static DFT labeling plans, conversion targets, validation
checks, and handoff paths such as DP-GEN `init_data_sys`.

Before running training or labeling jobs, configure DeepMD-kit/DP, VASP, CP2K,
and related executables for your own HPC environment. For portable and
reproducible runtime environments, Apptainer is recommended:
[`apptainer/apptainer`](https://github.com/apptainer/apptainer).

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
Copilot work, the current PRDs describe the active product scope.

## License And Acknowledgements

MLP Copilot is released under the MIT License. See [`LICENSE`](./LICENSE).
Third-party component notices are listed in
[`THIRD_PARTY_NOTICES.md`](./THIRD_PARTY_NOTICES.md). Security guidance is in
[`SECURITY.md`](./SECURITY.md).

MLP Copilot builds on and adapts work from the following projects and products:

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot), the MIT-licensed
  general-purpose agent runtime that provided the original runtime foundation.
- [`flarecentury/Auto-MLP`](https://github.com/flarecentury/Auto-MLP), the
  earlier AI-assisted MLP development framework whose active-learning and
  scientific-workflow experience informed this project direction.
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search),
  the MIT-licensed document-search project adapted as the bundled
  `agentic-file-search` MCP package.
- [OpenAI Codex](https://openai.com/codex), whose developer-workflow
  interaction design influenced MLP Copilot's TUI, command entrypoints,
  tool-call visibility, and human approval experience.
