# PRD: MLP Copilot TUI Codex-Style Interaction Refactor

## 1. Product Positioning

**MLP Copilot TUI** is the local primary workbench for MLP Copilot Runtime. It
supports long-running MLP training, active learning, DFT calculations, data
review, MCP tool calls, and human approvals.

This PRD extends `MLPCOPILOT_RUNTIME_PRD.md` with TUI-specific requirements. The
goal is to learn from the Codex CLI interaction model while preserving MLP
Copilot's current multi-pane workbench design.

Core decisions:

- Adopt Codex-style input, slash-command, approval, overlay, and task-control
  behavior.
- Do not copy Codex implementation code.
- Preserve the current Chat / Campaign / Tool Log / Artifacts / Approvals
  workbench layout.
- Keep the TUI architecture modular so later layouts can be swapped in.

## 2. Background

The current TUI already provides:

- Chat / Task pane.
- Campaign pane.
- Tool Log pane.
- Artifacts pane.
- Approvals pane.
- Input history.
- Slash commands such as `/approve`, `/reject`, `/changes`, `/runs`, and
  `/artifacts`.
- Approval overlay.
- Persistent tool logs.
- Initial background exec support.

The implementation still has engineering debt:

- Input, commands, approvals, rendering, and state transitions are still coupled
  in a small number of modules.
- Boundaries between local, agent, and queued slash commands are not strong
  enough.
- Some commands are queued while a task is running, instead of responding
  immediately in the Codex style.
- Approval, pager, and picker overlays do not share a common abstraction.
- Layout behavior is hard-coded in rendering, making later campaign-focused
  layouts expensive.
- Boundaries between long tasks, background jobs, Tool Log, and Chat output need
  to be tightened.

## 3. Goals

1. Reproduce the core Codex CLI interaction feel:
   - Slash-command registry.
   - Slash popup.
   - Arrow-key selection.
   - Enter confirmation.
   - Esc reject or close.
   - Immediate local commands while a task is running.
   - Strong blocking approval overlay.
   - Pager for long messages.
   - Background task management.

2. Preserve the current MLP Copilot TUI product shape:
   - Chat / Task.
   - Campaign.
   - Tool Log.
   - Artifacts.
   - Approvals.
   - Current input box and footer.

3. Refactor the TUI into an evolvable architecture:
   - Controller.
   - State.
   - Input composer.
   - Command registry.
   - Command dispatcher.
   - Overlay stack.
   - Layout spec.
   - View renderer.
   - Persistent stores.

4. Support later layouts:
   - Current four-pane layout.
   - Compact layout.
   - Campaign-focused layout.
   - Approvals-focused layout.
   - Mobile or remote snapshot layout.

5. Preserve runtime/plugin boundaries:
   - The TUI does not implement MLP scientific algorithms.
   - The TUI displays MCPs, skills, runs, artifacts, jobs, and approvals.
   - Metrics and reports still come from MCP tools or artifacts.

## 4. Non-Goals

1. Do not rewrite the TUI in Rust.
2. Do not introduce `ratatui`.
3. Do not copy Codex source code.
4. Do not implement a Web UI.
5. Do not implement active-learning, DFT, or training-scheduling algorithms in
   the TUI.
6. Do not let the TUI judge whether scientific results are reliable.
7. Do not treat Tool Log as the run manifest.
8. Do not dump long stdout into Chat.

## 5. Codex CLI Ideas To Reuse

Relevant Codex CLI design areas:

```text
slash command metadata and dispatch
approval overlays
protocol-level approval states
background task listing and stopping
pager behavior for long content
```

Ideas to absorb:

| Codex design | MLP Copilot implementation |
|---|---|
| SlashCommand enum plus metadata | Python command registry |
| `available_during_task` | Command availability while a task is running |
| `supports_inline_args` | Slash popup and input parsing |
| Slash-command history | Slash commands enter input history |
| Approval overlay | Strong blocking approval dialog |
| Esc is safe cancel/reject | Esc rejects approval or closes overlay |
| Local command dispatch | `/status`, `/runs`, and similar commands do not enter the model |
| Background process listing | `/ps`, `/stop <job_id>` |
| Pager for long content | Long content does not flood the main Chat pane |

Ideas not to absorb:

- Rust or `ratatui` component implementation.
- The full Codex product command set.
- Multi-agent product narrative.
- Cloud-account, plugin-marketplace, or IDE-specific behavior.

## 6. Target User Experience

### 6.1 Normal Input

```text
User types text
Enter -> submit to agent
Up/Down -> input history
Ctrl-T -> open latest message pager
PgUp/PgDn -> scroll Chat
Ctrl-C -> quit
```

These keys must be overridable through `tui.keymap`. Defaults keep Codex-style
`Ctrl-*` combinations, but users in Firefox, Jupyter, or browser terminals must
be able to switch to less frequently intercepted keys such as `F7/F8/F9/F10/F12`.
An empty list disables the shortcut for that action.

### 6.2 Slash Command

```text
User types /
Slash menu opens
Up/Down selects command
Enter confirms command
Esc closes menu
Inline args remain editable
Submitted slash command is added to history
```

Examples:

```text
/status
/runs
/artifacts run_20260504_xxx
/approvals
/ps
/tool-log
/raw
/stop
/stop job_123
/model
```

### 6.3 Approval

When a pending approval appears:

```text
Approval Required overlay opens
Chat input remains visible but normal submission is blocked
Left/Right selects action
Enter approves selected action
Esc rejects
F4 requests changes
```

Text commands remain available:

```text
/approve <approval_id>
/reject <approval_id>
/changes <approval_id>
```

Rationale:

- The TUI needs smooth keyboard approvals.
- Telegram, CLI, and API need text-form approvals.

### 6.4 Long Output

Long-output rules:

- Short summaries enter Chat.
- Full stdout/stderr goes to a job log or artifact.
- Chat includes the log path or artifact path.
- The configured pager shortcut, or Enter on a message, opens the pager.
- Tool Log shows summary rows only.

### 6.5 Long-Running Command

Long-running command rules:

- `!<cmd>` is TUI terminal pass-through mode. It runs directly through local
  `/bin/bash`; it does not enter the agent, runtime tool approval, or allowlist
  policy. The command blocks the TUI worker until it exits.
- Interactive or resident commands such as `cmatrix`, `htop`, `top`, and `watch`
  are backgrounded by default.
- Commands are backgrounded when the user explicitly requests `background=true`.
- Background tasks enter the jobs store.
- `/ps` lists background tasks.
- `/stop <job_id>` stops a background task.
- `/stop` stops the current foreground agent turn.

## 7. Information Architecture

Default layout keeps the current shape:

```text
┌──────────────────────────────┬──────────────────────┐
│ Chat / Task                  │ Campaign             │
│                              ├──────────────────────┤
│                              │ Tool Log             │
├──────────────────────────────┼──────────────────────┤
│ Artifacts                    │ Approvals            │
└──────────────────────────────┴──────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Input                                               │
└─────────────────────────────────────────────────────┘
Footer
```

Pane responsibilities:

| Pane | Responsibility |
|---|---|
| Chat / Task | Conversation, task summary, agent replies, necessary system messages |
| Campaign | Active-learning, training, and DFT campaign overview from external scripts or artifacts; default reads `active_learning/status.{json,md,txt}` and `campaign/status.{json,md,txt}`, configurable through `tui.campaignStatusPaths` |
| Tool Log | Recent tool-call summaries, status, duration, and target |
| Artifacts | Valuable reports, logs, manifests, and knowledge-base files in the workspace |
| Approvals | Pending approvals and recent approval history |
| Input | Input, slash command, history |
| Footer | Current state and important shortcuts |

### 7.1 Campaign Status Schema

The first `campaign/status.json` and `active_learning/status.json` read model is
implemented to support status display for long workflows such as active
learning, training, and DFT calculation.

This schema describes only state references that the runtime/TUI can display. It
does not implement active-learning or scientific algorithms in the TUI.
Suggested fields:

```json
{
  "campaign_id": "al_001",
  "state": "idle|planning|sampling|dft_running|training|validating|waiting_approval|blocked|done|failed",
  "iteration": 0,
  "dataset": {
    "path": "datasets/current",
    "artifact_id": "artifact_xxx"
  },
  "checkpoint": {
    "path": "checkpoints/model.pt",
    "artifact_id": "artifact_xxx"
  },
  "jobs": [
    {
      "job_id": "job_xxx",
      "kind": "dft|train|validate",
      "status": "running|queued|failed|done"
    }
  ],
  "next_decision": {
    "approval_id": "apr_xxx",
    "summary": "Approve DFT batch submission"
  },
  "blockers": [],
  "artifacts": []
}
```

Implemented behavior:

- Read `active_learning/status.{json,md,txt}` and `campaign/status.{json,md,txt}`
  by default.
- Allow `tui.campaignStatusPaths` to override read order; an empty list disables
  this fallback.
- Read only paths inside the workspace.
- `companion.display.json` keeps priority over status fallback.

## 8. Architecture Design

Current structure:

```text
mlpcopilot/runtime/tui/
├── app.py
├── controller.py
├── common.py
├── runtime_factory.py
├── state.py
├── commands/
├── input/
├── overlays/
├── layouts/
├── views/
└── stores/
```

`mlpcopilot.runtime.tui` is the current facade package. `__init__.py` continues
to re-export symbols that historical tests and external callers depend on. The
internal implementation is layered under `commands/`, `input/`, `overlays/`,
`layouts/`, `views/`, and `stores/`. Future refactors should keep splitting
files inside these directories instead of returning to a monolithic
`tui_parts/`.

## 9. State Model

### 9.1 AppState

```text
AppState
- session_id
- workspace
- model
- running
- active_task_id
- active_overlay
- overlays[]
- panes
- command_mode
- footer_status
```

### 9.2 PaneState

```text
ChatPaneState
- messages
- scroll
- follow_tail
- pager_target

ToolLogPaneState
- entries
- scroll
- follow_tail

ApprovalPaneState
- pending
- decisions
- selected_approval_id
- selected_action

ArtifactPaneState
- runs
- files
- selected_artifact

CampaignPaneState
- status
- source_path
- last_loaded_at
```

### 9.3 InputState

```text
InputState
- buffer
- history
- history_index
- slash_menu_open
- slash_query
- completion_items
```

## 10. Command Registry

Command definition:

```python
TuiCommand(
    name="/runs",
    description="Show recent run manifests",
    dispatch="local",
    supports_inline_args=False,
    available_during_task=True,
    add_to_history=True,
)
```

Dispatch kinds:

| Kind | Meaning | Examples |
|---|---|---|
| `local` | Execute immediately in TUI/runtime | `/status`, `/runs`, `/artifacts`, `/approvals`, `/ps` |
| `overlay` | Open a TUI overlay | `/model`, `/help`, `/layout` |
| `approval` | Modify ApprovalManager state | `/approve`, `/reject`, `/changes` |
| `agent` | Enter the agent loop | `/plan`, `/goal` |
| `session` | Affect session state | `/new`, `/history` |

Default commands:

```text
/help
/status
/profile
/model
/new
/history
/runs
/artifacts <run_id>
/approvals
/approve <id>
/reject <id>
/changes <id>
/ps
/tool-log
/raw [last|call_id]
/stop [job_id]
/layout [name]
```

## 11. Dispatch Rules

Priority order:

1. Active overlay key handling.
2. Approval shortcut handling.
3. Immediate local slash command.
4. Task-sensitive command gating.
5. Agent slash command.
6. Normal user message.

Rules:

- `/status`, `/runs`, `/artifacts`, `/approvals`, `/ps`, and `/stop` must respond
  immediately.
- Commands that modify runtime state, such as `/model` and `/new`, are disabled
  by default while a task is running.
- Unknown slash commands are not sent to the model; return `Unknown command`.
- Only ordinary natural-language messages enter the agent loop.
- When an approval overlay exists, normal input is blocked, but `/status`,
  `/approve`, `/reject`, `/changes`, and `/stop` remain usable.

## 12. Overlay System

Unified overlay interface:

```text
Overlay
- id
- title
- render(state)
- handle_key(event)
- can_close_with_esc
- blocks_input
```

Initial overlays:

| Overlay | Purpose |
|---|---|
| ApprovalOverlay | Current approval |
| MessagePager | View long messages |
| SlashMenu | Slash-command selection |
| ModelPicker | Model selection |
| LayoutPicker | Layout switching |
| JobPicker | Background task selection |

Overlay stack rules:

- Only one strongly blocking overlay may exist at a time.
- ApprovalOverlay has highest priority.
- Esc in ApprovalOverlay means reject, not silent close.
- Esc in Pager/Picker closes the overlay.

## 13. Layout System

LayoutSpec:

```text
LayoutSpec
- name
- min_width
- min_height
- render(app_state, panes, overlays)
```

Initial layouts:

| Layout | Purpose |
|---|---|
| `four_pane` | Default workbench |
| `compact` | Small terminals |
| `campaign_focus` | Active-learning and DFT long-task monitoring |
| `approval_focus` | Remote approval or batch approval |

Switching commands:

```text
/layout
/layout four_pane
/layout campaign_focus
```

The first version supports `four_pane`, `compact`, `campaign_focus`, and
`approval_focus`. `/layout <name>` writes workspace-local TUI state
(`sessions/tui-state.json`) and does not modify user config.

## 14. Tool Log

Tool Log shows summaries only, not large JSON payloads:

```text
Datetime    State   Tool    Action                         Time
05-04 18:26 OK      mcp     task=check database status...   2.1s
05-04 18:58 BG      exec    "cmatrix"                      -
05-04 19:02 Error   exec    "rm file"                      0.0s
```

States:

| State | Meaning |
|---|---|
| `OK` | Actually executed and succeeded |
| `Error` | Actually executed and failed |
| `Pending` | Waiting for approval |
| `BG` | Running in background |
| `Stopped` | Stopped |

Requirements:

- The Tool Log pane automatically follows the newest entries so new tool calls
  do not disappear outside the visible area.
- The Tool Log pane is only a recent-summary view. Full history and manual
  scrolling are handled through `/tool-log` or the configured tool-log shortcut.
- The pager supports scrolling through full history without affecting main
  layout focus or input.
- Persist to `workspace/logs/tool-log.jsonl`.

## 15. Jobs

Add a jobs store:

```text
workspace/jobs/
├── jobs.jsonl
├── exec_<id>.log
└── mcp_<id>.log
```

Job record:

```json
{
  "job_id": "job_xxx",
  "kind": "exec|mcp|agent",
  "command": "cmatrix",
  "status": "running|exited|stopped|failed",
  "pid": 1234,
  "started_at": "...",
  "ended_at": null,
  "log_path": "jobs/exec_xxx.log"
}
```

Commands:

```text
/ps
/stop <job_id>
```

## 16. Artifacts And Runs

Keep concepts separate:

| Concept | Storage | Purpose |
|---|---|---|
| Tool Log | `logs/tool-log.jsonl` | Operation audit and UI summary |
| Job Log | `jobs/*.log` | Long-task stdout/stderr |
| Run Manifest | `runs/<run_id>/manifest.json` | Scientific or tool artifact evidence |
| Artifact | reports/metrics/figures/logs | User-citable output |

`/runs` shows run manifests only.

Implemented behavior: `/runs` and `/artifacts <run_id>` show evidence summaries
including artifact type, hash, producer MCP, key metric references, lineage, and
approval decisions. They still do not expand large JSON or long reports in the
main Chat view.

`/ps` shows background jobs.

`/tool-log` can show tool audit history.

`/raw [last|call_id]` displays persisted raw tool results. By default it selects
the latest tool-log entry that has a raw result. MCP results and large-output
tool results are written to `logs/raw-tool-results/` so raw JSON does not flood
Chat.

An MCP tool call with a raw result is also registered as a completed `mcp` job
whose log path points to the same raw result file. The TUI does not
automatically turn every MCP call into a background task. True background or
stoppable MCP long tasks require async job semantics from the MCP server itself.

## 17. Approval Requirements

Approvals must include:

- Action type.
- Target.
- Argument summary.
- Risk level.
- Approval id.
- Copyable text commands.
- Keyboard hints.

Display example:

```text
Approval Required
apr_xxx [medium]
Action: MCP Tool Call
Target: mcp_agentic-file-search_agentic_explore
Args: {"task": "check database status"}

> Approve          Enter / Ctrl-Y / F2
  Reject           Esc / Ctrl-N / F3
  Request changes  F4
```

Rules:

- Approval decisions are written to `workspace/approvals/decisions.jsonl`.
- Pending approvals are written to `workspace/approvals/pending.jsonl`.
- The TUI loads them after restart.
- The approval pane shows pending approvals; when none are pending, it shows
  recent decisions.

## 18. Security And Permissions

The TUI must not bypass runtime tool policy.

Requirements:

- Exec allowlists are controlled by config.
- `!<cmd>` is the explicit terminal-mode exception. It does not use agent tool
  policy and is intended for users who actively use the TUI as a local shell.
- Read-only generalized commands must be parsed safely as shell commands.
- Shell structures such as `>`, `>>`, `<`, pipes, `;`, `&&`, `||`, `$()`, and
  backticks must be evaluated segment by segment.
- Do not allow an entire shell string just because its first token is `ls`,
  `cat`, or `echo`.
- MCP tool allowlists are controlled by config.
- File writes, deletes, and high-cost tasks require approval by default.

## 19. Streaming

The TUI should stream assistant replies.

Rules:

- Short text can be displayed incrementally.
- Markdown rendering can refresh periodically, but must not leak ANSI styling.
- Long tool results enter Chat as summaries; full content goes to pager, log, or
  artifact.
- Raw MCP JSON should not fill Chat unless the user explicitly views it with
  `/raw`.

## 20. Persistence

After restart, the TUI should restore:

- Recent chat session.
- Pending approvals.
- Recent approval decisions.
- Tool log.
- Jobs.
- Artifacts.
- Campaign status.
- Workspace-local UI preferences, such as active layout.

It does not need to restore:

- Closed overlays.
- Temporary slash-menu state.
- Unsubmitted input buffer, at least in the first version.

## 21. Testing

Tests needed:

### 21.1 Unit Tests

- Command registry metadata.
- Command-dispatch priority.
- Local slash commands do not enter the agent.
- Unknown slash commands do not enter the agent.
- Running-task command gating.
- Approval overlay key handling.
- Esc reject.
- Enter approve.
- Input history.
- Slash completion.
- Layout render smoke.

### 21.2 Integration Tests

- `/runs` displays ArtifactIndex run manifests.
- `/artifacts <run_id>` displays artifacts.
- `/ps` displays background jobs.
- `/stop <job_id>` stops background jobs.
- Pending approvals still display after TUI restart.
- Tool log still displays after TUI restart.
- Long exec does not block new input.

### 21.3 Visual Smoke

Low-priority manual validation, suitable before a release and not a current
development blocker.

- Wide terminal.
- Narrow terminal.
- VS Code terminal.
- Standard terminal.
- `--once` snapshot.

## 22. Migration Plan

### Phase 1: Command Registry

- Create `tui/commands/registry.py`.
- Move `_TUI_SLASH_COMMANDS` into the registry.
- Keep the old import facade.
- Add tests.

### Phase 2: Dispatcher

- Create `tui/commands/dispatcher.py`.
- Explicitly separate local, overlay, approval, agent, and session dispatch.
- Make `/status`, `/runs`, `/artifacts`, `/approvals`, `/ps`, and `/stop`
  immediate local commands.
- Keep unknown slash commands out of the model.

### Phase 3: Input Controller

- Create `tui/input/composer.py`.
- Normalize Enter, Esc, Up, Down, PgUp, PgDn, and pager shortcut behavior.
- Support `tui.keymap` overrides for default shortcuts and make footer, overlay,
  and help text show the resolved keys.
- Align slash popup and history behavior with Codex.

### Phase 4: Overlay Stack

- Create `tui/overlays/`.
- Move approval, pager, and picker behavior into overlays.
- Apply Esc semantics by overlay type.

### Phase 5: LayoutSpec

- Create `tui/layouts/` and `tui/views/`.
- Rename the current layout to `four_pane`.
- Let render code compose views without handling business logic.

### Phase 6: Jobs And Tool Log Polish

- Make the jobs store a first-class concept.
- Implement `/ps` and `/stop <job_id>`.
- Add the tool-log pager.
- Refresh background task status.

## 23. Acceptance Criteria

1. `/runs`, `/artifacts`, `/status`, and `/approvals` never enter the model.
2. `/status`, `/runs`, `/ps`, and `/stop` respond immediately while a task is
   running.
3. When a pending approval appears, Enter approves and Esc rejects.
4. `/approve <id>` and `/reject <id>` still work.
5. The slash menu supports arrow-key selection and Enter confirmation.
6. Up/Down input history remains stable.
7. Long output does not pollute the main Chat view.
8. Background tasks do not block TUI input.
9. Tool Log automatically shows the newest entries.
10. `/raw` can view persisted MCP or large-output tool results.
11. The TUI loads approvals, tool log, and jobs after restart.
12. The default four-pane UI remains usable.
13. New layouts can be added without changing command/input/overlay logic.

## 24. Risks

| Risk | Mitigation |
|---|---|
| Large refactor breaks the existing TUI | Move in phases and keep facades plus tests |
| `prompt_toolkit` ANSI rendering leaks again | Avoid ANSI-then-slice rendering; use Rich renderables or safe resets in key regions |
| Local and agent command boundaries blur | Registry requires an explicit dispatch kind |
| Long-task state becomes inconsistent | Persist jobs and reconcile on startup |
| Layout abstraction becomes overbuilt | Implement only `four_pane` first while reserving the interface |
| Approval UX conflicts with remote approval | Keep both overlay and slash-command paths |

## 25. Open Questions

None for the current TUI refactor slice.
