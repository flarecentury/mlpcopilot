# Agentic File Search

This copy is the package-level `agentic-file-search` MCP project used by the
MLP Copilot `agentic-file-search` skill. The skill prompt lives separately at
`../../skills/agentic-file-search/SKILL.md`.

This directory is a standalone `uv` project and can be run directly as a
single-tool MCP server.

Quick initialization from this project directory:

```bash
scripts/init-skill.sh
```

Start stdio MCP:

```bash
scripts/start-mcp-stdio.sh
```

Direct stdio command:

```bash
uv --directory . run agentic-file-search-mcp
```

Start Streamable HTTP MCP:

```bash
scripts/start-mcp-http.sh
```

> **Based on**: [run-llama/fs-explorer](https://github.com/run-llama/fs-explorer) — The original CLI agent for filesystem exploration.

An AI-powered document search agent that explores files like a human would — scanning, reasoning, and following cross-references. Unlike traditional RAG systems that rely on pre-computed embeddings, this agent dynamically navigates documents to find answers.

## Why Agentic Search?

Traditional RAG (Retrieval-Augmented Generation) has limitations:
- **Chunks lose context** — Splitting documents destroys relationships between sections
- **Cross-references are invisible** — "See Exhibit B" means nothing to embeddings
- **Similarity ≠ Relevance** — Semantic matching misses logical connections

This system uses a **three-phase strategy**:
1. **Parallel Scan** — Preview all documents in a folder at once
2. **Deep Dive** — Full extraction on relevant documents only
3. **Backtrack** — Follow cross-references to previously skipped documents

## Watch the video
This video explains the architecture of the project and how to run it. 
[![Watch the demo on YouTube](https://img.youtube.com/vi/rMADSuus6jg/maxresdefault.jpg)](https://www.youtube.com/watch?v=rMADSuus6jg)

## Features

- 🔍 **6 Tools**: `scan_folder`, `preview_file`, `parse_file`, `read`, `grep`, `glob`
- 📄 **Document Support**: PDF, DOCX, PPTX, XLSX, HTML, Markdown (via Docling)
- 🤖 **Powered by**: Google Gemini 3 Flash with structured JSON output
- 💰 **Cost Efficient**: ~$0.001 per query with token tracking
- 🌐 **Web UI**: Real-time WebSocket streaming interface
- 📊 **Citations**: Answers include source references

## Installation

```bash
# Clone the repository
git clone https://github.com/PromtEngineer/agentic-file-search.git
cd agentic-file-search

# Install with uv (recommended)
uv pip install .

# Or with pip
pip install .
```

## Configuration

Create a `.env` file in the project root:

```bash
GOOGLE_API_KEY=your_api_key_here
```

Get your API key from [Google AI Studio](https://aistudio.google.com/apikey).

## Usage

### CLI

```bash
# Basic query
uv run explore --task "What is the purchase price in data/test_acquisition/?"

# Multi-document query
uv run explore --task "Look in data/large_acquisition/. What are all the financial terms including adjustments and escrow?"
```

### Web UI

```bash
# Start the server
uv run uvicorn fs_explorer.server:app --host 127.0.0.1 --port 8000

# Open http://127.0.0.1:8000 in your browser
```

The web UI provides:
- Folder browser to select target directory
- Real-time step-by-step execution log
- Final answer with citations
- Token usage and cost statistics



### MCP Server

FsExplorer can run as a local MCP server over stdio or Streamable HTTP
using FastMCP. The default MCP entry point exposes exactly one tool,
`agentic_explore`; model, path, DB, and policy settings live in `.env`.

```bash
uv run agentic-file-search-mcp
```

Streamable HTTP mode:

```bash
uv run agentic-file-search-mcp --transport streamable-http --host 127.0.0.1 --port 8765 --path /mcp
```

Equivalent shortcut:

```bash
uv run agentic-file-search-mcp-http --host 127.0.0.1 --port 8765 --path /mcp
```

Example MCP client configuration:

```json
{
  "mcpServers": {
    "agentic-file-search": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/agentic-file-search",
        "run",
        "agentic-file-search-mcp"
      ],
      "env": {
        "FS_EXPLORER_MCP_ROOT": "/absolute/path/to/documents",
        "FS_EXPLORER_DB_PATH": "/absolute/path/to/fs-explorer.duckdb",
        "FS_EXPLORER_OPENAI_COMPAT_BASE_URL": "http://127.0.0.1:8000/v1",
        "FS_EXPLORER_OPENAI_COMPAT_MODEL": "local-model"
      }
    }
  }
}
```

MCP tool:

- `agentic_explore(task)` - ask a focused question over `FS_EXPLORER_MCP_ROOT`.
  The root is configured in the server environment and is not exposed as a tool
  argument, so put file names or relative paths in `task`. Task wording affects
  behavior: broad questions produce overviews, `read <path>` produces a file
  summary, and follow-up calls can ask for specific steps, risks, variables,
  commands, or short excerpts from the same file or folder. For follow-ups, keep
  the previous target and the new user intent in `task`; for example use
  `from test.txt, extract concrete natfrp installation steps` instead of merely
  `read test.txt`.

Runtime environment variables:

- `FS_EXPLORER_MCP_ROOT` restricts which local paths the MCP server can read.
- `FS_EXPLORER_OPENAI_COMPAT_BASE_URL`, `FS_EXPLORER_OPENAI_COMPAT_MODEL`, and optional
  `FS_EXPLORER_OPENAI_COMPAT_API_KEY` configure the OpenAI-compatible local model.
  The older `FS_EXPLORER_AGENT_*` names are still accepted as fallback.
- `FS_EXPLORER_AGENT_USE_INDEX` lets the internal agent use an existing index.
- `FS_EXPLORER_MCP_AUTO_REFRESH_INDEX` controls deterministic server-side index
  freshness checks when `FS_EXPLORER_AGENT_USE_INDEX=1` and indexing is allowed.
  It defaults to enabled; if the DB is missing or stale, the MCP server refreshes
  the index before invoking the model.
- `FS_EXPLORER_EXTRA_INDEXABLE_EXTENSIONS` adds plain-text extensions to the
  indexer whitelist. Use comma, semicolon, or whitespace separators; leading dots
  are optional, for example `vasp,poscar,.slurm`.
- `FS_EXPLORER_AGENT_TIMEOUT` controls the OpenAI-compatible request timeout;
  default is 120 seconds.
- `FS_EXPLORER_MCP_ALLOW_INDEXING`, `FS_EXPLORER_MCP_ALLOW_EMBEDDINGS`, and
  `FS_EXPLORER_MCP_ALLOW_METADATA` control which internal actions are allowed.

For large documents or scripts, `agentic_explore` asks the model to summarize the
content and cite paths instead of echoing the entire file back into the MCP result.

The OpenAI-compatible agent loop lives in `src/fs_explorer/openai_compatible_file_agent.py`.
The previous broad MCP server, including individual file/index tools, is
preserved in `src/fs_explorer/mcp_server_full.py` for reference.

For Streamable HTTP clients, use:

```text
http://127.0.0.1:8765/mcp
```

The HTTP transport defaults to localhost binding. Keep it on `127.0.0.1`
unless you are intentionally exposing the MCP server to another machine.

## Architecture

```
User Query
    ↓
┌─────────────────┐
│ Workflow Engine │ ←→ LlamaIndex Workflows (event-driven)
└────────┬────────┘
         ↓
┌─────────────────┐
│     Agent       │ ←→ Gemini 3 Flash (structured JSON)
└────────┬────────┘
         ↓
┌─────────────────────────────────────────┐
│ scan_folder │ preview │ parse │ read │ grep │ glob │
└─────────────────────────────────────────┘
                    ↓
              Document Parser (Docling - local)
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams.

## Test Documents

The repo includes test document sets for evaluation:

- `data/test_acquisition/` — 10 interconnected legal documents
- `data/large_acquisition/` — 25 documents with extensive cross-references

Example queries:
```bash
# Simple (single doc)
uv run explore --task "Look in data/test_acquisition/. Who is the CTO?"

# Cross-reference required
uv run explore --task "Look in data/test_acquisition/. What is the adjusted purchase price?"

# Multi-document synthesis
uv run explore --task "Look in data/large_acquisition/. What happens to employees after the acquisition?"
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| LLM | Google Gemini 3 Flash |
| Document Parsing | Docling (local, open-source) |
| Orchestration | LlamaIndex Workflows |
| CLI | Typer + Rich |
| Web Server | FastAPI + WebSocket |
| Package Manager | uv |

## Project Structure

```
src/fs_explorer/
├── agent.py      # Gemini client, token tracking
├── workflow.py   # LlamaIndex workflow engine
├── fs.py         # File tools: scan, parse, grep
├── models.py     # Pydantic models for actions
├── main.py       # CLI entry point
├── server.py     # FastAPI + WebSocket server
└── ui.html       # Single-file web interface
```

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## License

MIT

## Acknowledgments

- Original concept from [run-llama/fs-explorer](https://github.com/run-llama/fs-explorer)
- Document parsing by [Docling](https://github.com/DS4SD/docling)
- Powered by [Google Gemini](https://deepmind.google/technologies/gemini/)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=PromtEngineer/agentic-file-search&type=Date)](https://star-history.com/#PromtEngineer/agentic-file-search&Date)
