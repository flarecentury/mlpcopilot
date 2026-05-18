# MLP Copilot PRD 索引

本目录保存 MLP Copilot 当前产品需求文档。

## 当前文档

- `MLPCOPILOT_RUNTIME_PRD.md`：host runtime。覆盖 profile、workspace、approval、artifact index、API、Telegram、TUI host 行为、MCP/skill 加载和 tool policy。
- `MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`：TUI interaction layer。覆盖 slash commands、overlays、layouts、jobs、tool log、approvals、keymap 和 persistence。
- `MLPCOPILOT_MCP_SKILL_PRD.md`：plugin layer。覆盖 MLP MCP servers 和 MLP skills。
- `MLPCOPILOT_CONTEXT_MEMORY_PRD.md`：context 和 memory layer。覆盖常驻规则、长期记忆、session goal/plan、active project/run pointer、DP-GEN 实时状态与 MCP source-of-truth 边界。
- `RUNTIME_COMPLETION_NOTES.md`：runtime MVP 的实现状态和验证记录。

## 当前优先级

截至 2026-05-09，近期工作聚焦在稳定已落地能力：

1. Runtime 和 TUI 回归修复。
2. `mlp_training_controller_mcp` 面向真实 DP-GEN 项目继续硬化。
3. 维护已有 `mlp_dataset_mcp`、`mlp_model_eval_mcp`、`mlp_report_mcp`。
4. 维护已有 skill pack 和文档。
5. OOD 测试建议：维护 `mlp-ood-test-advisor`，按具体化学体系、部署边界、已有 evidence 和 reference budget 给出项目化测试切片建议。

## MCP 组织原则

不要为了“统一”把所有 MLP 工具塞进一个 MCP server。近期保持按职责拆分的 MCP：training controller、dataset audit、model evaluation、report aggregation 分别维护。Runtime 负责统一发现、审批、日志、artifact index 和 TUI/API 展示；MCP server 负责各自的科学/工程工具。

审稿人通常关心的是证据是否可复现、输入输出是否有 hash、指标是否来自工具 artifact、人工决策是否可追踪，而不是所有工具是否运行在同一个 MCP 进程里。

## 暂缓 Backlog

以下事项已降为低优先级。除非明确重新提升优先级，否则不作为近期开发驱动项：

- `mlp_coverage_mcp`.
- 固定 OOD/gap audit 工具和 Dataset 深度科学检查：unit consistency、structure sanity、duplicate detection、split leakage、label consistency、label outliers、通用 coverage analysis。
- `mlp_job_mcp`，即完整远程 Slurm/PBS/LSF 管理。
- HTML/PDF report rendering。
- 手工终端 visual smoke 和真实部署 smoke，release 前再做。

## 边界规则

Runtime PRD 工作不能把科学算法引入 mlpcopilot core。科学逻辑必须留在 MCP servers 或 skills 中。
