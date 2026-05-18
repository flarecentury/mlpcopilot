# CLI Reference

## Main Entrypoints

| Command | Description |
| --- | --- |
| `mlpcopilot onboard` | Initialize the default config and workspace |
| `mlpcopilot onboard --wizard` | Launch the interactive onboarding wizard |
| `mlpcopilot onboard -c <config> -w <workspace>` | Initialize or refresh a specific config/workspace |
| `mlpcopilot agent` | Start local interactive chat |
| `mlpcopilot agent -m "..."` | Run one chat prompt |
| `mlpcopilot tui` | Open the terminal workbench |
| `mlpcopilot tui --once` | Render one read-only workbench snapshot |
| `mlpcopilot serve` | Start the OpenAI-compatible API |
| `mlpcopilot gateway` | Start enabled chat gateways |
| `mlpcopilot status` | Show runtime status |

## MLP Runtime Commands

| Command | Description |
| --- | --- |
| `mlpcopilot mlp init --workspace <path>` | Initialize or repair an MLP Copilot workspace/profile |
| `mlpcopilot mlp status` | Show workspace, profile, MCP, skill, approval, and run status |
| `mlpcopilot mlp capabilities` | Show configured MCP servers and discoverable skills |
| `mlpcopilot mlp approvals` | List pending approval requests |
| `mlpcopilot mlp approve <approval_id>` | Approve a pending request |
| `mlpcopilot mlp reject <approval_id>` | Reject a pending request |
| `mlpcopilot mlp changes <approval_id>` | Request changes for a pending request |
| `mlpcopilot mlp projects create <name>` | Create a project-scoped MLP workspace skeleton |
| `mlpcopilot mlp projects list` | List project-scoped MLP workspaces |
| `mlpcopilot mlp projects show <project_id>` | Show a project and its project-scoped runs |
| `mlpcopilot mlp runs create <project_id>` | Create a project-scoped run skeleton |
| `mlpcopilot mlp runs list` | List run manifests |
| `mlpcopilot mlp runs show <run_id>` | Show one run manifest |
| `mlpcopilot mlp runs sync-dpgen <project_id> <run_id>` | Project an existing run's `backend/dpgen` workdir into run state and UI read models |
| `mlpcopilot mlp artifacts inspect <project_id> <run_id> <artifact>` | Inspect one project-scoped artifact record |
| `mlpcopilot mlp artifacts lineage <project_id> <run_id> <artifact>` | Show artifact parents and children |
| `mlpcopilot mlp artifacts attach <project_id> <run_id> <artifact>` | Build a compact artifact context block |

For attaching a local DP-GEN directory by path, use `bash run_tui.sh --dpgen-dir
<path>` or manually place/symlink the DP-GEN workdir at
`~/.mlpcopilot/workspace/projects/<project_id>/runs/<run_id>/backend/dpgen`
before running `mlpcopilot mlp runs sync-dpgen <project_id> <run_id>`.

## Provider And Channel Commands

| Command | Description |
| --- | --- |
| `mlpcopilot provider status` | Show provider status |
| `mlpcopilot provider login openai-codex` | OAuth login for OpenAI Codex provider |
| `mlpcopilot provider login github-copilot` | OAuth login for GitHub Copilot provider |
| `mlpcopilot channels status` | Show channel status |
| `mlpcopilot channels login <channel>` | Authenticate a channel interactively |

## TUI Slash Commands

| Command | Description |
| --- | --- |
| `/help` | Show available commands |
| `/status` | Show runtime status |
| `/new` | Start a new conversation |
| `/stop` | Stop the current task or selected job |
| `/restart` | Restart the bot process |
| `/model [model]` | Show or switch the active model |
| `/history [n]` | Show recent conversation messages |
| `/dream` | Run Dream memory consolidation |
| `/dream-log [sha]` | Show Dream memory changes |
| `/dream-restore [sha]` | Restore a Dream memory version |
| `/approvals [decisions]` | Show approval requests or decisions |
| `/approve <id> [reason]` | Approve a pending decision |
| `/reject <id> [reason]` | Reject a pending decision |
| `/changes <id> [reason]` | Request changes for a pending decision |
| `/runs` | Show recent run manifests |
| `/artifacts <run_id>` | Show artifact references for a run |
| `/jobs` or `/ps` | Show recent runtime jobs |
| `/tool-log` | Show recent tool log entries |
| `/raw <selector>` | Show a persisted raw tool result |
| `/layout [name]` | Show or switch TUI layout |
| `/profile` | Show active runtime profile |
| `/goal [text|clear]` | Show or set current goal |
| `/plan [verb] [text|n]` | Show or update current plan |

TUI also accepts blocking local shell commands with a leading bang, for example
`!ls`. This is explicit terminal mode: it runs through local `/bin/bash`, blocks
the TUI worker until exit, and does not use agent tool approval or exec allowlists.

Interactive mode exits with `exit`, `quit`, `/exit`, `/quit`, `:q`, or `Ctrl+D`.
