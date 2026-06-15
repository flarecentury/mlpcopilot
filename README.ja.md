<h1 align="center">MLP Copilot</h1>

<p align="center">
  機械学習ポテンシャルワークフロー向けの垂直 agent runtime
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">中文</a> |
  <a href="./README.fr.md">Français</a> |
  <a href="./README.ja.md">日本語</a>
</p>

MLP Copilot は、機械学習ポテンシャル向けワークフローのための垂直 agent
runtime です。現在は DeepMD-kit / DP-GEN のアクティブラーニング運用を中心に、
workspace 初期化、設定確認、実行状態の投影、artifact 追跡、ログ確認、人間による
承認付きの制御操作を扱います。

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">
    <img src="./data/videos/Video1_mlp_ai_agents.gif" alt="MLP Copilot AI agent workflow demo" width="640">
  </a>
</p>

<p align="center">
  <a href="./data/videos/Video1_mlp_ai_agents.mp4">完全版 MP4 demo を見る</a>
</p>

## 提供機能

| 領域 | 機能 |
| --- | --- |
| Runtime host | Agent loop、session、memory、TUI、Telegram/API gateway、MCP client、workspace、approval、artifact index |
| MLP plugins | 初期データセット準備、DP-GEN 制御、dataset validation、model evaluation、report、ローカル文書検索 |
| トレーサビリティ | Run manifest、artifact hash、approval decision、tool log、state projection |
| 人間による制御 | 高コストまたは破壊的な操作に対するブロッキング承認 |

## シミュレーションデータと DigAuto

`data/` ディレクトリは、以前の
[`flarecentury/Auto-MLP`](https://github.com/flarecentury/Auto-MLP) プロジェクトから
MLP Copilot に移行されています。このディレクトリには、アルミニウムナノ粒子燃焼の
分子動力学トラジェクトリ [`data/MDtrajs/`](./data/MDtrajs/) と対応する可視化動画
[`data/videos/`](./data/videos/) が含まれ、複数温度の bare-metal および core-shell
系をカバーしています。

AI agent、trained machine learning potential (MLP) models、および DFT
energies/forces 付きの約 90,000 atomic configurations を含む comprehensive dataset
はすべて、Digital Automation for Scientific Discovery platform (DigAuto) で
ホストされています：[https://www.digauto.org](https://www.digauto.org)。

## 必要条件

- Git。
- Python 3.11 以上。
- 依存関係管理用の `uv`。

`uv` がない場合：

```bash
python -m pip install --user uv
```

## ソースからインストール

```bash
git clone https://github.com/flarecentury/mlpcopilot.git
cd mlpcopilot
uv sync --extra dev
```

SSH を使う場合：

```bash
git clone git@github.com:flarecentury/mlpcopilot.git
cd mlpcopilot
uv sync --extra dev
```

CLI を確認：

```bash
uv run mlpcopilot --help
uv run mlpcopilot mlp capabilities
```

## Agentic File Search 設定

同梱の `agentic-file-search` MCP package は独自の環境設定ファイルを使います。
[`mlpcopilot/mcps/agentic-file-search/.env.example`](./mlpcopilot/mcps/agentic-file-search/.env.example)
をテンプレートとして使うか、初期化スクリプトを実行してください：

```bash
cd mlpcopilot/mcps/agentic-file-search
scripts/init-skill.sh
```

知識ベースのルート `FS_EXPLORER_MCP_ROOT`、インデックス DB
`FS_EXPLORER_DB_PATH`、任意の OpenAI-compatible endpoint はここで設定します。
これらはメイン設定 `~/.mlpcopilot/config.json` とは別です。

## 初回起動

ローカル設定とデフォルト workspace を作成：

```bash
uv run mlpcopilot onboard
```

推奨モデル設定：OpenAI Codex provider にログインし、アカウントで利用できる
最新の Codex GPT model を使います。

```bash
uv run mlpcopilot provider login openai-codex
```

ログイン後、onboarding でモデルを設定するか、TUI から
`/model openai-codex/gpt-5.3-codex` で切り替えます。

デフォルト workspace：

```text
~/.mlpcopilot/workspace
```

workspace を直接初期化：

```bash
uv run mlpcopilot mlp init --workspace ~/.mlpcopilot/workspace
```

TUI ワークベンチを起動：

```bash
uv run mlpcopilot tui
```

TUI スナップショットを出力：

```bash
uv run mlpcopilot tui --once
```

明示的な config と workspace を使う：

```bash
uv run mlpcopilot tui \
  --config ~/.mlpcopilot/config.json \
  --workspace ~/.mlpcopilot/workspace
```

## 初期データから始める

DP-GEN や active learning に入る前に、`mlp-initial-dataset-preparation`
skill を使って初期データセット生成戦略を整理できます。この skill は構造選択、
AIMD/static DFT ラベリング計画、変換先フォーマット、検証チェック、DP-GEN
`init_data_sys` などの受け渡しパスを決める支援をします。

training や labeling job を実行する前に、自分の HPC 環境に合わせて
DeepMD-kit/DP、VASP、CP2K などの実行ファイルと依存関係を設定してください。
移植性と再現性のある実行環境には Apptainer を推奨します：
[`apptainer/apptainer`](https://github.com/apptainer/apptainer)。

## よく使うコマンド

```bash
uv run mlpcopilot mlp status
uv run mlpcopilot mlp capabilities
uv run mlpcopilot mlp approvals
uv run mlpcopilot mlp runs list
uv run mlpcopilot mlp runs show <run_id>
```

TUI、API、Telegram：

```bash
uv run mlpcopilot tui
uv run mlpcopilot serve
uv run mlpcopilot gateway
```

既存 checkout を更新：

```bash
git pull --ff-only
uv sync --extra dev
```

## プロジェクト文書

プロダクト動作または実装を変更する前に、以下を確認してください：

1. [`AGENTS.md`](./AGENTS.md)
2. [`PROJECT.md`](./PROJECT.md)
3. [`prd/MLPCOPILOT_RUNTIME_PRD.md`](./prd/MLPCOPILOT_RUNTIME_PRD.md)
4. [`prd/MLPCOPILOT_MCP_SKILL_PRD.md`](./prd/MLPCOPILOT_MCP_SKILL_PRD.md)
5. [`prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md`](./prd/MLPCOPILOT_TUI_CODEX_INTERACTION_PRD.md)

## 開発チェック

```bash
uv run --extra dev ruff check mlpcopilot tests
uv run --extra dev pytest -q
```

## ライセンスと謝辞

MLP Copilot は MIT License で配布されています。詳細は [`LICENSE`](./LICENSE) を参照してください。

MLP Copilot は以下のプロジェクトおよび製品の成果を基にしています：

- [`HKUDS/nanobot`](https://github.com/HKUDS/nanobot)：MIT license の general-purpose agent runtime。
- [`PromtEngineer/agentic-file-search`](https://github.com/PromtEngineer/agentic-file-search)：MIT license の document search project。`agentic-file-search` MCP package として適配されています。
- [OpenAI Codex](https://openai.com/codex)：developer workflow 向けの interaction design が、MLP Copilot の TUI、command entrypoints、tool-call visibility、人間による approval experience に影響しています。
