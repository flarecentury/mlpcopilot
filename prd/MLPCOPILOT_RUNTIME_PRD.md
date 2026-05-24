# PRD: MLP Copilot Runtime

## 1. Product Positioning

**MLP Copilot Runtime** is the vertical host runtime adapted from `mlpcopilot`
for machine-learning-potential training and validation workflows.

This PRD defines only the runtime modification scope. MCP servers and skill
packs are plugin capabilities and are defined in separate PRDs.

Core decisions:

- Build a stable host for MLP workflows first.
- The host owns conversation, sessions, approvals, UI, plugin integration, and
  evidence indexing.
- Scientific computation, dataset validation, model inference, and validation
  methodology do not belong in `mlpcopilot` core.

## 2. Background

The original `mlpcopilot` is a general-purpose agent runtime with multiple
gateways, MCP integration, memory, skills, an OpenAI-compatible API, a CLI, and
many default tools. That foundation is useful for MLP training and validation,
but the default behavior is too broad:

- Too many channels increase deployment and security surface area.
- Default tools include web, spawn, notebook, and other capabilities that are
  not required for the first MLP runtime.
- Scientific workflows need approvals, artifacts, run manifests, and a TUI
  workbench.
- Plugin capability boundaries need to be explicit.

MLP Copilot Runtime is not intended to turn `mlpcopilot` into a scientific
computing platform. It narrows the runtime into a reliable vertical host.

## 3. Target Scenario

The first scenario is a **local and remote workbench for MLP checkpoint
validation and data-quality review**.

A typical user interacts with the agent through the TUI or Telegram:

1. Select a workspace.
2. Connect one or more MCP servers.
3. Load MLP project context.
4. Let the agent call MCP tools according to skill workflows.
5. Inspect tool logs, artifacts, and approvals.
6. Approve high-cost tasks, model-readiness decisions, and long-term memory
   updates.

## 4. Users

Primary users:

- Machine-learning-potential developers.
- Computational materials researchers.
- Engineering and research users running data cleaning, model evaluation, active
  learning, and validation tasks.

Secondary users:

- Remote approvers.
- Automation systems that need to call the agent through an OpenAI-compatible
  API.

## 5. Product Goals

1. Narrow `mlpcopilot` into the minimum trusted host for MLP workflows.
2. Keep Telegram as the only default remote gateway to reduce unrelated channel
   surface area.
3. Add a local TUI as the main workbench.
4. Add a general ApprovalManager for real human-in-the-loop workflows.
5. Add an ArtifactIndex for runs, manifests, reports, and decisions.
6. Keep the MCP client and explicitly support local and remote MCP plugins.
7. Keep skill discovery, while sourcing MLP skill content from plugin packages.
8. Keep the OpenAI-compatible API for external integration.

## 6. Non-Goals

1. Do not implement MLP dataset-validation algorithms.
2. Do not implement model inference, benchmarks, or job submission.
3. Do not embed validation-planning methodology in the runtime.
4. Do not place MCP server code in `mlpcopilot` core.
5. Do not hard-code skill content into the main prompt.
6. Do not keep every social channel enabled by default.
7. Do not enable unrestricted shell by default.
8. Do not build a heavy web platform as the first UI.

## 7. Module Boundaries

| Layer | Covered by this PRD | Responsibility |
|---|---|---|
| MLP Copilot runtime | Yes | Agent loop, sessions, memory, TUI, Telegram, API, approvals, artifacts, plugin registry |
| MCP server | No | Dataset validation, model inference, validation execution, report generation |
| Skill pack | No | Methodology, operating workflow, domain-decision framework |

The runtime only knows that tools, skills, artifacts, and approvals exist. It
does not understand specific scientific algorithms.

DP-GEN-related adapters, such as `mlpcopilot.plugins.dpgen_adapter`, belong to
the plugin layer. The runtime may display projected artifacts, run manifests,
and display documents from such adapters, but it must not parse `record.dpgen`,
`iter.*`, or other DP-GEN scientific or scheduling semantics in core runtime
logic.

## 8. Retained `mlpcopilot` Capabilities

Retain:

- `AgentLoop`
- `ContextBuilder`
- `SessionManager`
- `MemoryStore`
- `ToolRegistry`
- `providers`
- MCP client
- `bus`
- `config`
- Telegram channel
- OpenAI-compatible API

Continue supporting:

- `mlpcopilot serve`
- `mlpcopilot agent`
- MCP `stdio`
- MCP `sse`
- MCP `streamableHttp`
- workspace skills

## 9. Capabilities Disabled By Default

Under the `mlpcopilot` profile, disable the following by default:

- Slack, Discord, Feishu, WeChat, WeCom, WhatsApp, Matrix, Email, QQ, DingTalk,
  and MSTeams.
- WebUI / WebSocket, unless explicitly enabled in development mode.
- `web_search` and `web_fetch`.
- Unrestricted `exec`.
- Generic `spawn`.
- `notebook_edit`.
- Nonessential built-in skills.
- Cron-style non-scientific reminders.

## 10. Runtime Profile

Add:

```json
{
  "runtimeProfile": "mlpcopilot"
}
```

Behavior:

| Item | Behavior |
|---|---|
| Channels | Load only Telegram, CLI, and API by default |
| Tools | Use a minimal default tool set |
| MCP | Connect to local or remote MCP servers |
| Skills | Load only enabled workspace skills |
| Exec | Enabled only with approvals and allowlist policy |
| Web | Disabled by default |
| Workspace | Initialize the MLP Copilot schema |
| Approval | Gated actions require approval |

## 11. Workspace Schema

Default workspace:

```text
workspace/
├── AGENTS.md
├── SOUL.md
├── USER.md
├── PROJECT.md
├── TOOLS.md
├── structures/
├── datasets/
├── checkpoints/
├── configs/
├── validation_plans/
├── runs/
├── reports/
├── figures/
├── approvals/
├── jobs/
├── sessions/
├── memory/
└── skills/
```

The runtime creates directories and baseline templates only. It does not
generate scientific validation content.

`PROJECT.md` stores:

- Project name.
- Target system or application domain.
- Current workspace conventions.
- Summary or reference for known MCP/skill status.
- Approved high-level decisions.
- Path or reference for current acceptance criteria.

## 12. Tool Policy

Default tools for the `mlpcopilot` profile:

- `ask_user`
- `my`, read-only by default; it can modify runtime state only when
  `tools.my.allowSet` is explicitly enabled.
- `read_file`
- `file_info`
- `list_dir`
- `grep`
- `glob`
- `write_file`
- `edit_file`
- `message`
- `workstate`
- `mcp_*`
- `web_search` / `web_fetch`, registered only when web tools are explicitly
  enabled.
- `exec`, registered only when it is explicitly enabled and an allowlist is
  configured.

Approval policy:

- All agent-side built-in tool calls and MCP tool calls go through the runtime
  ApprovalManager.
- `tools.approvalAllowlist` uses exact tool-name matches. The `mlpcopilot`
  defaults allow read-only or status tools such as `read_file`, `list_dir`,
  `grep`, `glob`, `file_info`, `web_search`, `web_fetch`, and `workstate`.
- MCP tools annotated with standard `ToolAnnotations.readOnlyHint=true` are
  allowed by default when they do not also declare `destructiveHint=true`.
  Unannotated MCP tools, or tools that may modify files, start tasks, or cancel
  tasks, still require approval.
- `exec` keeps its own policy: exact `allowCommands` entries may run directly;
  all other commands block through the exec approval flow.
- `!cmd` is a TUI terminal mode and does not enter the agent tool approval
  policy.

Forbidden:

- Passing large datasets, trajectories, or long coordinate payloads through LLM
  context.
- Letting the LLM generate scientific metrics on its own.
- Letting plugins declare `approval_hint`, `requires_approval`, or `approved=true`
  in MCP output to bypass the runtime ApprovalManager.

## 13. MCP Integration

The runtime uses the existing `mlpcopilot` MCP client. It does not implement
scientific MCP logic in core.

Supported transports:

- `stdio`: local MCP server.
- `sse`: remote SSE MCP endpoint.
- `streamableHttp`: remote HTTP MCP endpoint.

Config example:

```json
{
  "tools": {
    "mcpServers": {
      "mlpDataset": {
        "type": "streamableHttp",
        "url": "${MLP_DATASET_MCP_URL}",
        "headers": {
          "Authorization": "Bearer ${MLP_MCP_TOKEN}"
        },
        "toolTimeout": 600,
        "enabledTools": [
          "inspect_dataset",
          "validate_dataset_integrity",
          "dataset_coverage_report"
        ]
      }
    }
  }
}
```

Runtime enhancements:

- Show MCP server connection status in the TUI.
- Show MCP server, tool, duration, and status in the tool log.
- Provide actionable errors for remote MCP failures.
- Discover MCP/skill sources from source-tree discovery and explicit config.
  The runtime may display connection state, but it must not create a separate
  workspace capability config file.

## 14. Skill Integration

The runtime does not define MLP skill content. It only loads and displays skills.

Requirements:

- Skills under workspace `skills/` can be discovered.
- `disabledSkills` can disable unrelated skills.
- The TUI can display the enabled skill list.
- `ContextBuilder` injects skill summaries under a token budget.
- Skills must not claim that they can directly generate scientific metrics.

## 15. TUI

Detailed TUI interaction and modularization requirements are defined in
`MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`. This section keeps only the runtime
PRD scope and first-version shape.

Add command:

```bash
mlpcopilot tui
```

First-version layout:

```text
┌──────────────────────────────┬──────────────────────────────┐
│ Chat / Task                  │ Tool Log                     │
├──────────────────────────────┼──────────────────────────────┤
│ Artifacts                    │ Approvals                    │
└──────────────────────────────┴──────────────────────────────┘
Status: model | workspace | MCP | skills | run_id | pending approvals | Telegram
```

Panes:

- Chat / Task: conversation, plan drafts, user input.
- Tool Log: tool calls, MCP server, argument summary, status, duration, errors.
- Artifacts: manifests, metrics, reports, figures, logs.
- Approvals: pending, approved, rejected, and needs-changes decisions.

The MVP may start with a read-only TUI plus approval operations. Advanced
artifact browsing can follow later.

## 16. Telegram

Telegram is the only default remote gateway.

Commands:

```text
/status
/runs
/artifacts <run_id>
/approvals
/approve <approval_id>
/reject <approval_id>
/changes <approval_id>
/help
```

Limitations:

- Do not show long reports in Telegram.
- Do not browse large logs in Telegram.
- Do not let unauthorized users trigger tasks.

`allowFrom` must be configured.

## 17. OpenAI-Compatible API

Retain:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
```

Requirements:

- Support `session_id`.
- Support streaming.
- Support file upload or path references.
- API sessions can trigger the same approval workflow.
- Bind to `127.0.0.1` by default.
- Require an API key or authenticated reverse proxy before public exposure.

## 18. ApprovalManager

ApprovalManager is a runtime capability, not an MCP plugin capability.

Responsibilities:

- Create approval items.
- Block gated actions.
- Receive decisions from the TUI, Telegram, CLI, and API.
- Record the decision log.
- Write approval records into run manifests.

Storage:

```text
approvals/pending.jsonl
approvals/decisions.jsonl
```

Approval states:

- `pending`
- `approved`
- `partially_approved`
- `rejected`
- `needs_changes`
- `expired`

Action types that require approval:

- Running medium- or high-cost tasks.
- Marking a checkpoint as usable for the target scenario.
- Changing project-level acceptance criteria.
- Updating confirmed facts in long-term memory.
- Deleting or overwriting existing run artifacts.
- Exporting or pushing results externally.

## 19. ArtifactIndex

ArtifactIndex is a runtime capability.

Each run has at least:

```text
runs/<run_id>/manifest.json
```

Fields:

```json
{
  "run_id": "...",
  "created_at": "...",
  "source": "mcp:<server>:<tool>",
  "inputs": [],
  "outputs": [],
  "artifacts": [],
  "approval": null,
  "errors": []
}
```

The runtime does not interpret scientific metrics. It only makes artifacts
indexable and traceable.

Implemented state: `RunManifest` / `ArtifactIndex` support `metrics`, `lineage`,
and `decisions` evidence fields for MLP workflow evidence. This remains runtime
indexing capability and does not add dataset validation, checkpoint inference,
benchmark, or active-learning algorithms to core.

Suggested extension fields:

```json
{
  "artifacts": [
    {
      "artifact_id": "artifact_xxx",
      "path": "runs/run_x/report.md",
      "type": "dataset_validation_report|metrics|figure|log|checkpoint|dataset|plan",
      "sha256": "...",
      "size_bytes": 123,
      "produced_by": "mcp:<server>:<tool>",
      "created_at": "..."
    }
  ],
  "metrics": [
    {
      "name": "force_rmse",
      "value": 0.08,
      "unit": "eV/A",
      "source_artifact": "artifact_xxx"
    }
  ],
  "lineage": {
    "inputs": [
      {
        "path": "datasets/current",
        "type": "dataset",
        "sha256": "..."
      }
    ],
    "parents": ["run_previous"]
  },
  "decisions": [
    {
      "approval_id": "apr_xxx",
      "status": "approved",
      "reason": "..."
    }
  ]
}
```

Requirements:

- Numeric conclusions must reference `metrics[*].source_artifact` or a concrete
  artifact path.
- TUI, Telegram, and API surfaces show evidence summaries only. Large files are
  viewed through artifact paths or `/raw`.
- MCP/Skill plugins generate scientific metrics and reports. The runtime records
  path, hash, type, producer, and references.

## 20. Memory Policy

Memory layers:

| Layer | File | Purpose |
|---|---|---|
| session | `sessions/*.jsonl` | Session history |
| history | `memory/history.jsonl` | Historical summaries |
| project | `PROJECT.md` | Project state |
| long-term | `memory/MEMORY.md` | Human-confirmed facts |
| artifact | `runs/*/manifest.json` | Tool evidence |

Rules:

- Do not write raw structure coordinates into long-term memory.
- Do not write one-off logs into long-term memory.
- Long-term fact updates require approval.
- Numeric conclusions should reference artifacts first.

## 21. CLI

Retain:

```bash
mlpcopilot agent
mlpcopilot serve
mlpcopilot gateway
```

Add:

```bash
mlpcopilot tui
mlpcopilot mlp init --workspace ~/.mlpcopilot/workspace
mlpcopilot mlp status
mlpcopilot mlp capabilities
mlpcopilot mlp runs list
mlpcopilot mlp runs show <run_id>
mlpcopilot mlp approvals
mlpcopilot mlp approve <approval_id>
mlpcopilot mlp reject <approval_id>
```

`mlpcopilot mlp` commands manage runtime state only. They do not execute
scientific algorithms.

## 22. Config Example

```json
{
  "runtimeProfile": "mlpcopilot",
  "agents": {
    "defaults": {
      "workspace": "~/.mlpcopilot/workspace",
      "provider": "openrouter",
      "model": "anthropic/claude-opus-4-6",
      "timezone": "Asia/Shanghai",
      "disabledSkills": ["weather", "github"],
      "maxToolIterations": 80
    }
  },
  "channels": {
    "sendProgress": true,
    "sendToolHints": true,
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}",
      "allowFrom": ["123456789"],
      "inlineKeyboards": true
    }
  },
  "tools": {
    "restrictToWorkspace": true,
    "web": {
      "enable": false
    },
    "exec": {
      "enable": false
    },
    "mcpServers": {}
  },
  "api": {
    "host": "127.0.0.1",
    "port": 8900,
    "timeout": 600
  }
}
```

## 23. MVP Scope

MVP includes:

1. `mlpcopilot` runtime profile.
2. Channel whitelist, with Telegram enabled by default.
3. Workspace initializer.
4. Minimal tool policy.
5. MCP status display.
6. Workspace skill loading and status display.
7. ApprovalManager.
8. ArtifactIndex.
9. Four-pane TUI skeleton.
10. Telegram approval.
11. CLI approval.
12. OpenAI-compatible API remains usable.

MVP does not include:

- MLP dataset validation.
- MLP model inference.
- Validation-planning skill.
- Remote job scheduler.
- Full WebUI.

## 24. Effort Estimate

| Scope | Estimate | Notes |
|---|---:|---|
| Lean runtime | 2-3 weeks | Profile, workspace, channel whitelist, approvals, artifacts, CLI |
| Runtime MVP | 3-5 weeks | TUI skeleton, Telegram approval, MCP/skill status display, API workflow |
| Robust runtime | 6-8 weeks | Fuller permissions, error recovery, TUI polish, tests, docs |

Build the lean runtime first, then connect MCP/Skill plugins.

## 25. Implementation Plan

Current state: the runtime MVP is largely implemented. The phases below remain
as implementation history and acceptance mapping; they are no longer the active
near-term queue. Real deployment smoke tests and manual TUI visual smoke tests
are low-priority release checklist items.

### Phase 1: Profile And Workspace

- Add `runtimeProfile`.
- Add the `mlpcopilot` profile.
- Add the workspace initializer.
- Add `PROJECT.md` and directory templates.
- Disable unrelated channels and tools.

### Phase 2: Plugin Host

- Keep the MCP client.
- Add MCP connection status.
- Add skill status.
- Restrict tool registration.

### Phase 3: Approval And Artifact

- Add ApprovalManager.
- Add pending/decision storage.
- Add ArtifactIndex.
- Link approval records to run manifests.

### Phase 4: TUI And Telegram

- Add `mlpcopilot tui`.
- Implement the four-pane skeleton.
- Implement the approval pane.
- Support approve/reject/changes in Telegram.

### Phase 5: API And Hardening

- Support approval workflow in the API.
- Add config validation.
- Add permission and path validation.
- Add baseline tests.

## 26. Acceptance Criteria

1. The runtime can start with `runtimeProfile=mlpcopilot`.
2. Only Telegram, CLI, and API are loaded by default.
3. Web, exec, spawn, and notebook are disabled by default.
4. The MLP workspace can be initialized.
5. The runtime can connect to local or remote MCP servers.
6. Enabled MCP tools and skills can be displayed.
7. A gated action creates an approval.
8. An unapproved gated action does not execute.
9. Approvals can be handled through TUI, Telegram, and CLI.
10. Run manifests can record tool source, inputs, outputs, artifacts, and
    approval.
11. The OpenAI-compatible API remains usable.
12. Runtime core does not contain MLP dataset-validation or model-inference
    algorithms.

## 27. Risks

| Risk | Mitigation |
|---|---|
| Core keeps expanding | Strictly keep scientific algorithms out of runtime |
| TUI slows down the first version | Start with a skeleton and defer advanced artifact browsing |
| Approval becomes performative | Gated actions without approvals must be blocked |
| Remote MCP security risk | Require tokens, headers, workspace-scoped references, and timeouts |
| Skill injection pollutes context | Limit skill summaries with a token budget |
