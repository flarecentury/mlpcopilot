# Multiple Instances

Run multiple mlpcopilot instances simultaneously with separate configs and runtime data. Use `--config` as the main entrypoint. Optionally pass `--workspace` during `onboard` when you want to initialize or update the saved workspace for a specific instance.

## Quick Start

If you want each instance to have its own dedicated workspace from the start, pass both `--config` and `--workspace` during onboarding.

**Initialize instances:**

```bash
# Create separate instance configs and workspaces
mlpcopilot onboard --config ~/.mlpcopilot-telegram/config.json --workspace ~/.mlpcopilot-telegram/workspace
mlpcopilot onboard --config ~/.mlpcopilot-discord/config.json --workspace ~/.mlpcopilot-discord/workspace
mlpcopilot onboard --config ~/.mlpcopilot-feishu/config.json --workspace ~/.mlpcopilot-feishu/workspace
```

**Configure each instance:**

Edit `~/.mlpcopilot-telegram/config.json`, `~/.mlpcopilot-discord/config.json`, etc. with different channel settings. The workspace you passed during `onboard` is saved into each config as that instance's default workspace.

**Run instances:**

```bash
# Instance A - Telegram bot
mlpcopilot gateway --config ~/.mlpcopilot-telegram/config.json

# Instance B - Discord bot
mlpcopilot gateway --config ~/.mlpcopilot-discord/config.json

# Instance C - Feishu bot with custom port
mlpcopilot gateway --config ~/.mlpcopilot-feishu/config.json --port 18792
```

## Path Resolution

When using `--config`, mlpcopilot derives its runtime data directory from the config file location. The workspace still comes from `agents.defaults.workspace` unless you override it with `--workspace`.

To open a CLI session against one of these instances locally:

```bash
mlpcopilot agent -c ~/.mlpcopilot-telegram/config.json -m "Hello from Telegram instance"
mlpcopilot agent -c ~/.mlpcopilot-discord/config.json -m "Hello from Discord instance"

# Optional one-off workspace override
mlpcopilot agent -c ~/.mlpcopilot-telegram/config.json -w /tmp/mlpcopilot-telegram-test
```

> `mlpcopilot agent` starts a local CLI agent using the selected workspace/config. It does not attach to or proxy through an already running `mlpcopilot gateway` process.

| Component | Resolved From | Example |
|-----------|---------------|---------|
| **Config** | `--config` path | `~/.mlpcopilot-A/config.json` |
| **Workspace** | `--workspace` or config | `~/.mlpcopilot-A/workspace/` |
| **Cron Jobs** | config directory | `~/.mlpcopilot-A/cron/` |
| **Media / runtime state** | config directory | `~/.mlpcopilot-A/media/` |

## How It Works

- `--config` selects which config file to load
- By default, the workspace comes from `agents.defaults.workspace` in that config
- If you pass `--workspace`, it overrides the workspace from the config file

## Minimal Setup

1. Copy your base config into a new instance directory.
2. Set a different `agents.defaults.workspace` for that instance.
3. Start the instance with `--config`.

Example config:

```json
{
  "agents": {
    "defaults": {
      "workspace": "~/.mlpcopilot-telegram/workspace",
      "model": "anthropic/claude-sonnet-4-6"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_TELEGRAM_BOT_TOKEN"
    }
  },
  "gateway": {
    "host": "127.0.0.1",
    "port": 18790
  }
}
```

Start separate instances:

```bash
mlpcopilot gateway --config ~/.mlpcopilot-telegram/config.json
mlpcopilot gateway --config ~/.mlpcopilot-discord/config.json
```

Each gateway instance also exposes a lightweight HTTP health endpoint on
`gateway.host:gateway.port`. By default, the gateway binds to `127.0.0.1`,
so the endpoint stays local unless you explicitly set `gateway.host` to a
public or LAN-facing address.

- `GET /health` returns `{"status":"ok"}`
- Other paths return `404`

Override workspace for one-off runs when needed:

```bash
mlpcopilot gateway --config ~/.mlpcopilot-telegram/config.json --workspace /tmp/mlpcopilot-telegram-test
```

## Common Use Cases

- Run separate bots for Telegram, Discord, Feishu, and other platforms
- Keep testing and production instances isolated
- Use different models or providers for different teams
- Serve multiple tenants with separate configs and runtime data

## Notes

- Each instance must use a different port if they run at the same time
- Use a different workspace per instance if you want isolated memory, sessions, and skills
- `--workspace` overrides the workspace defined in the config file
- Cron jobs and runtime media/state are derived from the config directory
