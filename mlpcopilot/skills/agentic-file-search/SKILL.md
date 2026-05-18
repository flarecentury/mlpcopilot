---
name: agentic-file-search
description: Use the configured agentic-file-search MCP tool to explore the local knowledge base.
always: true
---

# Agentic File Search

Use this skill when the user asks to inspect, search, read, summarize, or answer questions from the local knowledge base.

## Primary Tool

Call the MCP tool `mcp_agentic-file-search_agentic_explore`.

It exposes one argument:

- `task`: a focused natural-language request over the configured knowledge root.

The knowledge root, database path, model, and refresh policy are configured on the MCP server side. Do not search repository files, config files, or skill files just to discover how to call this tool.

## Usage Rules

- If the user explicitly says `agentic-file-search`, call `mcp_agentic-file-search_agentic_explore` directly.
- For status questions, use one focused call such as `check database status, list indexed files, and summarize staleness`.
- For broad knowledge-base questions, use one broad call first, then only make follow-up calls if the user asks for more detail.
- For a known file, include the file name or relative path in `task`; do not pass a filesystem root.
- For follow-ups, preserve the previous target and add the new intent. For example: `from test.txt, extract concrete natfrp installation steps`.
- For large files or scripts, ask for a summary or short cited excerpts unless the user explicitly requests full verbatim content.

## Examples

- User: `用agentic-file-search 看看数据库情况`
  - Tool: `mcp_agentic-file-search_agentic_explore(task="check database status, list knowledge-base files, indexed documents, and whether the index is stale")`
- User: `去知识库看看 natfrp 的信息`
  - Tool: `mcp_agentic-file-search_agentic_explore(task="find natfrp information in the knowledge base and summarize the relevant source files")`
- User: `具体安装步骤？`
  - Tool: `mcp_agentic-file-search_agentic_explore(task="from the previously identified natfrp source file, extract concrete installation steps, prerequisites, config files, service actions, and risks")`
