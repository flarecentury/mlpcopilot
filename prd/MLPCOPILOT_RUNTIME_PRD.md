# PRD: MLP Copilot Runtime

## 1. 产品定位

**MLP Copilot Runtime** 是从 mlpcopilot 直接产品化改造的垂直场景宿主运行时，面向机器学习势训练与验证工作流。

本 PRD 只定义 mlpcopilot 运行时本身的魔改范围。MCP server 和 skill pack 是插件能力，放到独立 PRD 中定义。

核心判断：

- 先做一个适合 MLP 场景的稳定宿主。
- 宿主只负责对话、会话、审批、界面、插件接入和证据索引。
- 科学计算、数据校验、模型推理、验证方法论不写进 mlpcopilot core。

## 2. 背景

原始 mlpcopilot 是通用 agent runtime，包含多通道 gateway、MCP 接入、memory、skills、OpenAI-compatible API、CLI 和大量默认工具。对 MLP 训练与验证场景来说，它的能力基础够用，但默认行为太宽：

- 通道过多，部署和安全面过大。
- 默认工具包含 web、spawn、notebook 等非必要能力。
- 缺少科学工作流需要的 approval、artifact、run manifest 和 TUI 工作台。
- 缺少面向插件能力的明确边界。

MLP Copilot Runtime 的目标不是把 mlpcopilot 改造成科学计算平台，而是把它收敛成一个可靠的垂直宿主。

## 3. 目标场景

首个场景：**MLP checkpoint 验证与数据质量审查的本地/远程操作台**。

典型用户通过 TUI 或 Telegram 与 agent 交互：

1. 指定 workspace。
2. 接入一个或多个 MCP server。
3. 加载 MLP 项目上下文。
4. 让 agent 根据 skill 流程调用 MCP 工具。
5. 查看 tool log、artifact、approval。
6. 对高成本任务、模型 readiness、长期记忆更新做人工审批。

## 4. 用户

主要用户：

- 机器学习势开发者。
- 计算材料研究人员。
- 运行数据清洗、模型评估、主动学习和验证任务的工程/科研人员。

次要用户：

- 远程审批者。
- 需要用 OpenAI-compatible API 接入该 agent 的自动化系统。

## 5. 产品目标

1. 将 mlpcopilot 收敛为 MLP 场景的最小可信宿主。
2. 默认只保留 Telegram gateway，减少无关通道和安全面。
3. 增加本地 TUI，作为主要工作台。
4. 增加通用 ApprovalManager，支撑 human-in-the-loop。
5. 增加 ArtifactIndex，记录 run、manifest、report、decision。
6. 保留 MCP client，并明确支持本地和远程 MCP 插件。
7. 保留 skill 发现机制，但 skill 内容由插件包提供。
8. 保留 OpenAI-compatible API，便于外部系统集成。

## 6. 非目标

1. 不实现 MLP 数据校验算法。
2. 不实现模型推理、benchmark、job submit。
3. 不内置 validation planning 方法论。
4. 不把 MCP server 代码写进 mlpcopilot core。
5. 不把 skill 内容写死到主 prompt。
6. 不保留所有社交通道。
7. 不默认启用 unrestricted shell。
8. 不建设重型 Web 平台作为首版主界面。

## 7. 模块边界

| 层 | 本 PRD 是否覆盖 | 职责 |
|---|---|---|
| MLP Copilot runtime | 是 | agent loop、session、memory、TUI、Telegram、API、approval、artifact、plugin registry |
| MCP server | 否 | 数据校验、模型推理、验证执行、报告生成 |
| Skill pack | 否 | 方法论、操作流程、领域判断框架 |

Runtime 只知道“有工具、有 skill、有 artifact、有审批”，不理解具体科学算法。

DP-GEN 相关适配器（例如 `mlpcopilot.plugins.dpgen_adapter`）属于 plugin 层。Runtime 可以展示其投影出的 artifact、run manifest 和 display document，但不解析 `record.dpgen`、`iter.*` 或其他 DP-GEN 科学/调度语义。

## 8. 保留的 mlpcopilot 能力

保留：

- `AgentLoop`
- `ContextBuilder`
- `SessionManager`
- `MemoryStore`
- `ToolRegistry`
- `providers`
- `MCP client`
- `bus`
- `config`
- `telegram channel`
- `OpenAI-compatible API`

继续支持：

- `mlpcopilot serve`
- `mlpcopilot agent`
- MCP `stdio`
- MCP `sse`
- MCP `streamableHttp`
- workspace skills

## 9. 默认禁用能力

在 `mlpcopilot` profile 下默认禁用：

- Slack、Discord、Feishu、WeChat、WeCom、WhatsApp、Matrix、Email、QQ、DingTalk、MSTeams。
- WebUI / WebSocket，除非开发模式显式启用。
- `web_search` 和 `web_fetch`。
- unrestricted `exec`。
- generic `spawn`。
- `notebook_edit`。
- 非必要内置 skills。
- cron 类非科学提醒。

## 10. Runtime Profile

新增：

```json
{
  "runtimeProfile": "mlpcopilot"
}
```

行为：

| 项 | 行为 |
|---|---|
| Channels | 默认只加载 Telegram、CLI、API |
| Tools | 默认最小工具集 |
| MCP | 可连接本地或远程 MCP server |
| Skills | 只加载 workspace 中启用的 skills |
| Exec | 默认开启，必须 审批 + allowlist。 |
| Web | 默认关闭 |
| Workspace | 强制初始化 MLP Copilot schema |
| Approval | gated action 必须审批 |

## 11. Workspace Schema

默认 workspace：

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

Runtime 只创建目录和基础模板，不生成科学验证内容。

`PROJECT.md` 存储：

- 项目名称。
- 目标体系或应用域。
- 当前 workspace 约定。
- 当前已知的 MCP/skill 状态摘要或引用。
- 已批准的高层决策。
- 当前 acceptance criteria 的路径或引用。

## 12. Tool Policy

`mlpcopilot` 默认工具：

- `ask_user`
- `my`（默认只读，只有显式启用 `tools.my.allowSet` 时才允许修改运行时状态）
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
- `web_search` / `web_fetch` 仅在显式启用 web tools 时注册。
- `exec` 仅在显式启用且配置 allowlist 时注册。

审批策略：

- agent 侧所有内置工具和 MCP 工具调用统一经过 runtime ApprovalManager。
- `tools.approvalAllowlist` 精确匹配放行工具名；`mlpcopilot` 默认放行只读/状态工具，例如 `read_file`、`list_dir`、`grep`、`glob`、`file_info`、`web_search`、`web_fetch`、`workstate`。
- MCP 工具若通过标准 `ToolAnnotations.readOnlyHint=true` 标注为只读，且未标注 `destructiveHint=true`，runtime 默认放行；未标注或可能修改文件/启动任务/取消任务的 MCP 工具继续审批。
- `exec` 保留独立策略：精确 `allowCommands` 可直接放行；其他命令按 exec 自身 approval flow 阻塞。
- `!cmd` 是 TUI 终端模式，不进入 agent tool approval policy。

禁止：

- 通过 LLM 上下文传输大数据集、轨迹或大段结构坐标。
- 让 LLM 自行生成科学指标。
- 让 plugin 在 MCP 输出中声明 `approval_hint`、`requires_approval` 或通过 `approved=true` 绕过 runtime ApprovalManager。

## 13. MCP 接入

Runtime 使用 mlpcopilot 已有 MCP client，不在 core 中实现科学 MCP 逻辑。

支持：

- `stdio`：本地 MCP server。
- `sse`：远程 SSE MCP endpoint。
- `streamableHttp`：远程 HTTP MCP endpoint。

配置示例：

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

Runtime 需要增强：

- 在 TUI 中显示 MCP server 连接状态。
- 在 tool log 中显示 MCP server、tool、duration、status。
- 对远程 MCP 失败给出可操作错误。
- MCP/skill 来源由源码自动发现和 config 显式配置决定；runtime 可展示连接状态，但不写入单独的 workspace capability 配置文件。

## 14. Skill 接入

Runtime 不定义 MLP skills 内容，只负责加载和展示。

要求：

- workspace `skills/` 下的 skill 可被发现。
- `disabledSkills` 可关闭无关 skill。
- TUI 能显示当前启用 skill 列表。
- ContextBuilder 注入 skill summary 时受 token budget 限制。
- Skill 不得声明自己能直接生成科学指标。

## 15. TUI

TUI 交互与模块化重构的详细要求见 `MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`。本节只保留 runtime 主 PRD 的范围和首版形态。

新增命令：

```bash
mlpcopilot tui
```

首版布局：

```text
┌──────────────────────────────┬──────────────────────────────┐
│ Chat / Task                  │ Tool Log                     │
├──────────────────────────────┼──────────────────────────────┤
│ Artifacts                    │ Approvals                    │
└──────────────────────────────┴──────────────────────────────┘
Status: model | workspace | MCP | skills | run_id | pending approvals | Telegram
```

Pane：

- Chat / Task：对话、计划草稿、用户输入。
- Tool Log：工具调用、MCP server、参数摘要、状态、耗时、错误。
- Artifacts：manifest、metrics、report、figures、logs。
- Approvals：待审批、批准、拒绝、要求修改。

MVP 可先实现只读 TUI + approval 操作；复杂 artifact 浏览后置。

## 16. Telegram

Telegram 是唯一默认远程 gateway。

命令：

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

限制：

- 不在 Telegram 中展示长报告。
- 不在 Telegram 中浏览大日志。
- 不允许未授权用户触发任务。

必须配置 `allowFrom`。

## 17. OpenAI-Compatible API

保留：

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
```

要求：

- 支持 `session_id`。
- 支持 streaming。
- 支持文件上传或路径引用。
- API session 可触发相同 approval workflow。
- 默认绑定 `127.0.0.1`。
- 对公网暴露前必须配置 API key 或反向代理鉴权。

## 18. ApprovalManager

ApprovalManager 是 runtime 能力，不属于 MCP 插件。

职责：

- 创建审批项。
- 阻塞 gated action。
- 接收 TUI、Telegram、CLI、API 的审批结果。
- 记录 decision log。
- 将 approval record 写入 run manifest。

存储：

```text
approvals/pending.jsonl
approvals/decisions.jsonl
```

审批状态：

- `pending`
- `approved`
- `partially_approved`
- `rejected`
- `needs_changes`
- `expired`

必须审批的动作类型：

- 执行中高成本任务。
- 标记 checkpoint 可用于目标场景。
- 修改 project-level acceptance criteria。
- 更新长期 memory 中的确认事实。
- 删除或覆盖已有 run artifact。
- 对外导出或推送结果。

## 19. ArtifactIndex

ArtifactIndex 是 runtime 能力。

每个 run 至少有：

```text
runs/<run_id>/manifest.json
```

字段：

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

Runtime 不解释科学指标，只保证 artifact 可索引、可追溯。

已实现：`RunManifest` / `ArtifactIndex` 支持 `metrics`、`lineage`、`decisions` evidence 字段，用于记录 MLP 工作流中的证据链。该扩展仍属于 runtime 索引能力，不把 dataset validation、checkpoint inference、benchmark 或主动学习算法写入 core。

建议扩展字段：

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

要求：

- 数值结论必须引用 `metrics[*].source_artifact` 或具体 artifact path。
- TUI、Telegram 和 API 只展示 evidence 摘要；大文件通过 artifact path 或 `/raw` 查看。
- MCP/Skill 负责生成科学指标和报告，Runtime 只记录路径、hash、类型、producer 和引用关系。

## 20. Memory Policy

Memory 层：

| 层 | 文件 | 用途 |
|---|---|---|
| session | `sessions/*.jsonl` | 会话历史 |
| history | `memory/history.jsonl` | 历史摘要 |
| project | `PROJECT.md` | 项目状态 |
| long-term | `memory/MEMORY.md` | 人类确认事实 |
| artifact | `runs/*/manifest.json` | 工具证据 |

规则：

- 不把原始结构坐标写入长期 memory。
- 不把一次性日志写入长期 memory。
- 长期事实更新需要 approval。
- 数值结论优先引用 artifact。

## 21. CLI

保留：

```bash
mlpcopilot agent
mlpcopilot serve
mlpcopilot gateway
```

新增：

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

`mlpcopilot mlp` 命令只管理 runtime 状态，不执行科学算法。

## 22. 配置示例

```json
{
  "runtimeProfile": "mlpcopilot",
  "agents": {
    "defaults": {
      "workspace": "~/.mlpcopilot/workspace",
      "provider": "openrouter",
      "model": "anthropic/claude-opus-4-6",
      "timezone": "Asia/Shanghai",
      "disabledSkills": ["weather", "github", "clawhub"],
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

MVP 包括：

1. `mlpcopilot` runtime profile。
2. channel whitelist，默认只启用 Telegram。
3. workspace initializer。
4. minimal tool policy。
5. MCP status display。
6. workspace skill loading and status display。
7. ApprovalManager。
8. ArtifactIndex。
9. TUI 四 pane skeleton。
10. Telegram approval。
11. CLI approval。
12. OpenAI-compatible API 保持可用。

MVP 不包括：

- MLP 数据校验。
- MLP 模型推理。
- validation planning skill。
- 远程 job scheduler。
- 完整 WebUI。

## 24. 工作量估算

| 范围 | 预计工作量 | 说明 |
|---|---:|---|
| Lean runtime | 2-3 周 | profile、workspace、channel whitelist、approval、artifact、CLI |
| Runtime MVP | 3-5 周 | 加 TUI skeleton、Telegram approval、MCP/skill 状态展示、API workflow |
| Robust runtime | 6-8 周 | 更完整权限、错误恢复、TUI polish、测试和文档 |

先做 Lean runtime，再接 MCP/Skill 插件。

## 25. 实施计划

当前状态：runtime MVP 已基本完成。以下 phase 作为实现历史和验收映射保留，不再表示近期待办队列。真实部署 smoke 和人工 TUI visual smoke 属于低优先级 release checklist。

### Phase 1: Profile And Workspace

- 增加 `runtimeProfile`。
- 增加 `mlpcopilot` profile。
- 增加 workspace initializer。
- 增加 `PROJECT.md` 和目录模板。
- 禁用无关通道和工具。

### Phase 2: Plugin Host

- 保留 MCP client。
- 增加 MCP connection status。
- 增加 skill status。
- 限制 tool registration。

### Phase 3: Approval And Artifact

- 增加 ApprovalManager。
- 增加 pending/decision storage。
- 增加 ArtifactIndex。
- 将 approval record 关联到 run manifest。

### Phase 4: TUI And Telegram

- 增加 `mlpcopilot tui`。
- 实现四 pane skeleton。
- 实现 approval pane。
- Telegram 支持 approve/reject/changes。

### Phase 5: API And Hardening

- API 支持 approval workflow。
- 补充 config validation。
- 补充权限和路径校验。
- 增加基础测试。

## 26. 验收标准

1. 可以用 `runtimeProfile=mlpcopilot` 启动。
2. 默认只加载 Telegram、CLI、API。
3. 默认关闭 web、exec、spawn、notebook。
4. 可以初始化 MLP workspace。
5. 可以连接本地或远程 MCP server。
6. 可以显示已启用 MCP tools 和 skills。
7. gated action 会创建 approval。
8. 未批准的 gated action 不会执行。
9. approval 可通过 TUI、Telegram、CLI 处理。
10. run manifest 可记录 tool source、inputs、outputs、artifacts、approval。
11. OpenAI-compatible API 仍可使用。
12. Runtime core 中不包含 MLP 数据校验或模型推理算法。

## 27. 风险

| 风险 | 缓解 |
|---|---|
| core 继续膨胀 | 严格禁止科学算法进入 runtime |
| TUI 拖慢首版 | 先做 skeleton，复杂 artifact 浏览后置 |
| approval 形式化 | gated action 无 approval 必须 blocked |
| 远程 MCP 安全风险 | token、headers、workspace scoped references、超时 |
| skill 注入过多污染上下文 | skill summary 限制 token budget |
