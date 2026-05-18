<p align="center">
  <strong>MLP Copilot</strong><br>
  機械学習ポテンシャルワークフロー向けの evidence-oriented agent runtime
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <a href="./README.zh-CN.md">中文</a> |
  <a href="./README.fr.md">Français</a> |
  <a href="./README.ja.md">日本語</a>
</p>

# MLP Copilot

MLP Copilot は、機械学習ポテンシャル向けワークフローのための垂直 agent
runtime です。現在は DeepMD-kit / DP-GEN のアクティブラーニング運用を中心に、
workspace 初期化、設定確認、実行状態の投影、artifact 追跡、ログ確認、人間による
承認付きの制御操作を扱います。

## 提供機能

| 領域 | 機能 |
| --- | --- |
| Runtime host | Agent loop、session、memory、TUI、Telegram/API gateway、MCP client、workspace、approval、artifact index |
| MLP plugins | DP-GEN 制御、dataset validation、model evaluation、report、ローカル文書検索 |
| Evidence model | Run manifest、artifact hash、approval decision、tool log、state projection |
| Human control | 高コストまたは破壊的な操作に対する blocking approval |

runtime はホスト層に限定します。科学アルゴリズム、DP-GEN セマンティクス、
checkpoint 推論、benchmark、dataset validation は core runtime ではなく
MCP server または skill に置きます。

## 必要条件

- `flarecentury/mlpcopilot` private repo にアクセスできる Git 環境。
- GitHub に登録済みの SSH key。
- Python 3.11 以上。
- 依存関係管理用の `uv`。

`uv` がない場合：

```bash
python -m pip install --user uv
```

SSH 接続を確認：

```bash
ssh -T git@github.com
```

## ソースからインストール

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

## 初回起動

ローカル設定とデフォルト workspace を作成：

```bash
uv run mlpcopilot onboard
```

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

## 既存 DP-GEN ディレクトリを使う

既存の DP-GEN 作業ディレクトリを MLP Copilot workspace に投影：

```bash
bash run_tui.sh --dpgen-dir /path/to/dpgen/workdir --no-tui
```

その後 TUI を起動：

```bash
uv run mlpcopilot tui --config ~/.mlpcopilot/config.json --session tui:local
```

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
