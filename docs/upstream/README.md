# Upstream Reference Docs

This directory keeps inherited general-purpose mlpcopilot documentation for
comparison and migration context. These documents are not MLP Copilot product
defaults unless the MLP PRDs or runtime configuration say so.

| Document | Purpose |
| --- | --- |
| [`chat-apps.md`](./chat-apps.md) | Multi-channel setup inherited from upstream |
| [`channel-plugin-guide.md`](./channel-plugin-guide.md) | Custom channel plugin guide |
| [`websocket.md`](./websocket.md) | WebSocket channel reference |
| [`my-tool.md`](./my-tool.md) | Inherited runtime self-inspection tool notes |

If an upstream behavior becomes part of MLP Copilot, document the MLP-specific
default in [`../reference/`](../reference/) or [`../runtime/`](../runtime/)
instead of relying on this directory.
