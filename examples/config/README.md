# Configuration Examples

These examples are templates for `~/.mlpcopilot/config.json` or for a config
path passed with `mlpcopilot tui -c`.

- `mlpcopilot-minimal.example.json` is the smallest practical MLP Copilot
  runtime profile setup with an OpenAI-compatible custom provider.
- `mlpcopilot-local-mcp.example.json` is based on a local development
  `~/.mlpcopilot/config.json` and keeps the MLP runtime profile, TUI keymap,
  approval policy, tool policy, and source-tree MCP server wiring. Secrets,
  private endpoints, and machine-specific paths are replaced with placeholders.
- `mlpcopilot-exec-opt-in.example.json` shows the explicit settings required to
  enable the `exec` tool under the `mlpcopilot` profile.

Values written as `${VAR_NAME}` are resolved from environment variables at
runtime. Set those variables before starting MLP Copilot, or replace the values
with local paths and credentials outside version control.

The `mlpcopilot` profile applies defaults only when fields are absent. Explicit
allowlists and enabled lists in these examples are preserved exactly by the
runtime, so edit them intentionally for your deployment.
