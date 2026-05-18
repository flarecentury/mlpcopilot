# PRD: MLP Copilot MCP And Skill Pack

## 1. 产品定位

**MLP Copilot MCP And Skill Pack** 是运行在 MLP Copilot Runtime 之上的机器学习势插件能力层。

插件层包含两类能力：

- **MCP servers**：提供可执行、可测试、可远程部署的工具，例如 DP-GEN 控制、数据检查、模型评估、覆盖分析和报告生成。
- **Skills**：提供方法论、流程指导和人机协作策略，例如主动学习策略生成、训练故障排查和验证计划制定。

本 PRD 不定义 mlpcopilot runtime 的 TUI、Telegram、approval、session、memory 或 OpenAI-compatible API。这些由 `MLPCOPILOT_RUNTIME_PRD.md` 定义。

## 2. 背景

当前 MLP 训练流以 **DeepMD-kit** 为训练框架，并由 **DP-GEN** 控制主动学习流程。

DP-GEN 已经负责：

- 根据 `param.json` 和 `machine.json` 执行 `dpgen run`。
- 组织主动学习迭代。
- 执行训练、模型偏差探索和第一性原理标注。
- 通过 `record.dpgen` 记录迭代和阶段。
- 通过 `iter.000000/00.train`、`01.model_devi`、`02.fp` 管理每轮产物。
- 通过 DPDispatcher 接入本地、Slurm、PBS、SSH 等计算资源。

MLP Copilot 不应该重写 DP-GEN，而应该先提供一个 **训练流控制器插件**：

- 根据体系和目标生成主动学习策略。
- 生成 DP-GEN `param.json` 和 `machine.json`。
- 校验配置文件。
- 启动、停止、重置和查看 训练 run。
- 读取 训练状态。
- 分析 DP-GEN 报错日志并给出可执行修复建议。

DP-GEN 不覆盖的能力，例如模型性能测试、数据库覆盖情况、局域原子环境覆盖和构型缺口分析，应作为后续独立 MCP 模块实现。

因此首版训练流控制器必须采用 **backend/provider abstraction**：

- 通用 MCP 名称保持为 `mlp_training_controller_mcp`。
- DP-GEN 是首个 backend provider，而不是插件总命名。
- 后续可以接入其他主动学习或训练编排框架，而不改变 runtime 和上层 skill。
- 工具、artifact 和报告使用通用 `training_*` 命名，并在 metadata 中记录 `backend: "dpgen"`。

## 3. 产品目标

1. 首先实现 `mlp_training_controller_mcp`，以 DP-GEN backend 把 DeepMD-kit + DP-GEN 主训练流纳入 MLP Copilot。
2. 提供 `mlp-active-learning` skill，指导用户从体系目标生成主动学习策略。
3. 所有执行动作通过 MCP 工具完成，并产出 artifact path、hash、manifest 和错误信息。
4. 所有高成本或破坏性动作必须交给 runtime ApprovalManager 阻塞审批。
5. 不在 mlpcopilot core 中实现 DP-GEN 或科学分析逻辑。
6. 支持 backend-specific 配置 profile、模板文件、远程资源配置和日志诊断。
7. 对 machine/resource 配置中的 secret 做脱敏、引用化和安全校验。
8. 已以独立 MCP 模块补齐 dataset validation 首版、model evaluation 首版和 report rendering 首版；coverage analysis 暂缓。
9. 大数据、轨迹、结构和日志全文通过文件路径、artifact id 或对象引用传递，不进入 LLM 上下文。

## 4. 非目标

1. 不修改 mlpcopilot runtime 的 approval、TUI、channels、session 或 API 内部实现。
2. 不重写 DP-GEN 主循环。
3. 不替代 DeepMD-kit、LAMMPS、VASP、ABACUS、CP2K、Gaussian 或其他后端软件。
4. 不让 LLM 直接生成科学指标。
5. 不自动声明模型可靠或 ready。
6. 不把训练流控制器命名或接口绑定死到 DP-GEN。
7. 不在 训练流控制器中实现完整模型泛化 benchmark。
8. 不在 训练流控制器中实现局域原子环境覆盖算法。
9. 不默认取消远程 HPC 队列任务，除非用户显式请求且审批通过。
10. 不在 artifact、日志摘要或 LLM 上下文中暴露明文密码、token、私钥或 SSH secret。

## 5. 插件边界

| 插件类型 | 负责 | 不负责 |
|---|---|---|
| `mlp_training_controller_mcp` | 通用训练流控制；首个 backend 为 DP-GEN；配置生成、校验、启动、停止、重置、状态读取、日志诊断、run 报告 | 模型泛化评估、数据库覆盖算法、局域环境分析 |
| `mlp_dataset_mcp` | 当前负责数据集文件布局、schema、基础完整性、hash 和报告 artifact | 训练 run 控制；单位、异常结构、重复结构、split 泄漏、固定 OOD/gap 判定等通用重检查暂缓 |
| `mlp_model_eval_mcp` | checkpoint 性能评估、benchmark、模型对比 | DP-GEN 进程管理 |
| `mlp_coverage_mcp` | 低优先级 backlog：数据覆盖、局域原子环境覆盖、构型缺口 | 当前不实现；DP-GEN 调度 |
| `mlp_report_mcp` | 当前负责汇总已有 run、数据、模型和审批证据的 Markdown evidence report | 生成未由工具产出的科学指标；HTML/PDF 暂缓 |
| Skills | 流程、策略、解释、风险判断、工具调用顺序 | 直接执行科学计算或伪造指标 |

审批由 runtime 负责。MCP server 保持标准工具语义和标准 JSON 输出，不声明 `approval_hint`、`requires_approval`，也不暴露 `approved=true` 之类的审批绕行参数。

## 5.1 当前优先级调整

截至 2026-05-09，插件层近期目标调整为“稳定已落地能力 + 提供项目化 OOD 测试建议”。不恢复整套 coverage/job 大模块，也不把固定 OOD 验证流程写成通用工具。

近期优先级：

1. P0：维护并硬化已实现的 training controller、dataset 首版、model evaluation 首版、report 首版和对应 skills。
2. P0/P1：新增并维护 `mlp-ood-test-advisor` skill，帮助用户按目标体系、部署边界、reference budget 和已有证据选择 OOD 测试切片、artifact 和 approval gate。
3. P1：如具体项目需要，再按该项目化学体系和审稿问题设计最小 OOD/gap evidence artifact；不把固定 OOD 验证流程写死为通用 MCP 行为。
4. P1：围绕真实 DP-GEN/DeePMD 项目修 bug、补文档、补少量证据字段，不引入大模块。
5. P2：完整 coverage MCP、job MCP、dataset 深度科学检查、固定 OOD/gap audit 工具、HTML/PDF 报告输出暂时降级为 backlog，不作为当前验收阻塞项。

除非用户明确重新提升优先级，后续开发不应主动推进 P2 backlog。

## 6. 推荐包结构

```text
mlp-sentinel-plugins/
├── mcp/
│   ├── mlp_training_controller_mcp/
│   │   ├── server.py
│   │   ├── controller.py
│   │   ├── config_builder.py
│   │   ├── status.py
│   │   ├── log_analyzer.py
│   │   ├── template_assets.py
│   │   ├── secret_redactor.py
│   │   ├── schemas.py
│   │   ├── backends/
│   │   │   ├── __init__.py
│   │   │   └── dpgen.py
│   │   └── templates/
│   ├── mlp_dataset_mcp/
│   ├── mlp_model_eval_mcp/
│   ├── mlp_coverage_mcp/
│   ├── mlp_job_mcp/
│   └── mlp_report_mcp/
├── skills/
│   ├── mlp-active-learning/
│   │   └── SKILL.md
│   ├── mlp-dataset-validation/
│   │   └── SKILL.md
│   ├── mlp-validation-planner/
│   │   └── SKILL.md
│   ├── mlp-checkpoint-auditor/
│   │   └── SKILL.md
│   └── mlp-failure-analysis/
│       └── SKILL.md
├── schemas/
├── templates/
└── examples/
```

首版必须实现：

1. `mlp_training_controller_mcp`
2. `mlp-active-learning` skill

当前已超出首版要求，完成了 dataset/model-eval/report 首版。`mlp_coverage_mcp/` 和 `mlp_job_mcp/` 只作为 backlog 目录占位，不是当前实施要求。

### 6.1 MCP 组织原则

不要把所有 MLP 工具合并成单个 MCP server。这样会让维护、测试、权限边界和审稿解释都变复杂。近期保持按职责拆分：

- `mlp_training_controller_mcp`：训练流控制和 DP-GEN backend。
- `mlp_dataset_mcp`：dataset 文件级检查。
- `mlp_model_eval_mcp`：checkpoint benchmark、预测和 metrics artifact。
- `mlp_report_mcp`：跨工具 evidence aggregation 和 audit report。

统一性由 runtime 提供：MCP discovery、tool approval、tool log、artifact index、run manifest、TUI/API 展示和 workspace 路径约定。插件只需要提供标准 MCP 工具和可复现 artifact。

## 7. MCP 部署方式

支持三种方式：

| 方式 | 场景 |
|---|---|
| `stdio` | 本地开发、本地工作站、本地 训练项目 |
| `sse` | 远程服务，兼容 SSE MCP endpoint |
| `streamableHttp` | 推荐远程 HTTP MCP endpoint |

远程部署适合：

- HPC 登录节点。
- 数据服务器。
- GPU 工作站。
- 内部 MLP 工具服务。

远程安全要求：

- 必须支持 token 或 mTLS 等认证。
- 必须限制 workspace root 或 project namespace。
- 必须限制单次任务资源。
- 必须限制返回体大小。
- 大日志和大结构文件必须通过 artifact path 返回。

## 8. MCP 通用输出协议

所有 MCP 工具返回 JSON 文本，结构如下：

```json
{
  "status": "success|failed|blocked",
  "summary": "...",
  "metrics": {},
  "artifacts": [
    {
      "type": "report|metrics|figure|log|structure|manifest|config|status",
      "path": "...",
      "sha256": "..."
    }
  ],
  "warnings": [],
  "errors": []
}
```

规则：

- 不只返回自然语言。
- 生成的文件必须有 path。
- 关键输入必须有 hash。
- 使用缓存时必须报告 cache key、cache source、input hash。
- 长任务应返回 job id、run id 或 controller state id。
- MCP 输出可以包含摘要，但不能把大日志、轨迹或结构全文放入 LLM 上下文。
- MCP 工具本身不实现 runtime approval；所有 agent 侧 MCP 调用由 runtime approval policy 拦截，显式 allowlist 放行。

## 9. MLP Training Controller MCP

首个必须实现的 MCP module：`mlp_training_controller_mcp`。

### 9.1 目标

以通用训练流控制器方式接入 MLP 主动学习和训练编排。首个 backend 是 DP-GEN，后续可以扩展到其他主动学习框架或训练调度器。

控制器提供：

- 训练项目检查。
- 主动学习策略到 backend-native 参数文件的生成。
- 机器资源配置到 backend-native machine/resource 文件的生成。
- 训练后端配置校验。
- 训练 run 启动、停止、重置。
- 训练迭代状态读取。
- 训练日志和失败原因分析。
- 训练 run 报告和 artifact manifest。

### 9.2 Backend Provider Model

训练流控制器必须提供 backend provider 接口。

首个 provider：

```text
backend = "dpgen"
```

DP-GEN provider 负责：

- 识别 `param.json`、`machine.json`、`record.dpgen`、`dpgen.log`。
- 识别 `iter.??????/00.train`、`01.model_devi`、`02.fp`。
- 使用 DP-GEN `dargs` schema 校验 `param.json` 和 `machine.json`。
- 解析 DP-GEN stage。
- 启动 `dpgen run param.json machine.json`。
- 诊断 DP-GEN、DPDispatcher、DeepMD-kit、LAMMPS、CP2K、VASP、ABACUS 等常见错误。

通用 controller metadata 必须记录：

```json
{
  "backend": "dpgen",
  "backend_version": "...",
  "training_engine": "deepmd-kit",
  "exploration_engine": "lammps",
  "labeling_engine": "cp2k|vasp|abacus|pwscf|gaussian|custom"
}
```

### 9.3 DP-GEN Backend 已有约定

DP-GEN 主入口：

```text
dpgen run param.json machine.json
```

DP-GEN 每轮目录：

```text
iter.000000/
├── 00.train/
├── 01.model_devi/
└── 02.fp/
```

训练状态文件：

```text
record.dpgen
```

`record.dpgen` 每行格式：

```text
<iteration_index> <stage_index>
```

阶段映射：

| Stage | DP-GEN 阶段 |
|---:|---|
| 0 | `make_train` |
| 1 | `run_train` |
| 2 | `post_train` |
| 3 | `make_model_devi` |
| 4 | `run_model_devi` |
| 5 | `post_model_devi` |
| 6 | `make_fp` |
| 7 | `run_fp` |
| 8 | `post_fp` |

### 9.4 工具列表

首版工具：

```text
inspect_training_project(project_path, backend="auto")
generate_training_param(backend, system_profile_path, strategy_config_path, output_path)
generate_training_machine(backend, machine_profile_path, output_path)
validate_training_inputs(backend, param_path, machine_path)
start_training_run(backend, project_path, param_path, machine_path)
stop_training_run(run_id)
reset_training_run(backend, project_path, target_iteration, target_stage, mode)
get_training_status(project_path, backend="auto")
list_training_iterations(project_path, backend="auto")
inspect_training_iteration(project_path, iteration, backend="auto")
collect_training_logs(project_path, backend="auto")
analyze_training_failure(project_path, backend="auto")
build_training_run_report(project_path, backend="auto")
```

首个开发切片只实现只读和低风险工具：

```text
inspect_training_project
validate_training_inputs
get_training_status
list_training_iterations
inspect_training_iteration
collect_training_logs
analyze_training_failure
```

### 9.5 `inspect_training_project`

输入：

```text
project_path
```

检查：

- 是否存在 `param.json`。
- 是否存在 `machine.json`。
- 是否存在 `record.dpgen`。
- 是否存在 `dpgen.log`。
- 是否存在 `iter.??????` 目录。
- 是否包含 `00.train`、`01.model_devi`、`02.fp`。
- 是否存在 controller state。

输出：

```json
{
  "status": "success",
  "summary": "Detected DP-GEN project with 4 iterations.",
  "metrics": {
    "iterations_found": 4,
    "has_record": true,
    "has_log": true,
    "has_param": true,
    "has_machine": true
  },
  "artifacts": []
}
```

### 9.6 `generate_training_param`

输入：

```text
system_profile_path
strategy_config_path
output_path
```

`system_profile.json` 描述体系：

```json
{
  "elements": ["Li", "P", "S", "Cl"],
  "system_type": "bulk|surface|interface|molecule|reaction|amorphous",
  "initial_data": ["datasets/init"],
  "exploration_structures": ["structures/**/*.vasp"],
  "target_conditions": {
    "temperature_k": [300, 600, 900],
    "pressure_bar": [1, 10000],
    "ensemble": ["nvt", "npt"]
  }
}
```

`strategy_config.json` 描述主动学习策略：

```json
{
  "numb_models": 4,
  "iterations": 8,
  "model_devi_f_trust_lo": 0.05,
  "model_devi_f_trust_hi": 0.15,
  "fp_task_min": 5,
  "fp_task_max": 100,
  "fp_style": "vasp",
  "train_backend": "pytorch"
}
```

生成：

```text
runs/<run_id>/training_param.json
runs/<run_id>/training_param_generation_report.md
```

要求：

- 生成后必须用 DP-GEN `dargs` schema 校验。
- 不硬编码单一材料体系。
- 不替用户决定最终高成本策略，只给出建议和可审批配置。
- 保留输入文件 hash。
- 支持 backend-specific template assets，例如 LAMMPS input template、CP2K input template、DFT-D3 参数文件引用。
- 支持 DP-GEN `model_devi_jobs[*].template` 和 `rev_mat` 参数矩阵。
- 必须校验 `rev_mat` 中声明的变量是否在模板文件中有对应占位符。
- 必须记录模板文件 path、sha256 和用途。
- 不把模板全文注入 LLM 上下文，只返回摘要、path 和 hash。

### 9.7 `generate_training_machine`

输入：

```text
machine_profile_path
output_path
```

`machine_profile.json` 描述计算资源：

```json
{
  "train": {
    "command": "dp",
    "batch_type": "Slurm",
    "context_type": "local",
    "gpu_per_node": 1,
    "cpu_per_node": 8,
    "group_size": 1,
    "queue_name": "gpu"
  },
  "model_devi": {
    "command": "lmp",
    "batch_type": "Slurm",
    "context_type": "local",
    "gpu_per_node": 1,
    "cpu_per_node": 8,
    "group_size": 10
  },
  "fp": {
    "command": "bash /path/to/cp2k_cpu_wrapper.sh -in *.inp",
    "batch_type": "shell|PBS|Slurm",
    "context_type": "SSHContext",
    "cpu_per_node": 32,
    "gpu_per_node": 0,
    "group_size": 5,
    "remote_root": "/remote/work/path",
    "source_list": ["/path/to/env.sh"]
  }
}
```

生成：

```text
runs/<run_id>/training_machine.json
runs/<run_id>/training_machine_generation_report.md
```

要求：

- 不保存明文密码。
- 远程认证信息通过环境变量、SSH config、token 或外部 secret 引用。
- 输出必须标注资源风险，例如远程队列、GPU 数量、FP 任务数量。
- 支持 `SSHContext`、local context、shell wrapper command、Slurm/PBS 等不同资源模式。
- 支持用户常用的 Singularity/容器 wrapper script，但必须把 command 作为可审计 artifact。
- 必须在展示和报告中脱敏 `password`、`token`、`private_key`、`secret` 等字段。
- 如果输入 machine 文件含明文 secret，validation 必须给出高优先级 warning，并建议迁移到 secret reference。

### 9.8 Template Asset Handling

训练配置经常依赖外部模板和资源文件。训练流控制器必须把这些文件作为 artifact 处理。

首版需要支持：

```text
LAMMPS model deviation template
CP2K external_input_path
CP2K DFT-D3 parameter file reference
VASP INCAR/KPOINTS/POTCAR path references
ABACUS INPUT/KPT/STRU path references
custom wrapper command scripts
```

模板资产规则：

- 所有模板路径必须存在，除非用户显式选择 draft mode。
- 所有模板必须记录 sha256。
- 所有模板必须记录 backend、stage 和 consumer，例如 `dpgen.model_devi.lammps` 或 `dpgen.fp.cp2k`。
- 不复制大文件进 LLM 上下文。
- 对 wrapper command 只记录 command string、resolved executable、hashable script path 和资源摘要。
- 对 CP2K `external_input_path` 必须校验引用路径和实际文件名一致。
- 对 LAMMPS `rev_mat` 必须校验变量名和模板占位符一致。

### 9.9 `validate_training_inputs`

输入：

```text
param_json_path
machine_json_path
```

校验：

- JSON/YAML 格式。
- DP-GEN `run_jdata_arginfo` schema。
- DP-GEN `run_mdata_arginfo` schema。
- `type_map`、`mass_map` 基本一致性。
- `init_data_sys` 路径存在性。
- `init_batch_size` 数量是否与 `init_data_sys` 匹配。
- `sys_configs` 二维结构和路径存在性。
- `sys_batch_size` 数量是否与 `sys_configs` 匹配。
- `model_devi_jobs[*].sys_idx` 是否越界。
- `model_devi_jobs[*].template` 文件是否存在。
- `model_devi_jobs[*].rev_mat` 变量是否能在对应模板中找到。
- `fp_style` 对应必要字段是否存在。
- `external_input_path`、INCAR、POTCAR、KPT、basis、potential、DFT-D3 等 backend asset path 是否存在。
- `machine.json` 是否包含当前 DP-GEN schema 的 `train`、`model_devi`、`fp` 顶层对象。
- `api_version` 是否建议为 `1.0` 或以上；不兼容旧 DPDispatcher key layout 或 list-of-dicts stage layout，只给出迁移建议。
- `machine.json` 是否包含明文 secret。
- `remote_root` 是否按 train/model_devi/fp 分离或显式复用。
- shell wrapper command 是否存在不可审计风险，例如未记录脚本路径或依赖未知环境。

输出：

```text
runs/<run_id>/training_input_validation.json
runs/<run_id>/training_input_validation.md
```

### 9.10 `start_training_run`

输入：

```text
project_path
param_json_path
machine_json_path
```

行为：

- 在 `project_path` 下启动 `dpgen run param.json machine.json`。
- 以后台进程方式运行。
- 记录 PID、命令、cwd、环境摘要、param hash、machine hash。
- 写入 controller state。
- 返回 run id 和日志路径。

产物：

```text
runs/<run_id>/training_controller_state.json
runs/<run_id>/manifest.json
runs/<run_id>/logs/dpgen.stdout.log
runs/<run_id>/logs/dpgen.stderr.log
```

实现状态：

- `start_training_run` / `stop_training_run` 会写入或更新 `runs/<run_id>/manifest.json`。
- manifest 记录 param/machine hash、controller state、log artifacts、operation events、runtime decision 引用。

审批：

- MCP 工具本身不接收 approval 参数。
- 通过 MLP Copilot agent 调用时必须由 runtime ApprovalManager 审批。
- 审批请求应包含 command、cwd、param hash、machine hash 和资源摘要。

### 9.11 `stop_training_run`

输入：

```text
run_id
```

行为：

- 第一版只停止本地 training controller process。
- 不默认取消已经提交到 Slurm/PBS/SSH 的远程任务。
- 如果检测到远程任务可能仍在运行，返回 warning 和后续建议。

审批：

- MCP 工具本身不接收 approval 参数。
- 通过 MLP Copilot agent 调用时必须由 runtime ApprovalManager 审批。

后续可扩展：

```text
cancel_remote_jobs(run_id, scheduler, job_ids)
```

该工具必须单独审批。

### 9.12 `reset_training_run`

输入：

```text
project_path
target_iteration
target_stage
mode
```

`mode`：

| Mode | 行为 |
|---|---|
| `soft` | 备份并改写 `record.dpgen`，让 DP-GEN 从指定 iteration/stage 继续 |
| `hard` | 备份并移除目标之后的 `iter.*` 目录，再改写 `record.dpgen` |

要求：

- 必须先备份。
- 必须生成 reset plan。
- 通过 MLP Copilot agent 调用时必须由 runtime ApprovalManager 审批。
- 不默认删除远程任务目录。

产物：

```text
runs/<run_id>/training_reset_plan.json
runs/<run_id>/training_reset_report.md
backups/dpgen_reset_<timestamp>/
```

### 9.13 `get_training_status`

输入：

```text
project_path
```

读取：

- `record.dpgen` 最后一行。
- `dpgen.log` 最后若干行。
- `iter.??????` 目录。
- 当前 iteration 的 `00.train`、`01.model_devi`、`02.fp`。
- `candidate*.out`、`rest_failed*.out`、`rest_accurate*.out`。
- `02.fp/task.*`、`OUTCAR`、`vasprun.xml`、`data.*`。

输出：

```json
{
  "status": "success",
  "summary": "DP-GEN is at iter.000003 stage 4 run_model_devi.",
  "metrics": {
    "current_iteration": 3,
    "current_stage": 4,
    "stage_name": "run_model_devi",
    "iterations_found": 4,
    "candidate_frames": 120,
    "failed_frames": 18,
    "accurate_frames": 850,
    "fp_tasks": 64
  },
  "artifacts": [
    {
      "type": "status",
      "path": "runs/run_x/training_status.json",
      "sha256": "..."
    }
  ],
  "warnings": [],
  "errors": []
}
```

### 9.14 `analyze_training_failure`

输入：

```text
project_path
```

读取候选日志：

```text
dpgen.log
record.dpgen
iter.*/00.train/*/train.log
iter.*/01.model_devi/task.*/model_devi.out
iter.*/02.fp/task.*/OUTCAR
iter.*/02.fp/task.*/vasprun.xml
iter.*/02.fp/task.*/err
iter.*/02.fp/task.*/log
```

首版规则库：

| 错误模式 | 诊断方向 |
|---|---|
| `Command not found` | 环境未激活、软件未安装、machine command 错误 |
| `JSONDecodeError` | JSON 语法错误 |
| `ArgumentKeyError` | DP-GEN strict schema 不接受旧字段或未知字段 |
| `ArgumentTypeError` | 字段类型错误 |
| `FileNotFoundError ... graph.xxx.pb` | 训练未产出模型，检查初始数据和 train log |
| `cannot find valid data system` | `init_data_sys` 或数据路径错误 |
| `job failed 3 times` | DPDispatcher 远程任务失败，检查 remote_root 和 `.sub` 脚本 |
| `too many unsuccessfully terminated jobs` | FP 失败比例过高，检查输入或调高 `ratio_failure` |
| `OUTCAR not convergence` | 第一性原理任务未收敛 |
| `batch_size` / `numb_test` | 数据帧数不足或 `fp_task_min` 太小 |
| `sys_idx` 越界 | `model_devi_jobs[*].sys_idx` 与 `sys_configs` 不匹配 |

输出：

```json
{
  "failure_type": "dpdispatcher_job_failed",
  "evidence": [
    "RuntimeError: job failed 3 times",
    "remote_root=/path/to/remote"
  ],
  "likely_causes": [
    "remote environment missing executable",
    "input file invalid",
    "scheduler resource mismatch"
  ],
  "recommended_actions": [
    "check train.log under remote_root",
    "verify source_list in machine.json",
    "manually run generated .sub script"
  ]
}
```

规则：

- 日志全文不进入 LLM 上下文。
- 输出必须包含证据片段和对应路径。
- 建议必须可执行。
- 如果不能判断，返回 unknown，并列出下一步应检查的 artifact。

### 9.15 Training Run Report

`build_training_run_report` 生成：

```text
runs/<run_id>/training_run_report.md
runs/<run_id>/training_status.json
runs/<run_id>/training_iteration_metrics.json
runs/<run_id>/manifest.json
```

报告章节：

1. Project summary。
2. Param and machine hash。
3. Current status。
4. Iteration timeline。
5. Train stage summary。
6. Model deviation summary。
7. FP labeling summary。
8. Failure or warning summary。
9. Approval and action history。
10. Recommended next operational actions。

报告不能声明 checkpoint 可靠性。checkpoint 可靠性由 `mlp_model_eval_mcp` 负责。

## 10. `mlp-active-learning` Skill

首个必须实现的 skill：`mlp-active-learning`。

### 10.1 目标

指导用户把 MLP 训练目标转化为 主动学习配置和执行计划。

### 10.2 Skill 职责

Skill 负责：

- 询问目标体系、元素、相态、温压范围、目标应用。
- 询问已有初始数据、结构来源、计算资源和 FP 后端。
- 帮助用户选择主动学习策略。
- 调用 `generate_training_param`。
- 调用 `generate_training_machine`。
- 调用 `validate_training_inputs`。
- 请求用户审批后再启动 `start_training_run`。
- 根据 `get_training_status` 和 `analyze_training_failure` 解释当前状态和下一步。

Skill 不负责：

- 直接执行 DP-GEN。
- 直接生成科学指标。
- 直接判断模型 ready。
- 修改 runtime internals。

### 10.3 建议流程

```text
1. 收集体系和目标。
2. 收集已有数据和探索结构。
3. 收集计算资源和 FP 后端。
4. 生成 system_profile.json。
5. 生成 strategy_config.json。
6. 调用 generate_training_param。
7. 调用 generate_training_machine。
8. 调用 validate_training_inputs。
9. 展示风险和资源摘要。
10. 请求审批。
11. 调用 start_training_run。
12. 周期性调用 get_training_status。
13. 失败时调用 analyze_training_failure。
14. 生成 training_run_report。
```

## 11. Dataset Validation MCP

已实现首版：`mlp_dataset_mcp`。

当前范围是 lightweight 文件级 dataset MCP：`inspect_dataset`、`validate_dataset_schema`、`validate_dataset_integrity`、`build_dataset_validation_report`。OOD 测试先由 `mlp-ood-test-advisor` skill 给出项目化建议；固定 OOD/gap audit 工具暂不作为当前默认能力。

低优先级 backlog：unit、structure sanity、duplicate、split leakage、label consistency、coverage 等重检查暂缓，不作为当前版本验收项。

### 11.1 目标

当前目标是检查 MLP 数据集的文件布局、schema、基础完整性、hash 和报告 artifact。重科学检查只保留为 backlog。

### 11.2 工具列表

当前工具：

```text
inspect_dataset(dataset_path)
validate_dataset_schema(dataset_path, schema_path)
validate_dataset_integrity(dataset_path)
build_dataset_validation_report(dataset_path, output_path, max_files)
```

低优先级 backlog：

```text
check_unit_consistency(dataset_path)
check_structure_sanity(dataset_path)
detect_duplicate_or_near_duplicate_structures(dataset_path)
detect_split_leakage(dataset_path, split_config_path)
validate_split_strategy(dataset_path, split_config_path, target_use_case)
validate_label_consistency(dataset_path, reference_config_path)
detect_label_outliers(dataset_path)
dataset_coverage_report(dataset_path, target_domain_path)
```

Dataset validation 不负责启动 DP-GEN，也不声明 checkpoint 可用。

### 11.3 OOD Test Advisory

当前 OOD 能力先作为 skill，而不是固定 dataset MCP 工具。原因是化学体系、相空间、部署边界和 reference budget 差异很大，单一 OOD/gap checklist 容易制造虚假的安全感。

Skill：

```text
mlp-ood-test-advisor
```

输入语义：

- `dataset_path`：训练/验证 dataset 根目录或 manifest。
- `target_use_case`：目标应用域、composition/phase/temperature/pressure/strain/ensemble 边界。
- `suspected_ood_sources`：reviewer 指出的挑战构型、finite cluster、surface/interface、failed DP-GEN cluster、production failure 等。
- `checkpoint_path`、`model_eval_report_path`、`dataset_report_path`：已有证据 artifact。
- `reference_budget`：可承受的 DFT/ab initio 标注数量、HPC/GPU 限制和 walltime。

输出：

- 项目化 OOD 测试切片建议。
- 每个切片需要的输入路径、reference calculation、checkpoint evaluation、artifact 和 approval gate。
- 缺失证据和剩余风险。
- 如果用户明确需要可引用 evidence artifact，再按该项目定义后续 MCP 工具或手工 artifact 格式。

边界：

- 不声称完成局域环境覆盖分析。
- 不生成 descriptor matrix，不把大坐标载入 LLM 上下文。
- 不用 LLM 判断“已充分覆盖”；结论只能是 evidence present/missing/insufficient。
- 如果后续需要局域环境覆盖、候选结构排序或 descriptor-based gap analysis，再提升 `mlp_coverage_mcp`。

## 12. Model Evaluation MCP

第三阶段实现：`mlp_model_eval_mcp`。

当前已实现 checkpoint metadata、预计算 metrics artifact 处理、基于 DeePMD-kit v3 `dp test` 的 benchmark 执行入口，以及基于 ASE + DeePMD-kit v3 `deepmd.calculator.DP` 的单结构/批量预测入口：`inspect_checkpoint`、`run_deepmd_test`、`predict_energy_force`、`batch_predict`、`validate_checkpoint_on_dataset`、`compare_checkpoints`、`build_checkpoint_metrics`、`build_benchmark_plots`、`build_checkpoint_benchmark_report`。metrics 必须来自已有 artifact、`dp test` 执行结果或 ASE/DeepMD 预测结果，工具负责 hash、日志、detail 文件、归一化、阈值检查、对比摘要、PNG 图表 artifact 和 Markdown benchmark report。已补 `mlp-checkpoint-evaluation` skill 约束 agent 只基于证据 artifact 陈述模型质量。

目标：

- 对 DeepMD checkpoint 在独立 benchmark set 上进行评估。
- 生成能量、力、应力等误差指标。
- 对比多个 checkpoint。
- 输出 artifact 和 manifest。

工具：

```text
inspect_checkpoint(checkpoint_path)
run_deepmd_test(checkpoint_path, dataset_path, data_source, dp_command, backend, ...)
predict_energy_force(structure_path, checkpoint_path)
batch_predict(structure_dir, checkpoint_path)
validate_checkpoint_on_dataset(checkpoint_path, dataset_path, metric_config_path)
compare_checkpoints(checkpoint_a, checkpoint_b, dataset_path, metric_config_path)
build_checkpoint_metrics(run_id)
build_benchmark_plots(metrics_path, detail_prefix, output_dir)
build_checkpoint_benchmark_report(metrics_path, checkpoint_path, dataset_path)
```

要求：

- checkpoint 必须记录 hash。
- dataset 必须记录 hash。
- metrics 必须来自工具执行结果。
- 不由 LLM 判断模型 ready。

## 13. Coverage MCP

低优先级 backlog：`mlp_coverage_mcp`。

当前暂不实现。OOD 测试当前由 `mlp-ood-test-advisor` 提供项目化建议，不等价于完整 coverage MCP。该模块只有在用户明确需要 descriptor-based 覆盖分析、候选结构排序或局域环境缺口证据时再重新提升优先级。

目标：

- 分析当前数据库覆盖情况。
- 识别是否缺少特定构型类型。
- 分析局域原子环境覆盖。
- 为后续 DP-GEN 探索策略提供证据。

工具草案：

```text
build_structure_descriptors(dataset_path, descriptor_config_path)
analyze_local_environment_coverage(dataset_path, target_domain_path)
find_coverage_gaps(dataset_path, target_domain_path)
rank_candidate_structures_for_labeling(candidate_pool_path, coverage_model_path)
build_coverage_report(dataset_path, target_domain_path)
```

要求：

- 覆盖指标必须来自工具 artifact。
- 不把大规模 descriptor matrix 放入 LLM 上下文。
- 不和 训练流控制器耦合。

## 14. Job MCP

低优先级 backlog：`mlp_job_mcp`。

当前暂不实现。已有 training controller 和 DPDispatcher 证据读取足够支撑本地 DP-GEN 工作流；独立 HPC 队列管理在需要真实 Slurm/PBS/LSF 运维闭环时再做。

目标：

- 查询 HPC 队列。
- 查询 Slurm/PBS/LSF job 状态。
- 映射 DP-GEN remote job 和本地 run。
- 支持取消远程任务。

要求：

- 取消任务必须审批。
- 不默认杀任务。
- 必须记录 scheduler、job id、command 和 decision id。

## 15. Report MCP

当前已实现轻量版 `mlp_report_mcp`：从 workspace 中已有 run manifest、artifact reference、approval pending/decision 记录和显式 artifact path 生成 Markdown evidence report。Report MCP 只汇总已有证据，不生成新的科学指标，也不声明模型 ready。固定的一键 `build_mlp_audit_report` 暂不作为当前默认目标；如具体项目需要，应先由 `mlp-ood-test-advisor` 定义证据输入和审稿问题，再决定是否新增项目化 report 工具。

当前目标：

- 汇总已存在的 training run、dataset validation、model evaluation 和 approval decisions。
- 生成 Markdown 报告。
- 所有结论必须引用 artifact。
- 可汇总已有 checkpoint、dataset、OOD 建议/证据 artifact 和 human decision；项目化一键 audit report 暂不作为当前验收阻塞项。

### 15.1 Project-Specific Audit Report Backlog

固定的一键 audit report 已降级为项目化 backlog。只有当某个项目已经明确需要的证据输入、OOD 切片、approval decision 和审稿问题时，才实现对应 report 工具。

可能的工具：

```text
build_mlp_audit_report(
  model_eval_report_path,
  checkpoint_path,
  dataset_report_path,
  ood_gap_audit_path,
  approval_id,
  approval_decision_path,
  output_dir,
  title
)
```

输入语义：

- `model_eval_report_path`：`mlp_model_eval_mcp` 生成的 benchmark report、metrics JSON 或 manifest。
- `checkpoint_path`：被审计模型/checkpoint 路径；必须记录 hash。
- `dataset_report_path`：`mlp_dataset_mcp` 生成的 dataset validation report，可为空但必须标记缺失。
- `ood_gap_audit_path`：项目化 OOD 建议、OOD evidence 或 gap evidence artifact，可为空但必须标记缺失；不假定存在固定通用工具。
- `approval_id`：workspace ApprovalManager 中的审批 ID；工具应解析对应 decision record。
- `approval_decision_path`：显式 approval decision JSON 路径；当 `approval_id` 不可解析时使用。
- `output_dir`：报告输出目录。
- `title`：报告标题，可选。

输出 artifact：

- `mlp_audit_report.md`：论文修订和人工审查可读的综合报告。
- `mlp_audit_summary.json`：机器可读摘要，包含输入 artifact、hash、metrics summary、approval state、missing evidence 和 warnings。

如果实现，报告必须包含：

- checkpoint 路径、hash、工具版本和评估时间。
- model-eval metrics 的来源 artifact，不重新计算或伪造指标。
- dataset validation evidence 和项目化 OOD/dataset-gap advice/evidence。
- approval decision：状态、审批人/来源、时间、理由、关联 tool call 或 artifact。
- missing evidence section：任何缺失输入都必须显式列出，不能静默跳过。
- conservative conclusion：只总结证据状态，不替用户做“模型可发表/可上线”的最终判断。

低优先级 backlog：

- HTML/PDF 输出。
- 完整 coverage analysis 纳入综合报告。
- 更复杂的跨 run 报告模板。

报告不能伪造未执行的指标。

## 16. Capability Discovery

MLP Copilot 不维护单独的 workspace capability 定义文件。MCP 和 skill 来源如下：

- 源码内置 MCP：从 `mlpcopilot/mcps/*/pyproject.toml` 自动发现，要求 `[project.scripts]` 中存在 MCP entrypoint。
- workspace MCP：由用户在 config 的 `tools.mcpServers` 中显式配置。
- 源码内置 skills：从 `mlpcopilot/skills/*/SKILL.md` 自动发现。
- workspace skills：从 active workspace 的 `skills/*/SKILL.md` 自动发现。
- 启用、禁用、allowlist 和 tool timeout 由 config 控制；默认值只在字段缺失时生效，不覆盖用户显式配置。

TUI/API 可以展示 runtime 当前发现和连接状态，但这些状态是运行时 read model，不是新的配置源。

config 示例：

```json
{
  "tools": {
    "mcpServers": {
      "trainingController": {
        "type": "stdio",
        "command": "uv",
        "args": [
          "--directory",
          "mlpcopilot/mcps/mlp_training_controller_mcp",
          "run",
          "mlp-training-controller-mcp"
        ],
        "toolTimeout": 600,
        "enabledTools": [
          "inspect_training_project",
          "validate_training_inputs",
          "get_training_status",
          "analyze_training_failure"
        ]
      }
    }
  }
}
```

## 17. Approval Policy

必须审批的工具：

```text
start_training_run
stop_training_run
reset_training_run
cancel_remote_jobs
overwrite_param
overwrite_machine
delete_iteration
hard_reset_run
submit_remote_jobs
```

可只读执行的工具：

```text
inspect_training_project
validate_training_inputs
get_training_status
list_training_iterations
inspect_training_iteration
collect_training_logs
analyze_training_failure
build_training_run_report
```

审批请求必须包含：

- action type。
- project path。
- command 或将修改的文件。
- param hash。
- machine hash。
- resource summary。
- expected artifacts。
- rollback or backup plan。

## 18. Artifact Rules

插件产物应写入 workspace：

```text
runs/<run_id>/
reports/
logs/
approvals/
```

training controller 产物：

```text
runs/<run_id>/training_param.json
runs/<run_id>/training_machine.json
runs/<run_id>/training_controller_state.json
runs/<run_id>/training_status.json
runs/<run_id>/training_iteration_metrics.json
runs/<run_id>/training_failure_analysis.md
runs/<run_id>/training_run_report.md
runs/<run_id>/manifest.json
logs/<run_id>/training.stdout.log
logs/<run_id>/training.stderr.log
```

规则：

- 重要 artifact 必须计算 SHA256。
- 重要输入必须记录 hash。
- run manifest 必须记录 tool、version、input、output、errors。
- 报告中的指标必须引用 artifact。

## 19. 实施顺序

### Phase 1: Training Controller Read-Only

1. 创建 `mlp_training_controller_mcp` 包。
2. 实现 MCP server skeleton。
3. 实现通用输出协议。
4. 实现 `inspect_training_project`。
5. 实现 `validate_training_inputs`。
6. 实现 `get_training_status`。
7. 实现 `list_training_iterations`。
8. 实现 `inspect_training_iteration`。
9. 实现 `collect_training_logs`。
10. 实现 `analyze_training_failure`。

### Phase 2: Training Backend Config Generation

1. 定义 `system_profile.json` schema。
2. 定义 `strategy_config.json` schema。
3. 定义 `machine_profile.json` schema。
4. 实现 `generate_training_param`。
5. 实现 `generate_training_machine`。
6. 生成配置报告。
7. 接入 `mlp-active-learning` skill。

### Phase 3: Training Execution Control

1. 已实现 `start_training_run`。
2. 已实现 controller state。
3. 已实现 stdout/stderr log capture。
4. 已实现 `stop_training_run`。
5. 已实现 `reset_training_run` soft mode。
6. 已实现 `reset_training_run` hard mode。
7. 已接入 runtime approval-gated tool policy。
8. 已实现 start/stop/reset/rewind execution evidence manifest。

### Phase 4: Dataset And Model Modules

1. 已实现 `mlp_dataset_mcp` 首版。
2. 已实现 `mlp-dataset-validation` skill 首版。
3. 已实现 `mlp-validation-planner` skill 首版。
4. 已实现 `mlp_model_eval_mcp` 首版。
5. 已实现 `mlp-checkpoint-evaluation` skill 首版。
6. 已实现基于 DeePMD-kit v3 `dp test` 的 checkpoint benchmark 执行入口。
7. 已实现基于 ASE 的 `predict_energy_force` 和 `batch_predict`。
8. 已实现 checkpoint benchmark report。
9. 已实现 benchmark parity/error PNG plot artifacts。

### Phase 5: OOD Advisory Additions

近期补齐一项面向论文修订和审稿回复的建议能力：

1. 新增 `mlp-ood-test-advisor` skill，按项目化目标体系、部署边界和 reference budget 建议 OOD 测试切片和 evidence artifact。
2. 更新相关 skills，使 agent 能先收集证据路径、识别缺口，再建议工具或人工步骤，不用 LLM 编造指标。

以下项保持 backlog，只有在用户明确需要时再提升优先级：

1. 完整 `mlp_coverage_mcp`。
2. Descriptor-based 局域环境覆盖分析。
3. 固定 OOD/gap audit 工具和 dataset 深度科学检查。
4. `mlp_job_mcp`。
5. 综合 MLP 训练与验证报告的 HTML/PDF 输出。

已完成：轻量版 `mlp_report_mcp`、checkpoint benchmark report 和 benchmark PNG plot artifacts。

## 20. 验收标准

### Training Controller Read-Only

- 可以识别 DP-GEN backend project。
- 可以解析 `record.dpgen`。
- 可以列出 iteration。
- 可以识别当前 stage。
- 可以从 `iter.*` 目录统计 train/model_devi/fp 基本状态。
- 可以分析常见 DP-GEN 错误并输出 artifact。

### Config Generation

- 可以从 system/strategy/machine profile 生成 backend-native JSON。
- 生成后通过 DP-GEN schema 校验。
- 输出 param/machine hash。
- 输出配置风险摘要。

### Execution Control

- 启动训练 run 前必须触发审批。
- stop/reset 必须触发审批。
- controller state 可恢复。
- 失败后可以通过日志分析给出下一步建议。

### Runtime Boundary

- 不修改 mlpcopilot core 科学逻辑。
- 不把训练 backend 逻辑写入 runtime。
- MCP/Skill 插件可独立升级。

## 21. 关键设计决定

- 训练流控制器是第一插件里程碑。
- 训练流控制器包 CLI/进程/文件状态，不重写 DP-GEN 或其他 backend 主循环。
- `record.dpgen` 是状态读取的主依据之一。
- `iter.??????` 目录结构是状态和 artifact 索引依据。
- 启动、停止、重置必须是 blocking approval workflow。
- 模型性能测试和覆盖分析不塞进 训练流控制器。
- 指标必须来自 MCP 工具 artifact，不来自 LLM 判断。
