# MLP Workspace and UI Design

本文记录 MLP 主动学习工作流下的 workspace 目录设计，以及 TUI 中 `Artifacts` 和 `Companion` 两块区域的设计约定。

设计边界：

- `mlpcopilot` runtime 只负责 workspace、session、approval、artifact index、UI 状态和 MCP/skill 接入。
- MLP/DP-GEN/DeepMD-kit 的具体科学流程由 MCP server 和 skill 实现。
- runtime core 不直接实现数据集验证、模型推理、benchmark、主动学习策略或科学判断。
- 大型科学数据通过文件路径、artifact id、object id 引用，不直接塞进 LLM 上下文。
- 指标和状态必须来自工具产物和 artifact metadata，不能由 LLM 从聊天历史推断。
- backend 原生工作目录应保持原样，runtime 通过 adapter/projector 将其投影成通用 project/run/iteration/artifact 状态。

## 1. Workspace 总体结构

推荐 workspace 分成三类状态：

| 类型 | 是否跨 session | 职责 |
| --- | --- | --- |
| runtime state | 部分跨 session | chat、tool log、approval、memory、TUI 状态 |
| project state | 跨 session | 项目、数据清单、checkpoint、计划、当前 run |
| run/artifact state | 跨 session | 主动学习运行、iteration、产物、证据链 |

推荐结构：

```text
~/.mlpcopilot/workspace/
  sessions/
  logs/
  approvals/
  memory/

  projects/
    <project_id>/
      project.json
      companion.json

      inventory/
        datasets.jsonl
        structures.jsonl
        checkpoints.jsonl
        reference_data.jsonl
        compute_resources.jsonl

      plans/
        active_learning_plan.<plan_id>.json
        validation_plan.<plan_id>.json

      runs/
        <run_id>/
          run.json
          run_state.json
          artifacts.jsonl
          approvals.jsonl

          controller/
            controller.json
            generated_param.json
            generated_machine.json
            rendered_inputs/
              param.json
              machine.json
            submit_scripts/

          backend/
            dpgen/
              param.json
              machine.json
              record.dpgen
              iter.000000/
                00.train/
                01.model_devi/
                02.fp/
              iter.000001/
              iter.000002/

          iterations/
            iter_000000.json
            iter_000001.json
            iter_000002.json

          ui/
            artifacts.state.json
            companion.state.json

          reports/
            run_report.md
            run_report.json

          logs/
            controller.log
            tool_calls.jsonl

  artifacts/
    artifacts.jsonl
    artifacts.duckdb
    blobs/
```

## 2. Project、Run、Iteration 的语义

推荐语义：

| 层级 | 语义 | 示例 |
| --- | --- | --- |
| project | 一个长期 MLP 项目或体系任务 | Fe-C-H 势函数开发 |
| run | 一次具体主动学习/训练/验证执行 | 使用某套阈值和机器配置跑 DP-GEN 风格 AL |
| iteration | run 内的一轮通用阶段视图 | `iter_000003` |
| artifact | 某一步产生的文件、指标、报告或审批证据 | model deviation summary、label task batch |

通用 `iterations` 记录应该放在 `projects/<project_id>/runs/<run_id>/iterations/` 下，而不是直接放在 `projects/<project_id>/iterations/` 下。

backend 原生 iteration 目录应放在 `projects/<project_id>/runs/<run_id>/backend/<backend_name>/` 下。例如 DP-GEN 使用 `iter.000000`、`iter.000001`，不应强制改成 `iter_000000/train/explore/label`。

原因：

- 同一个 project 可以有多次主动学习 run，每个 run 都可能从 `iter_000000` 开始。
- reset、retry、分支实验、对比实验都需要保留 run 上下文。
- iteration 依赖对应 run 的 controller config、selection threshold、model committee、机器配置和审批记录。
- artifact lineage 需要能明确回溯到具体 run 和 iteration。
- DP-GEN 等 backend 对当前工作目录、`record.dpgen` 和 `iter.??????` 目录有原生假设，runtime 不应破坏这些假设。

如果 UI 需要项目级 iteration 总览，可以额外维护索引视图：

```text
projects/<project_id>/iteration_index.jsonl
```

示例：

```json
{
  "run_id": "run_20260505_1330",
  "iteration_id": "iter_000003",
  "stage": "label_pending",
  "status": "blocked",
  "path": "runs/run_20260505_1330/iterations/iter_000003"
}
```

结论：

- 通用 iteration metadata 挂在 run 下。
- backend 原生 iteration workdir 挂在 `runs/<run_id>/backend/<backend_name>/` 下。
- iteration 视图上可以按 project 聚合。

## 3. Runtime State

### 3.1 sessions

`sessions/` 保存 TUI/API 会话历史。

要求：

- `/new` 应创建新的 session。
- chat history 默认属于当前 session。
- 关闭后重新进入同一 root session 时，应恢复最近 active session。
- 不应该从旧 session history 推断当前 skills、MCP 或项目状态。

### 3.2 logs

`logs/` 保存 runtime 工具调用日志。

要求：

- tool log 应 session-scoped。
- 新 session 应有新的 tool log。
- runtime tool log 和 MLP 训练日志分开。
- 训练日志应作为 project/run/iteration artifact 注册。

### 3.3 approvals

`approvals/` 保存人类审批状态。

要求：

- approval 应 session-scoped 或 run-scoped，具体取决于审批对象。
- 危险操作必须阻塞等待审批。
- 审批结果应持久化，并可作为 artifact evidence 引用。

典型审批对象：

- 启动训练 run。
- 停止/重置 run。
- 提交 label/DFT 任务。
- 覆盖已有 controller 配置。
- 删除或归档 run 产物。

### 3.4 memory

`memory/` 保存长期偏好和稳定事实。

要求：

- memory 可以跨 session 共享。
- memory 不能作为当前 skill inventory、MCP inventory、active project、active run 的权威来源。
- 当前状态必须以 workspace state、runtime config 和 loader inventory 为准。

## 4. Project State

### 4.1 project.json

`project.json` 保存项目级稳定信息。

示例：

```json
{
  "project_id": "proj_fech_001",
  "name": "Fe-C-H active learning",
  "domain": "machine_learning_potential",
  "target_use_case": "compressed liquid and defect environments",
  "created_at": "2026-05-05T13:30:00+08:00",
  "active_run_id": "run_20260505_1330",
  "status": "active"
}
```

### 4.2 inventory

`inventory/` 保存项目级资源清单。

推荐文件：

| 文件 | 内容 |
| --- | --- |
| `datasets.jsonl` | 已有训练集、验证集、label 数据集 |
| `structures.jsonl` | 结构池、候选构型、未标注构型 |
| `checkpoints.jsonl` | 模型 checkpoint、frozen model、committee 成员 |
| `reference_data.jsonl` | DFT/reference 数据和计算设置 |
| `compute_resources.jsonl` | 本地/集群/队列/容器资源 |

inventory 只保存 metadata 和路径，不保存大型坐标正文。

### 4.3 plans

`plans/` 保存主动学习计划和验证计划。

要求：

- plan 是意图和执行方案，不是运行状态。
- plan 可以由 skill 生成或修改。
- 执行时应复制或引用到具体 run 中，避免计划变更污染历史 run。

## 5. Run State

### 5.1 run.json

`run.json` 保存一次运行的不可变或半稳定元信息。

示例：

```json
{
  "run_id": "run_20260505_1330",
  "project_id": "proj_fech_001",
  "controller_type": "active_learning_controller",
  "backend": "dpgen",
  "created_at": "2026-05-05T13:30:00+08:00",
  "plan_id": "active_learning_plan.v1",
  "status": "running"
}
```

注意：

- `backend` 可以是 `dpgen`，但目录和 runtime 接口不要绑定 DP-GEN。
- `controller_type` 使用通用名称，方便未来支持其他主动学习控制器。
- backend 原生运行目录由 `backend_workdir` 或约定路径定位，例如 `backend/dpgen`。

### 5.2 run_state.json

`run_state.json` 保存当前运行状态。

示例：

```json
{
  "stage": "explore",
  "iteration_id": "iter_000003",
  "status": "blocked",
  "blocking_reason": "label_approval_required",
  "updated_at": "2026-05-05T14:20:00+08:00"
}
```

### 5.3 controller

`controller/` 保存控制器输入和渲染结果。

推荐内容：

- `controller.json`: runtime/MCP 通用控制器配置。
- `generated_param.json`: 由工具生成的训练/主动学习参数。
- `generated_machine.json`: 由工具生成的机器/队列配置。
- `rendered_inputs/`: 后端实际使用的输入文件。
- `submit_scripts/`: 后端提交脚本。

命名原则：

- runtime 目录名用 `controller`。
- 后端特定文件可以保留原始文件名，例如 DP-GEN 的 `param.json`、`machine.json`。
- 不把顶层目录命名为 `dpgen`，避免未来迁移成本。

### 5.4 backend

`backend/` 保存后端原生工作目录。该目录是后端工具的执行根目录，不要求符合 MLP Copilot 的通用 iteration 目录命名。

DP-GEN 推荐结构：

```text
projects/<project_id>/runs/<run_id>/backend/dpgen/
  param.json
  machine.json
  record.dpgen
  iter.000000/
    00.train/
    01.model_devi/
    02.fp/
  iter.000001/
  iter.000002/
```

设计要求：

- DP-GEN 应在 `backend/dpgen/` 作为 cwd 运行。
- `param.json` 和 `machine.json` 保留 DP-GEN 原生命名。
- `record.dpgen` 是 DP-GEN 断点续跑和状态解析的重要输入。
- `iter.??????/00.train`、`iter.??????/01.model_devi`、`iter.??????/02.fp` 保持原样。
- runtime 不直接改写 DP-GEN 的 iteration 目录。
- projector/adapter 将 DP-GEN 原生目录投影成通用 iteration、artifact 和 companion 状态。

### 5.5 DP-GEN phase 映射

DP-GEN `run_iter(param_file, machine_file)` 每轮包含 9 个 task。通用 phase 应作为投影视图，而不是直接改变 DP-GEN 物理目录。

| MLP Copilot phase | DP-GEN task | DP-GEN directory |
| --- | ---: | --- |
| `train.prepare` | 0 `make_train` | `iter.??????/00.train` |
| `train.run` | 1 `run_train` | `iter.??????/00.train` |
| `train.collect` | 2 `post_train` | `iter.??????/00.train` |
| `explore.prepare` | 3 `make_model_devi` | `iter.??????/01.model_devi` |
| `explore.run` | 4 `run_model_devi` | `iter.??????/01.model_devi` |
| `explore.collect` | 5 `post_model_devi` | `iter.??????/01.model_devi` |
| `label.prepare` | 6 `make_fp` | `iter.??????/02.fp` |
| `label.run` | 7 `run_fp` | `iter.??????/02.fp` |
| `label.collect` | 8 `post_fp` | `iter.??????/02.fp` |

状态解析建议：

```text
read backend/dpgen/record.dpgen
  -> last_completed_iter, last_completed_task
  -> map to normalized phase
  -> scan backend/dpgen/iter.?????? for artifacts and diagnostics
  -> write run_state.json, artifacts.jsonl, ui/*.state.json
```

DP-GEN 适配器应只做目录解析、状态映射和 artifact/event 注册，不做科学判断。

## 6. Artifact 设计

Artifact 是 workspace 中的证据对象，不是普通文件列表。

推荐 schema：

```json
{
  "artifact_id": "art_...",
  "project_id": "proj_...",
  "run_id": "run_...",
  "iteration_id": "iter_000003",
  "kind": "model_deviation",
  "role": "evidence",
  "name": "iter_000003 model deviation summary",
  "path": "/abs/path/to/file.json",
  "producer": "trainingController",
  "tool_call_id": "call_...",
  "status": "ready",
  "created_at": "2026-05-05T13:30:00+08:00",
  "size_bytes": 123456,
  "sha256": "...",
  "parents": ["art_..."],
  "metrics": {
    "max_deviation": 0.42,
    "selected_frames": 128
  },
  "tags": ["active_learning", "explore", "needs_review"],
  "summary": "High deviation found in compressed-volume structures."
}
```

推荐 `kind`：

| kind | 示例 |
| --- | --- |
| `config` | controller config、param、machine |
| `dataset` | DeepMD npy 数据、raw labeled data |
| `structure_pool` | exploration candidate structures |
| `model_checkpoint` | frozen model、checkpoint |
| `training_metric` | loss curve、validation metric |
| `model_deviation` | committee deviation 结果 |
| `label_task` | DFT labeling 输入任务 |
| `reference_result` | DFT/reference 输出 |
| `report` | run report、failure report |
| `log` | controller/train/label 日志 |
| `decision` | 人类审批、接受/拒绝原因 |
| `run_record` | backend 断点续跑和阶段记录，例如 `record.dpgen` |
| `diagnostic` | failure analyzer 或 backend adapter 产出的诊断 |

推荐 `role`：

| role | 说明 |
| --- | --- |
| `input` | run 或 iteration 的输入 |
| `output` | 工具生成的输出 |
| `evidence` | 决策证据 |
| `decision` | 人类审批或选择结果 |
| `diagnostic` | 日志、错误分析、健康检查 |
| `report` | 汇总报告 |

## 7. Artifacts Pane 设计

Artifacts pane 不应该是普通文件浏览器，而应该是当前 project/run 的证据链视图。

核心问题：

- 当前 run 有哪些关键产物？
- 哪些产物是输入？
- 哪些产物是新生成的？
- 哪些产物决定下一步？
- 哪些产物需要审批？
- 哪些产物异常、缺失或过期？

推荐表格：

```text
Kind        Scope          Status     Name                         Metrics
config      run            ready      generated_param.json          -
model       iter_000002    ready      model committee               4 models
deviation   iter_000003    warning    high deviation candidates     max=0.42
label       iter_000003    pending    DFT label batch               128 tasks
report      run            ready      failure analysis              3 issues
```

推荐操作：

| 操作 | 说明 |
| --- | --- |
| filter | 按 project、run、iteration、kind、status 过滤 |
| inspect | 展开 metadata、路径、父子关系、指标摘要 |
| attach | 将 artifact 摘要和路径加入当前 chat 上下文 |
| lineage | 查看 artifact 的输入来源和派生产物 |
| approval | 对危险操作关联审批 |
| open path | 展示路径或小文件摘要，不加载大文件正文 |
| health flags | 显示缺文件、checksum 变化、指标异常、未审批、过期 |

Artifacts pane 的数据来源：

- `projects/<project_id>/runs/<run_id>/artifacts.jsonl`
- `projects/<project_id>/runs/<run_id>/iterations/<iteration_id>.json`
- 全局 `artifacts/artifacts.jsonl` 或 `artifacts/artifacts.duckdb`
- backend 原生目录经过 projector 后注册的 artifact records

优先级：

1. 当前 active project。
2. 当前 active run。
3. 当前 active iteration。
4. 用户筛选条件。

Artifacts pane 不应从 chat history 或 memory 猜 artifact。

## 8. Companion Pane 设计

Companion pane 是 deterministic project/run side panel，不是第二个 agent。

它应该从 workspace state 渲染，不从聊天历史推断。

可以替换或扩展当前 TUI 中的 `Campaign` 区域。

推荐显示：

```text
Project
  Fe-C-H active learning

Goal
  Improve coverage for compressed liquid/defect environments

Active Run
  run_20260505_1330

Stage
  iter_000003 / explore -> label approval pending

Blocking Item
  128 DFT label tasks need approval

Health
  training: ok
  exploration: warning, high deviation cluster found
  labeling: pending
  artifact index: ok

Suggested Next
  1. inspect high-deviation candidates
  2. approve label batch
  3. generate iteration report
```

推荐字段：

| 字段 | 来源 |
| --- | --- |
| project | `project.json` |
| goal | `project.json` 或 active plan |
| active run | `project.json.active_run_id` |
| stage | `run_state.json` |
| blocking item | `approvals.jsonl`、controller status、artifact status |
| health | MCP status、artifact index、run_state、latest diagnostics |
| suggested next | skill 基于 state/artifact 生成，但必须可追溯 |

Companion 需要区分两类建议：

| 类型 | 说明 |
| --- | --- |
| deterministic next action | 从状态机直接推导，例如 approval pending |
| advisory suggestion | skill 根据 artifact 摘要和计划生成，需要标注来源 |

Companion 不应该：

- 从 memory/history 猜当前 skills。
- 从 memory/history 猜当前 active run。
- 直接判断科学结论。
- 编造覆盖率、误差、收敛状态。
- 自动执行危险操作。

## 9. UI 与 Workspace 的状态关系

推荐状态来源：

| UI 区域 | 权威数据源 |
| --- | --- |
| Chat | 当前 session history |
| Tool Log | 当前 session tool log |
| Artifacts | active project/run artifact index |
| Approvals | current session approvals + run approvals |
| Companion | project.json + run_state.json + artifacts + approvals |
| Skills/MCP status | 当前 loader inventory 和 MCP registry |

重要规则：

- `memory` 可以共享。
- `session/log` 应隔离。
- `approval` 按对象决定 session-scoped 或 run-scoped。
- `project/run/artifact` 应持久共享。
- 当前 skills、MCP、active project、active run 必须来自当前 inventory/state。
- UI 不应该从历史回答里恢复 runtime truth。

## 10. UI Read Model 与自动刷新机制

`Artifacts` pane 和 `Companion` pane 建议采用自动刷新机制，但 UI 不直接读取后端运行目录、DP-GEN 目录或训练程序日志。

推荐架构：

```text
MCP / backend tools
  -> artifact records / run events / approval events
  -> projector / reducer
  -> artifacts.state.json
  -> companion.state.json
  -> TUI panes auto-refresh
```

核心规则：

- 后端/MCP 不直接驱动 UI。
- 后端/MCP 只产出事实记录，例如 artifact、run event、approval event、diagnostic event。
- 独立 `projector` 或 `reducer` 将事实记录投影成 UI read-model。
- `Artifacts` pane 和 `Companion` pane 只消费 UI read-model 状态文件。
- UI read-model 是可重建缓存，不是唯一 source of truth。
- UI 不从 chat history 或 memory 推断当前 project、run、artifact、skill 或 MCP 状态。

推荐状态文件位置：

```text
projects/<project_id>/runs/<run_id>/ui/
  artifacts.state.json
  companion.state.json
```

如果需要 project 级总览，可以增加：

```text
projects/<project_id>/ui/
  artifacts.state.json
  companion.state.json
```

### 10.1 artifacts.state.json

`artifacts.state.json` 是给 UI 表格消费的 read-model，不等于完整 artifact ledger。

示例：

```json
{
  "schema_version": 1,
  "project_id": "proj_fech_001",
  "run_id": "run_20260505_1330",
  "revision": 42,
  "updated_at": "2026-05-05T14:30:00+08:00",
  "source": {
    "artifact_index_revision": 128,
    "run_state_revision": 31,
    "approval_revision": 7
  },
  "rows": [
    {
      "artifact_id": "art_001",
      "kind": "model_deviation",
      "scope": "iter_000003",
      "status": "warning",
      "name": "high deviation candidates",
      "metrics": {
        "max_deviation": 0.42,
        "selected_frames": 128
      },
      "path": "/abs/path/to/file.json",
      "health_flags": ["needs_review"]
    }
  ]
}
```

设计要求：

- `revision` 单调递增，UI 用它判断是否刷新。
- `schema_version` 必须存在，便于后续升级。
- `source` 记录投影来源，方便排查 UI 状态是否滞后。
- `rows` 只放 UI 需要的摘要字段。
- 大型文件内容、完整日志、完整坐标数据不进入该文件。

### 10.2 companion.state.json

`companion.state.json` 是给 Companion pane 消费的状态摘要。

示例：

```json
{
  "schema_version": 1,
  "project_id": "proj_fech_001",
  "run_id": "run_20260505_1330",
  "revision": 42,
  "updated_at": "2026-05-05T14:30:00+08:00",
  "source": {
    "project_revision": 5,
    "run_state_revision": 31,
    "artifact_index_revision": 128,
    "approval_revision": 7
  },
  "project": {
    "name": "Fe-C-H active learning",
    "goal": "Improve compressed liquid and defect coverage"
  },
  "stage": {
    "iteration_id": "iter_000003",
    "phase": "explore",
    "status": "blocked"
  },
  "blocking_items": [
    {
      "kind": "approval",
      "message": "128 DFT label tasks need approval",
      "approval_id": "appr_001"
    }
  ],
  "health": [
    {
      "component": "exploration",
      "status": "warning",
      "message": "high deviation cluster found"
    }
  ],
  "suggested_next": [
    {
      "label": "inspect high-deviation candidates",
      "source_artifact_id": "art_001",
      "action": "inspect_artifact"
    }
  ]
}
```

设计要求：

- Companion 是 deterministic side panel，不是第二个 agent。
- `blocking_items` 必须可追溯到 approval、artifact、run event 或 diagnostic event。
- `health` 必须来自工具状态、artifact metadata 或 run state。
- `suggested_next` 可以来自 skill，但必须带 `source_artifact_id`、`approval_id`、`event_id` 或其他可追溯来源。
- Companion 不直接判断科学结论，不编造覆盖率、误差或收敛状态。

### 10.3 Projector / Reducer

`projector` 是后端事实记录到 UI read-model 的转换层。

输入：

- `project.json`
- `run.json`
- `run_state.json`
- run-level `artifacts.jsonl`
- normalized iteration records
- approval records
- diagnostic records
- MCP status records
- backend-native status files，例如 DP-GEN 的 `record.dpgen`
- backend-native iteration directories，例如 DP-GEN 的 `iter.??????`

输出：

- `artifacts.state.json`
- `companion.state.json`

实现要求：

- projector 不执行科学计算。
- projector 不访问 DP-GEN/DeepMD-kit 的内部语义，除非这些语义已经被 MCP 转换成通用 artifact metadata。
- projector 可以读取 backend 原生目录结构和状态锚点，例如 `record.dpgen`、`iter.??????/00.train`、`iter.??????/01.model_devi`、`iter.??????/02.fp`。
- projector 可以被重新运行，并从 source of truth 重建 UI state。
- projector 应保持 schema 稳定，方便 TUI、Web UI、API 复用。

### 10.4 自动刷新

TUI 自动刷新建议使用 `mtime` 轮询或文件 watcher。

要求：

- UI 只读状态文件。
- UI 根据 `revision` 判断是否需要重绘。
- projector 写文件时必须使用原子写入。

推荐写入方式：

```text
write artifacts.state.json.tmp
fsync
rename artifacts.state.json.tmp -> artifacts.state.json
```

这样可以避免 UI 读到半截 JSON。

模块边界：

| 模块 | 职责 |
| --- | --- |
| MCP/backend | 产出事实记录和文件产物 |
| ArtifactIndex | 保存 artifact ledger 和查询索引 |
| ApprovalManager | 保存审批请求和决策 |
| projector/reducer | 生成 UI read-model |
| TUI panes | 读取 read-model 并渲染 |
| skills | 生成计划、解释 workflow、给出可追溯建议 |

这种设计的收益：

- backend 可替换。
- projector 可替换。
- TUI/Web UI/API 可以共用状态文件。
- UI 不绑定 DP-GEN、DeepMD-kit、Slurm 或本地 runner。
- read-model 可版本化、可重建、易调试。

## 11. 后续实现建议

建议分阶段实现：

1. 定义 workspace schema 和 project/run 初始化逻辑。
2. 实现 ArtifactIndex 的 JSONL 后端。
3. 定义 backend workdir 约定，例如 `runs/<run_id>/backend/dpgen/`。
4. 定义 run event、approval event、diagnostic event 的最小 schema。
5. 让现有 training controller MCP 输出 artifact records 和 event records。
6. 实现 DP-GEN adapter/projector，读取 `record.dpgen` 和 `iter.??????`，生成通用状态。
7. 实现通用 projector/reducer，生成 `artifacts.state.json` 和 `companion.state.json`。
8. 将 Artifacts pane 从文件列表改为 artifact evidence table。
9. 将 Campaign pane 替换为 Companion pane。
10. 增加 project/run selector。
11. 增加 artifact inspect/attach/lineage 操作。

实现边界：

- runtime 可以实现 `ArtifactIndex`、workspace schema、UI 渲染、审批绑定。
- MCP 负责生成 MLP 领域 artifact 和 metrics。
- skill 负责解释 workflow、生成计划和建议动作。
- runtime 不实现 MLP 科学算法。
