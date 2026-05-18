# MLP Copilot Documentation

This directory contains implementation-facing documentation for the current MLP
Copilot repository. Product requirements and boundary decisions remain in
[`../prd/`](../prd/); these docs explain how the current implementation is used,
operated, and maintained.

## Start Here

| Document | Purpose |
| --- | --- |
| [`../README.md`](../README.md) | Product entrypoint, quick start, and current status |
| [`../AGENTS.md`](../AGENTS.md) | Development rules for agent-assisted changes |
| [`../PROJECT.md`](../PROJECT.md) | Short project summary and source-of-truth list |
| [`../prd/README.md`](../prd/README.md) | PRD index and current priority notes |
| [`MAINTENANCE.md`](./MAINTENANCE.md) | Documentation placement, update, and review checklist |

## Directory Map

| Directory | Scope |
| --- | --- |
| [`design/`](./design/) | Architecture maps, workspace design, UI/read-model notes |
| [`runtime/`](./runtime/) | Runtime behavior notes that are broader than one command or API |
| [`reference/`](./reference/) | CLI, config, OpenAI-compatible API, Python SDK reference |
| [`operations/`](./operations/) | Deployment and multi-instance operation guides |
| [`upstream/`](./upstream/) | Inherited general-purpose docs kept for reference only |

## Current Docs

### Design

| Document | Purpose |
| --- | --- |
| [`design/architecture.md`](./design/architecture.md) | Current runtime/plugin architecture and code-navigation map |
| [`design/mlp-workspace-ui-design.md`](./design/mlp-workspace-ui-design.md) | Workspace, run, artifact, and UI read-model design |

### Runtime

| Document | Purpose |
| --- | --- |
| [`runtime/memory.md`](./runtime/memory.md) | Session memory and Dream consolidation behavior |

### Reference

| Document | Purpose |
| --- | --- |
| [`reference/configuration.md`](./reference/configuration.md) | Runtime profile, providers, tools, channels, MCP, security |
| [`reference/cli-reference.md`](./reference/cli-reference.md) | CLI and TUI slash command reference |
| [`reference/mcp-skill-index.md`](./reference/mcp-skill-index.md) | Current MCP server and skill inventory |
| [`reference/openai-api.md`](./reference/openai-api.md) | OpenAI-compatible API and approval endpoints |
| [`reference/python-sdk.md`](./reference/python-sdk.md) | Programmatic Python API |

### Operations

| Document | Purpose |
| --- | --- |
| [`operations/dpgen-active-learning-runbook.md`](./operations/dpgen-active-learning-runbook.md) | DP-GEN active-learning attach, inspect, operate, and rewind workflow |
| [`operations/deployment.md`](./operations/deployment.md) | Docker, service, and LaunchAgent deployment notes |
| [`operations/multiple-instances.md`](./operations/multiple-instances.md) | Separate configs and workspaces for multiple instances |
| [`operations/troubleshooting.md`](./operations/troubleshooting.md) | Common runtime, MCP, TUI, approval, and DP-GEN issues |
| [`operations/release-readiness-checklist.md`](./operations/release-readiness-checklist.md) | Release and handoff checklist for stable MLP work |

### Upstream Reference

Some general-purpose upstream docs are retained under [`upstream/`](./upstream/)
for comparison and migration context. They are not MLP Copilot product defaults.

| Document | Purpose |
| --- | --- |
| [`upstream/chat-apps.md`](./upstream/chat-apps.md) | Multi-channel setup inherited from upstream |
| [`upstream/channel-plugin-guide.md`](./upstream/channel-plugin-guide.md) | Custom channel plugin guide |
| [`upstream/websocket.md`](./upstream/websocket.md) | WebSocket channel reference |
| [`upstream/my-tool.md`](./upstream/my-tool.md) | Inherited runtime self-inspection tool notes |
