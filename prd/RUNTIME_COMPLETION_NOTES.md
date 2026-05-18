# MLP Copilot Runtime MVP Completion Notes

Date: 2026-05-08

This note records the current runtime MVP completion state against:

- `prd/MLPCOPILOT_RUNTIME_PRD.md`
- `prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`
- Runtime-facing parts of `prd/MLPCOPILOT_MCP_SKILL_PRD.md`

It is a status snapshot, not a replacement for the PRDs.

## Runtime MVP Status

Runtime MVP is functionally complete for the current product slice.

Completed runtime capabilities:

- `runtimeProfile = "mlpcopilot"` profile defaults and validation.
- MLP workspace schema initialization.
- Minimal builtin tool policy and exact tool approval allowlist.
- ApprovalManager pending/decision lifecycle.
- TUI approval workflow.
- Telegram approval workflow.
- CLI approval workflow.
- OpenAI-compatible API approval workflow.
- ArtifactIndex and run manifest evidence fields.
- MCP source discovery and config-driven registration.
- MCP status display in TUI.
- `stdio`, `sse`, and `streamableHttp` MCP transport coverage.
- Real local `streamableHttp` MCP server e2e coverage.
- Workspace skill discovery and disabled skill policy.
- TUI four-pane, compact, campaign-focused, and approval-focused layouts.
- TUI slash command dispatch, approval gating, jobs, raw tool result, and tool log persistence.
- `!cmd` terminal passthrough behavior.
- Dream long-term memory approval gate.
- Public API bind safety: `api.apiKey` or `api.trustProxyAuth=true`.
- Telegram enabled safety: `channels.telegram.allowFrom` required.

## Runtime PRD Acceptance Mapping

| Acceptance item | Status | Evidence |
|---|---|---|
| `runtimeProfile=mlpcopilot` starts | Complete | `tests/config/test_mlp_profile.py` |
| Default channel/tool narrowing | Complete | `tests/channels/test_mlp_profile_channels.py`, `tests/agent/test_mlp_profile_tools.py` |
| Web/exec/spawn/notebook default off | Complete | `tests/config/test_mlp_profile.py`, `tests/agent/test_mlp_profile_tools.py` |
| MLP workspace initialization | Complete | `tests/runtime/test_mlp_workspace.py` |
| Local/remote MCP support | Complete for client coverage | `tests/tools/test_mcp_tool.py`, `tests/agent/test_mcp_connection.py` |
| MCP tools and skills display | Complete | `tests/runtime/tui/test_tool_log.py`, TUI layout tests |
| Gated action creates approval | Complete | `tests/runtime/test_approval_artifact.py` |
| Unapproved gated action blocked | Complete | `tests/runtime/test_approval_artifact.py`, tool policy tests |
| Approval through TUI/Telegram/CLI/API | Complete | `tests/runtime/tui/test_approval_rendering.py`, `tests/channels/test_telegram_channel.py`, `tests/cli/test_commands.py`, `tests/test_api_approvals.py` |
| Run manifest records source/artifacts/approval | Complete | `tests/runtime/test_approval_artifact.py`, TUI run/artifact command tests |
| OpenAI-compatible API remains usable | Complete | `tests/test_openai_api.py`, `tests/test_api_stream.py`, `tests/test_api_attachment.py` |
| Runtime core contains no MLP scientific algorithms | Complete by boundary | Scientific logic remains under `mlpcopilot/mcps/` and `mlpcopilot/skills/` |

## TUI PRD Status

Completed TUI requirements:

- Slash command registry and dispatch metadata.
- Local slash commands do not enter the model.
- Unknown slash commands do not enter the model.
- Approval overlay and text commands both work.
- Running-task immediate commands are supported.
- `/status`, `/runs`, `/artifacts`, `/approvals`, `/ps`, `/stop`, `/tool-log`, `/raw`, `/layout`, `/model`, `/goal`, and `/plan` are covered by tests or command runtime paths.
- Tool Log pane shows latest entries and persists to `workspace/logs/tool-log.jsonl`.
- Raw MCP/large tool results persist under `workspace/logs/raw-tool-results/`.
- Jobs store persists under `workspace/jobs/`.
- Startup and snapshot rendering reconcile stale persisted job records.
- TUI reloads approvals, tool logs, jobs, artifacts, and workspace-local layout state.
- `mlpcopilot tui --once` snapshot path is covered.
- TUI code is split into `runtime/tui/{commands,input,overlays,layouts,views,stores}` with `runtime.tui` kept as the public facade package.

Low-priority manual TUI validation:

- Manual visual smoke across real terminals:
  - wide terminal
  - narrow terminal
  - VS Code terminal
  - ordinary terminal
- Snapshot smoke script exists at `scripts/tui_visual_smoke.sh`; real interactive checks remain manual.
- These checks are useful before a tagged release, but they are not active development blockers.

## Security Policy Status

Completed:

- Public API bind requires either `api.apiKey` or `api.trustProxyAuth=true`.
- `api.apiKey` protects `/v1/*` routes.
- `/health` remains unauthenticated for local health checks.
- CLI `serve --host 0.0.0.0` cannot bypass public bind safety.
- Telegram enabled profile requires `allowFrom`.
- Agent-side builtin and MCP tool calls are gated by runtime ApprovalManager unless exactly allowlisted.
- `exec` keeps its own exact command allowlist and approval flow.
- TUI `!cmd` is explicitly a terminal passthrough exception and does not enter agent tool approval policy.
- MCP plugins must not use `approval_hint`, `requires_approval`, or `approved=true` to bypass runtime approval.

Low-priority deployment validation:

- Run one real deployment smoke with `api.apiKey`.
- Run one real deployment smoke with trusted reverse proxy auth and `api.trustProxyAuth=true`.
- These are release/deployment checklist items, not immediate PRD implementation work.

## Runtime Verification Commands

Representative commands used during runtime hardening:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy uv run pytest \
  tests/config/test_mlp_profile.py \
  tests/test_openai_api.py \
  tests/test_api_approvals.py \
  tests/tools/test_mcp_tool.py \
  tests/agent/test_mcp_connection.py \
  tests/channels/test_mlp_profile_channels.py \
  tests/channels/test_telegram_channel.py \
  tests/runtime/tui/test_tool_log.py \
  tests/runtime/tui/test_approval_rendering.py
```

Latest focused runtime regression result:

```text
208 passed, 14 skipped
remote MCP e2e: 1 passed with local loopback permissions
ruff: All checks passed
```

The skipped tests are environment-dependent API/socket tests from the existing suite.

## Explicitly Out Of Runtime MVP

These belong to MCP/Skill plugin work, not runtime core:

- `mlp_coverage_mcp`
- `mlp_job_mcp`
- Heavy dataset checks:
  - unit consistency
  - structure sanity
  - duplicate detection
  - split leakage
  - label consistency
  - label outliers
  - coverage analysis
- HTML/PDF report rendering beyond current Markdown evidence reports and PNG benchmark plots.
- Full remote HPC scheduler integration.
- Scientific validation methodology beyond skill guidance.

## OOD Advisory Plugin Direction

The near-term plugin direction is narrowed to advisory OOD planning rather than
a fixed chemistry-agnostic validation workflow:

1. Add and maintain an `mlp-ood-test-advisor` skill that helps users choose
   project-specific OOD validation slices, evidence artifacts, and approval gates.
2. Keep dataset/model/report MCP tools evidence-based; do not hard-code a
   universal OOD checklist into runtime or MCP core.

If a later project needs a concrete OOD/gap audit artifact, it should be scoped
from that chemistry, target use case, available reference data, and compute
budget.

## Deferred Plugin Backlog

The following items are intentionally lowered in priority as of 2026-05-09. They should not drive near-term work unless the user explicitly asks to restart them:

1. `mlp_coverage_mcp`.
2. Dataset MCP heavy checks and fixed OOD/gap audit workflows.
3. `mlp_job_mcp` for remote scheduler monitoring and cancellation.
4. `mlp_report_mcp` HTML/PDF rendering.

Near-term plugin work should focus on hardening existing training controller,
dataset, model-eval, report MCP, skills, and the OOD advisory skill.
