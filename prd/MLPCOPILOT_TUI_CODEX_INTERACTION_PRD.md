# PRD: MLP Copilot TUI Codex-Style Interaction Refactor

## 1. 产品定位

**MLP Copilot TUI** 是 MLP Copilot Runtime 的本地主工作台，面向长时间 MLP 训练、主动学习、DFT 计算、数据审查、MCP 工具调用和人工审批。

本 PRD 是 `MLPCOPILOT_RUNTIME_PRD.md` 的 TUI 细化补充，目标是借鉴 Codex CLI 的交互模型，同时保留 MLP Copilot 当前的四窗格工作台设计。

核心判断：

- 借鉴 Codex CLI 的输入、slash command、审批、overlay、任务控制体验。
- 不复制 Codex 的 Rust/ratatui 代码。
- 保留 MLP Copilot 当前的 Chat / Campaign / Tool Log / Artifacts / Approvals 工作台布局。
- TUI 架构必须模块化，后续可以切换不同 layout。

## 2. 背景

当前 TUI 已具备以下能力：

- Chat / Task pane。
- Campaign pane。
- Tool Log pane。
- Artifacts pane。
- Approvals pane。
- 输入框历史。
- `/approve`、`/reject`、`/changes`、`/runs`、`/artifacts` 等 slash command。
- 审批 overlay。
- 工具日志持久化。
- 后台 exec 初步支持。

但当前实现仍有明显工程债：

- 输入、命令、审批、渲染、状态机仍耦合在少数模块中。
- slash command 的 local / agent / queued 边界不够强。
- 运行中命令有时会被排队，不能像 Codex 一样即时响应。
- approval、pager、picker 等 overlay 没有统一抽象。
- layout 写死在渲染层，后续切换 Campaign-focused layout 成本较高。
- 长任务、后台任务、Tool Log、Chat 输出之间的边界仍需收敛。

## 3. 目标

1. 复刻 Codex CLI 的核心交互体验：
   - slash command 注册表。
   - slash popup。
   - 方向键选择。
   - Enter 确认。
   - Esc 拒绝或关闭。
   - 运行中 local command 即时执行。
   - approval overlay 强阻塞。
   - pager 查看长消息。
   - 后台任务管理。

2. 保留 MLP Copilot 当前 TUI 产品形态：
   - Chat / Task。
   - Campaign。
   - Tool Log。
   - Artifacts。
   - Approvals。
   - 当前输入框和 footer。

3. 将 TUI 重构为可演化架构：
   - Controller。
   - State。
   - Input composer。
   - Command registry。
   - Command dispatcher。
   - Overlay stack。
   - Layout spec。
   - View renderer。
   - Persistent stores。

4. 支持后续不同 layout：
   - 当前四窗格 layout。
   - compact layout。
   - campaign-focused layout。
   - approvals-focused layout。
   - mobile/remote snapshot layout。

5. 保持 runtime / plugin 边界：
   - TUI 不实现 MLP 科学算法。
   - TUI 只展示 MCP、skills、runs、artifacts、jobs、approvals。
   - 指标和报告仍来自 MCP 或 artifact。

## 4. 非目标

1. 不重写为 Rust。
2. 不引入 ratatui。
3. 不复制 Codex 源码。
4. 不实现 Web UI。
5. 不把主动学习、DFT、训练调度算法写入 TUI。
6. 不让 TUI 直接判断科学结果是否可靠。
7. 不把 Tool Log 当作 run manifest。
8. 不把长 stdout 直接塞满 Chat。

## 5. Codex CLI 可借鉴点

参考源码：

```text
/home/flare/TRAE_PJS/other/codex/codex-rs/tui/src/slash_command.rs
/home/flare/TRAE_PJS/other/codex/codex-rs/tui/src/chatwidget/slash_dispatch.rs
/home/flare/TRAE_PJS/other/codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs
/home/flare/TRAE_PJS/other/codex/codex-rs/protocol/src/approvals.rs
```

借鉴内容：

| Codex 设计 | MLP Copilot 吸收方式 |
|---|---|
| SlashCommand enum + metadata | Python command registry |
| available_during_task | 命令运行中可用性控制 |
| supports_inline_args | slash popup 和输入解析 |
| slash command history | slash 命令进入输入历史 |
| approval overlay | 强阻塞审批弹窗 |
| Esc is safe cancel/reject | Esc 拒绝审批或关闭 overlay |
| local command dispatch | `/status`、`/runs` 等不进模型 |
| background process listing | `/ps`、`/stop <job_id>` |
| pager for long content | 长消息不塞爆主 Chat pane |

不借鉴内容：

- Rust/ratatui 组件实现。
- Codex 产品命令全集。
- Codex 多 agent 叙事。
- Codex 云端账号、plugin marketplace、IDE 专有行为。

## 6. 目标用户体验

### 6.1 常规输入

```text
User types text
Enter -> submit to agent
Up/Down -> input history
Ctrl-T -> open latest message pager
PgUp/PgDn -> scroll Chat
Ctrl-C -> quit
```

这些快捷键必须可通过 `tui.keymap` 覆盖。默认值保留 Codex 风格的 `Ctrl-*` 组合键，但在 Firefox/Jupyter/浏览器终端中，用户应可切换为 `F7/F8/F9/F10/F12` 等不容易被宿主截获的按键。空列表表示禁用该动作快捷键。

### 6.2 Slash command

```text
User types /
Slash menu opens
Up/Down selects command
Enter confirms command
Esc closes menu
Inline args remain editable
Submitted slash command is added to history
```

示例：

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

当出现 pending approval：

```text
Approval Required overlay opens
Chat input remains visible but normal submission is blocked
Left/Right selects action
Enter approves selected action
Esc rejects
F4 requests changes
```

同时保留文本命令：

```text
/approve <approval_id>
/reject <approval_id>
/changes <approval_id>
```

理由：

- TUI 需要键盘丝滑审批。
- Telegram / CLI / API 需要文本式审批。

### 6.4 Long output

长输出处理规则：

- 短摘要进入 Chat。
- 完整 stdout/stderr 进入 job log 或 artifact。
- Chat 中提供 log path 或 artifact path。
- 配置的 pager shortcut 或 Enter on message 打开 pager。
- Tool Log 只显示摘要行。

### 6.5 Long-running command

长任务处理规则：

- `!<cmd>` 是 TUI 终端直通模式：直接交给本地 `/bin/bash` 执行，不进入 agent、不走 runtime tool approval、也不做 allowlist 限制；命令会阻塞 TUI worker 直到退出。
- `cmatrix`、`htop`、`top`、`watch` 等交互/常驻命令默认后台化。
- 用户显式 `background=true` 时后台化。
- 后台任务进入 jobs store。
- `/ps` 展示后台任务。
- `/stop <job_id>` 停止后台任务。
- `/stop` 停止当前前台 agent turn。

## 7. 信息架构

默认 layout 保持当前形态：

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

Pane 职责：

| Pane | 职责 |
|---|---|
| Chat / Task | 对话、任务摘要、agent 回复、必要的系统消息 |
| Campaign | 主动学习/训练/DFT campaign 总览，由外部脚本或 artifact 提供数据；默认读 `active_learning/status.{json,md,txt}` 和 `campaign/status.{json,md,txt}`，可通过 `tui.campaignStatusPaths` 配置 |
| Tool Log | 最近工具调用摘要、状态、耗时、目标 |
| Artifacts | workspace 中有价值的报告、日志、manifest、知识库文件 |
| Approvals | pending approval 和最近审批历史 |
| Input | 输入、slash command、历史 |
| Footer | 当前状态和关键快捷键 |

### 7.1 Campaign Status Schema

已实现首版 `campaign/status.json` 和 `active_learning/status.json` 读模型，用于支撑主动学习、训练、DFT 计算等长流程的状态展示。

该 schema 只描述 runtime/TUI 可展示的状态引用，不在 TUI 中实现主动学习或科学算法。建议字段包括：

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

落地行为：

- 默认读取 `active_learning/status.{json,md,txt}` 和 `campaign/status.{json,md,txt}`。
- 可通过 `tui.campaignStatusPaths` 配置覆盖读取顺序；空列表表示禁用该 fallback。
- 只读取 workspace 内路径。
- `companion.display.json` 仍然优先于 status fallback。

## 8. 架构设计

当前落地结构：

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

`mlpcopilot.runtime.tui` 是当前 facade package：`__init__.py` 继续 re-export
历史测试和外部调用依赖的符号，内部实现按 commands/input/overlays/layouts/views/stores
分层。后续重构应优先在这些目录内继续拆小文件，而不是恢复单体 `tui_parts/`。

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

命令定义：

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

dispatch 类型：

| 类型 | 含义 | 示例 |
|---|---|---|
| `local` | TUI/Runtime 本地立即执行 | `/status`, `/runs`, `/artifacts`, `/approvals`, `/ps` |
| `overlay` | 打开 TUI overlay | `/model`, `/help`, `/layout` |
| `approval` | 修改 ApprovalManager | `/approve`, `/reject`, `/changes` |
| `agent` | 进入 agent loop | `/plan`, `/goal` |
| `session` | 影响会话 | `/new`, `/history` |

默认命令：

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

优先级从高到低：

1. Active overlay key handling。
2. Approval shortcut handling。
3. Immediate local slash command。
4. Task-sensitive command gating。
5. Agent slash command。
6. Normal user message。

规则：

- `/status`、`/runs`、`/artifacts`、`/approvals`、`/ps`、`/stop` 必须即时响应。
- `/model`、`/new` 等会修改运行时状态的命令，任务运行中默认禁用。
- 未识别 slash command 不发送给模型，返回 `Unknown command`。
- 普通自然语言才进入 agent loop。
- approval overlay 存在时，普通输入被阻塞，但 `/status`、`/approve`、`/reject`、`/changes`、`/stop` 可用。

## 12. Overlay System

统一 overlay interface：

```text
Overlay
- id
- title
- render(state)
- handle_key(event)
- can_close_with_esc
- blocks_input
```

首批 overlay：

| Overlay | 用途 |
|---|---|
| ApprovalOverlay | 当前审批 |
| MessagePager | 查看长消息 |
| SlashMenu | slash command 选择 |
| ModelPicker | 模型选择 |
| LayoutPicker | layout 切换 |
| JobPicker | 后台任务选择 |

Overlay stack 规则：

- 同一时间只允许一个强阻塞 overlay。
- ApprovalOverlay 优先级最高。
- Esc 在 ApprovalOverlay 中等价于 reject，不是 silent close。
- Esc 在 Pager/Picker 中关闭 overlay。

## 13. Layout System

LayoutSpec：

```text
LayoutSpec
- name
- min_width
- min_height
- render(app_state, panes, overlays)
```

首批 layout：

| Layout | 用途 |
|---|---|
| `four_pane` | 默认工作台 |
| `compact` | 小终端 |
| `campaign_focus` | 主动学习/DFT 长任务监控 |
| `approval_focus` | 远程审批或批量审批 |

切换命令：

```text
/layout
/layout four_pane
/layout campaign_focus
```

首版支持 `four_pane`、`compact`、`campaign_focus`、`approval_focus`。`/layout <name>` 写入 workspace-local TUI state（`sessions/tui-state.json`），不修改用户 config。

## 14. Tool Log

Tool Log 只显示摘要，不显示大块 JSON：

```text
Datetime    State   Tool    Action                         Time
05-04 18:26 OK      mcp     task=检查数据库状态...          2.1s
05-04 18:58 BG      exec    "cmatrix"                      -
05-04 19:02 Error   exec    "rm file"                      0.0s
```

状态：

| State | 含义 |
|---|---|
| `OK` | 已真实执行并成功 |
| `Error` | 已真实执行并失败 |
| `Pending` | 等待审批 |
| `BG` | 后台运行 |
| `Stopped` | 被停止 |

要求：

- Tool Log pane 自动显示最新条目，避免新工具调用被挤到不可见区域。
- Tool Log pane 只承担最近摘要视图；完整历史和手动滚动通过 `/tool-log` 或配置的 tool log shortcut 完成。
- pager 中支持滚动查看完整历史，不影响主 layout 的焦点和输入。
- 持久化到 `workspace/logs/tool-log.jsonl`。

## 15. Jobs

新增 jobs store：

```text
workspace/jobs/
├── jobs.jsonl
├── exec_<id>.log
└── mcp_<id>.log
```

Job record：

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

命令：

```text
/ps
/stop <job_id>
```

## 16. Artifacts And Runs

必须保持概念分离：

| 概念 | 存储 | 用途 |
|---|---|---|
| Tool Log | `logs/tool-log.jsonl` | 操作审计和 UI 摘要 |
| Job Log | `jobs/*.log` | 长任务 stdout/stderr |
| Run Manifest | `runs/<run_id>/manifest.json` | 科学或工具产物证据 |
| Artifact | reports/metrics/figures/logs | 用户可引用产物 |

`/runs` 只显示 run manifest。

已实现：`/runs` 和 `/artifacts <run_id>` 展示 artifact type、hash、producer MCP、关键 metric references、lineage、approval decision 等证据摘要，但仍不在 Chat 主视图直接铺开大 JSON 或大报告。

`/ps` 显示后台 job。

`/tool-log` 后续可显示工具审计。

`/raw [last|call_id]` 显示已持久化的原始 tool result。默认选择最近一个带 raw result 的 tool log entry；MCP tool result 和大输出 tool result 会写入 `logs/raw-tool-results/`，避免原始 JSON 直接铺满 Chat。

带 raw result 的 MCP tool call 会同步登记为已结束的 `mcp` job，log path 指向同一个 raw result 文件。TUI 不自动把任意 MCP call 转为后台运行；真正的后台/可停止 MCP 长任务需要 MCP server 自身提供异步 job 语义。

## 17. Approval Requirements

审批必须具备：

- 操作类型。
- 目标。
- 参数摘要。
- 风险等级。
- approval id。
- 可复制文本命令。
- 键盘操作提示。

显示示例：

```text
Approval Required
apr_xxx [medium]
Action: MCP Tool Call
Target: mcp_agentic-file-search_agentic_explore
Args: {"task": "查看数据库情况"}

> Approve          Enter / Ctrl-Y / F2
  Reject           Esc / Ctrl-N / F3
  Request changes  F4
```

规则：

- 审批结果写入 `workspace/approvals/decisions.jsonl`。
- pending 写入 `workspace/approvals/pending.jsonl`。
- TUI 重启后自动加载。
- approval pane 显示 pending；无 pending 时显示最近 decisions。

## 18. Security And Permissions

TUI 不能绕过 runtime 工具策略。

要求：

- exec 白名单由 config 控制。
- `!<cmd>` 是显式终端模式例外：它不走 agent tool policy，适合用户主动把 TUI 当本地 shell 用。
- read-only 泛化命令必须经过 shell 安全解析。
- 包含 `>`, `>>`, `<`, pipe, `;`, `&&`, `||`, `$()`, backtick 等 shell 结构时必须逐段判断。
- 不能因为命令首 token 是 `ls`、`cat`、`echo` 就放行整条 shell。
- MCP tool allowlist 由 config 控制。
- 写文件、删除文件、高成本任务默认审批。

## 19. Streaming

TUI 应支持流式显示 assistant 回复。

规则：

- 短文本可以直接增量显示。
- Markdown 渲染可以阶段性刷新，但不能造成 ANSI 样式泄漏。
- 长 tool result 默认总结后进入 Chat，完整内容进 pager/log/artifact。
- MCP 原始 JSON 不应直接铺满 Chat，除非用户明确使用 `/raw` 查看。

## 20. Persistence

TUI 重启后应恢复：

- 最近 chat session。
- pending approvals。
- recent approval decisions。
- tool log。
- jobs。
- artifacts。
- campaign status。
- workspace-local UI preferences such as active layout.

不要求恢复：

- 已关闭 overlay。
- 临时 slash menu 状态。
- 输入框未提交内容，首版可不恢复。

## 21. Testing

需要测试：

### 21.1 Unit Tests

- command registry metadata。
- command dispatch 优先级。
- local slash command 不进入 agent。
- unknown slash command 不进入 agent。
- running task command gating。
- approval overlay key handling。
- Esc reject。
- Enter approve。
- input history。
- slash completion。
- layout render smoke。

### 21.2 Integration Tests

- `/runs` 显示 ArtifactIndex run manifest。
- `/artifacts <run_id>` 显示 artifact。
- `/ps` 显示后台 job。
- `/stop <job_id>` 停止后台 job。
- pending approval TUI 重启后仍显示。
- tool log TUI 重启后仍显示。
- long exec 不阻塞新输入。

### 21.3 Visual Smoke

低优先级人工验证。适合 release 前检查，不作为当前开发阻塞项。

- 宽终端。
- 窄终端。
- VS Code terminal。
- 普通 terminal。
- `--once` snapshot。

## 22. Migration Plan

### Phase 1: Command Registry

- 新建 `tui/commands/registry.py`。
- 将 `_TUI_SLASH_COMMANDS` 迁移为 registry。
- 保留旧 import facade。
- 补测试。

### Phase 2: Dispatcher

- 新建 `tui/commands/dispatcher.py`。
- 明确 local / overlay / approval / agent / session。
- `/status`、`/runs`、`/artifacts`、`/approvals`、`/ps`、`/stop` 变成 immediate local。
- 未知 slash command 不进模型。

### Phase 3: Input Controller

- 新建 `tui/input/composer.py`。
- 统一 Enter、Esc、Up、Down、PgUp、PgDn、pager shortcut。
- 支持 `tui.keymap` 覆盖默认快捷键，并让 footer/overlay/help 文案显示解析后的实际按键。
- slash popup 和 history 行为对齐 Codex。

### Phase 4: Overlay Stack

- 新建 `tui/overlays/`。
- approval、pager、picker 迁移为 overlay。
- Esc 语义按 overlay 类型处理。

### Phase 5: LayoutSpec

- 新建 `tui/layouts/` 和 `tui/views/`。
- 当前 layout 改名 `four_pane`。
- render 层只组合 view，不处理业务逻辑。

### Phase 6: Jobs And Tool Log Polish

- jobs store 一等公民。
- `/ps`、`/stop <job_id>`。
- tool log pager。
- 后台任务状态刷新。

## 23. Acceptance Criteria

1. `/runs`、`/artifacts`、`/status`、`/approvals` 不会进入模型。
2. 任务运行中 `/status`、`/runs`、`/ps`、`/stop` 立即响应。
3. pending approval 出现时，Enter approve、Esc reject 可用。
4. `/approve <id>`、`/reject <id>` 仍可用。
5. slash menu 支持方向键选择和 Enter 确认。
6. 输入框 Up/Down 历史稳定可用。
7. 长输出不会污染 Chat 主视图。
8. 后台任务不会阻塞 TUI 输入。
9. Tool Log 自动显示最新条目。
10. `/raw` 可查看已持久化的 MCP 或大输出 tool result。
11. TUI 重启后加载 approvals、tool log、jobs。
12. 默认四窗格 UI 保持可用。
13. 新 layout 可以不改 command/input/overlay 逻辑。

## 24. Risks

| 风险 | 缓解 |
|---|---|
| 一次性大重构破坏已有 TUI | 分 phase，保留 facade 和测试 |
| prompt_toolkit ANSI 渲染再次泄漏 | 避免先 ANSI 后切片；关键区域使用 Rich renderable 或安全 reset |
| local command 和 agent command 边界混乱 | registry 强制声明 dispatch kind |
| 长任务状态不一致 | jobs store 持久化，启动时 reconcile |
| layout 抽象过度 | 首版只实现 `four_pane`，接口预留 |
| approval UX 和远程审批冲突 | overlay 和 slash command 同时保留 |

## 25. Open Questions

None for the current TUI refactor slice.
