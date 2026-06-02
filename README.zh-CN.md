<h1 align="center">MLP Copilot</h1>

<p align="center">
  面向机器学习势能工作流的垂直 agent runtime
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">中文</a> |
  <a href="./README.fr.md">Français</a> |
  <a href="./README.ja.md">日本語</a>
</p>

MLP Copilot 是面向机器学习势能工作流的垂直 agent runtime。它聚焦
DeepMD-kit / DP-GEN 主动学习场景，强调 workspace 初始化、配置检查、运行状态投影、
artifact 跟踪、日志检查，以及需要人工审批的控制操作。

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">
    <img src="./data/videos/Video1_mlp_ai_agents.gif" alt="MLP Copilot AI agent workflow demo" width="640">
  </a>
</p>

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">查看完整 MP4 demo</a>
</p>

## 能力概览

| 模块 | 能力 |
| --- | --- |
| Runtime host | Agent loop、session、memory、TUI、Telegram/API、MCP client、workspace、approval、artifact index |
| MLP plugins | DP-GEN 控制、数据集验证、模型评估、报告、本地文档搜索 |
| 可追溯性 | Run manifest、artifact hash、approval decision、tool log、状态投影 |
| 人工控制 | 高成本或破坏性动作必须阻塞等待人工审批 |

运行时只做宿主层能力。数据集验证算法、checkpoint 推理、benchmark 和具体科学判断
应放在 MCP server 或 skill 中，而不是写进 core runtime。

## 仿真数据与 DigAuto

`data/` 目录已从早期的
[`flarecentury/Auto-MLP`](https://github.com/flarecentury/Auto-MLP) 项目迁移到
MLP Copilot。该目录包含铝纳米颗粒燃烧的分子动力学轨迹
[`data/MDtrajs/`](./data/MDtrajs/) 和对应可视化视频
[`data/videos/`](./data/videos/)，覆盖 bare-metal 与 core-shell 体系的多个温度。

AI agent、已训练的 machine learning potential (MLP) models，以及包含约 90,000 个
带 DFT energies/forces 的 atomic configurations 的 comprehensive dataset，均托管在
Digital Automation for Scientific Discovery 平台 DigAuto：
[https://www.digauto.org](https://www.digauto.org)。

## 安装要求

- Git。
- Python 3.11 或更高版本。
- `uv` 依赖管理工具。

如果还没有 `uv`：

```bash
python -m pip install --user uv
```

## 从源码安装

```bash
git clone https://github.com/flarecentury/mlpcopilot.git
cd mlpcopilot
uv sync --extra dev
```

如果你更习惯使用 SSH：

```bash
git clone git@github.com:flarecentury/mlpcopilot.git
cd mlpcopilot
uv sync --extra dev
```

验证命令行：

```bash
uv run mlpcopilot --help
uv run mlpcopilot mlp capabilities
```

## 第一次使用

初始化配置和默认 workspace：

```bash
uv run mlpcopilot onboard
```

默认 workspace：

```text
~/.mlpcopilot/workspace
```

也可以直接初始化 workspace：

```bash
uv run mlpcopilot mlp init --workspace ~/.mlpcopilot/workspace
```

打开本地 TUI 工作台：

```bash
uv run mlpcopilot tui
```

渲染一次 TUI 快照：

```bash
uv run mlpcopilot tui --once
```

指定配置和 workspace：

```bash
uv run mlpcopilot tui \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace
```

## 接入已有 DP-GEN 工作目录

将已有 DP-GEN 工作目录投影到 MLP Copilot workspace：

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

然后打开工作台：

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

## 常用命令

```bash
uv run mlpcopilot mlp status
uv run mlpcopilot mlp capabilities
uv run mlpcopilot mlp approvals
uv run mlpcopilot mlp runs list
uv run mlpcopilot mlp runs show <run_id>
```

TUI、API 和 Telegram：

```bash
uv run mlpcopilot tui
uv run mlpcopilot serve
uv run mlpcopilot gateway
```

更新已有 checkout：

```bash
git pull --ff-only
uv sync --extra dev
```

## 项目文档

修改产品行为或实现前，优先阅读：

1. [`AGENTS.md`](./AGENTS.md)
2. [`PROJECT.md`](./PROJECT.md)
3. [`prd/MLPCOPILOT_RUNTIME_PRD.md`](./prd/MLPCOPILOT_RUNTIME_PRD.md)
4. [`prd/MLPCOPILOT_MCP_SKILL_PRD.md`](./prd/MLPCOPILOT_MCP_SKILL_PRD.md)
5. [`prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`](./prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md)

## 开发检查

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

## 许可与致谢

MLP Copilot 使用 MIT License。见 [`LICENSE`](./LICENSE)。

MLP Copilot 借鉴并适配了以下项目和产品：

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot)，MIT 许可的通用 agent runtime。
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search)，MIT 许可的文档搜索项目，已适配为随包提供的 `agentic-file-search` MCP package。
- [OpenAI Codex](https://openai.com/codex)，其面向开发者工作流的交互设计影响了 MLP Copilot 的 TUI、命令入口、工具调用可见性和人工审批体验。
