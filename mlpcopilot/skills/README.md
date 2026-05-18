# mlpcopilot Skills

This directory contains built-in skills that extend mlpcopilot's capabilities.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:
- YAML frontmatter (name, description, metadata)
- Markdown instructions for the agent

When skills reference large local documentation or logs, prefer mlpcopilot's built-in
`grep` / `glob` tools to narrow the search space before loading full files.
Use `grep(output_mode="count")` / `files_with_matches` for broad searches first,
use `head_limit` / `offset` to page through large result sets,
and `glob(entry_type="dirs")` when discovering directory structure matters.

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.
The skill format and metadata structure follow OpenClaw's conventions to maintain compatibility.

## Available Skills

| Skill | Description |
|-------|-------------|
| `agentic-file-search` | Search and summarize configured local knowledge-base files through the Agentic File Search MCP |
| `dpgen-machine-writer` | Write and review DP-GEN `machine.json` files, especially with Apptainer/Singularity wrappers |
| `github` | Interact with GitHub using the `gh` CLI |
| `mlp-active-learning` | Plan, configure, validate, monitor, and diagnose MLP active-learning runs |
| `mlp-checkpoint-evaluation` | Inspect checkpoints and use existing metrics artifacts for criteria checks and comparisons |
| `mlp-dataset-validation` | Inspect and validate MLP datasets through dataset MCP evidence |
| `mlp-validation-planner` | Build project-specific MLP validation plans from evidence, criteria, and compute budget |
| `summarize` | Summarize URLs, files, and YouTube videos |
| `tmux` | Remote-control tmux sessions |
| `clawhub` | Search and install skills from ClawHub registry |
| `skill-creator` | Create new skills |
