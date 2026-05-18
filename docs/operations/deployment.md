# Deployment

## Docker

> [!TIP]
> The `-v ~/.mlpcopilot:/home/mlpcopilot/.mlpcopilot` flag mounts your local config directory into the container, so your config and workspace persist across container restarts.
> The container runs as the non-root user `mlpcopilot` (UID 1000) and reads config from `/home/mlpcopilot/.mlpcopilot`. Always mount your host config directory to `/home/mlpcopilot/.mlpcopilot`, not `/root/.mlpcopilot`.
> If you get **Permission denied**, fix ownership on the host first: `sudo chown -R 1000:1000 ~/.mlpcopilot`, or pass `--user $(id -u):$(id -g)` to match your host UID. Podman users can use `--userns=keep-id` instead.
>
> [!IMPORTANT]
> Official Docker usage currently means building from this repository with the included `Dockerfile`. Docker Hub images under third-party namespaces are not maintained or verified by flarecentury/mlpcopilot; do not mount API keys or bot tokens into them unless you trust the publisher.

### Docker Compose

```bash
docker compose run --rm mlpcopilot-cli onboard   # first-time setup
vim ~/.mlpcopilot/config.json                     # add API keys
docker compose up -d mlpcopilot-gateway           # start gateway
```

```bash
docker compose run --rm mlpcopilot-cli agent -m "Hello!"   # run CLI
docker compose logs -f mlpcopilot-gateway                   # view logs
docker compose down                                      # stop
```

### Docker

```bash
# Build the image
docker build -t mlpcopilot .

# Initialize config (first time only)
docker run -v ~/.mlpcopilot:/home/mlpcopilot/.mlpcopilot --rm mlpcopilot onboard

# Edit config on host to add API keys
vim ~/.mlpcopilot/config.json

# Run gateway (connects to enabled channels, e.g. Telegram/Discord/Mochat)
docker run -v ~/.mlpcopilot:/home/mlpcopilot/.mlpcopilot -p 18790:18790 mlpcopilot gateway

# Or run a single command
docker run -v ~/.mlpcopilot:/home/mlpcopilot/.mlpcopilot --rm mlpcopilot agent -m "Hello!"
docker run -v ~/.mlpcopilot:/home/mlpcopilot/.mlpcopilot --rm mlpcopilot status
```

## Public OpenAI-Compatible API

The API defaults to `127.0.0.1:8900`. For any public bind such as `0.0.0.0`, the
`mlpcopilot` runtime profile requires either `api.apiKey` or
`api.trustProxyAuth=true`.

### Direct API Key

Use this when MLP Copilot should authenticate requests itself:

```json
{
  "runtimeProfile": "mlpcopilot",
  "api": {
    "host": "0.0.0.0",
    "port": 8900,
    "apiKey": "${MLPCOPILOT_API_KEY}"
  }
}
```

Start the service:

```bash
export MLPCOPILOT_API_KEY='replace-with-a-long-random-secret'
mlpcopilot serve
```

Client requests must include a key:

```bash
curl http://YOUR_HOST:8900/v1/models \
  -H "Authorization: Bearer $MLPCOPILOT_API_KEY"
```

`/health` intentionally remains unauthenticated so local service monitors can
check the process.

### Trusted Reverse Proxy Auth

Use this only when the reverse proxy enforces authentication and the backend port
is not reachable directly from untrusted networks:

```json
{
  "runtimeProfile": "mlpcopilot",
  "api": {
    "host": "127.0.0.1",
    "port": 8900,
    "trustProxyAuth": true
  }
}
```

Minimal Nginx shape:

```nginx
server {
    listen 443 ssl;
    server_name mlpcopilot.example.org;

    # Put real auth here: mTLS, SSO gateway, auth_request, or allowlist.
    # Do not proxy unauthenticated internet traffic to MLP Copilot.

    location / {
        proxy_pass http://127.0.0.1:8900;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

With `trustProxyAuth=true`, MLP Copilot skips API-key checks. The proxy is the
security boundary.

## TUI Visual Smoke

Snapshot smoke renders can be generated with:

```bash
bash scripts/tui_visual_smoke.sh
```

The script renders wide and narrow snapshots into a temporary workspace and then
prints the manual checks to repeat in an ordinary terminal and in the VS Code
integrated terminal. Real interactive smoke is still manual because terminal
emulators differ in wrapping, key handling, and full-screen support.

## Linux Service

Run the gateway as a systemd user service so it starts automatically and restarts on failure.

**1. Find the mlpcopilot binary path:**

```bash
which mlpcopilot   # e.g. /home/user/.local/bin/mlpcopilot
```

**2. Create the service file** at `~/.config/systemd/user/mlpcopilot-gateway.service` (replace `ExecStart` path if needed):

```ini
[Unit]
Description=MLP Copilot Gateway
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/mlpcopilot gateway
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=%h

[Install]
WantedBy=default.target
```

**3. Enable and start:**

```bash
systemctl --user daemon-reload
systemctl --user enable --now mlpcopilot-gateway
```

**Common operations:**

```bash
systemctl --user status mlpcopilot-gateway        # check status
systemctl --user restart mlpcopilot-gateway       # restart after config changes
journalctl --user -u mlpcopilot-gateway -f        # follow logs
```

If you edit the `.service` file itself, run `systemctl --user daemon-reload` before restarting.

> **Note:** User services only run while you are logged in. To keep the gateway running after logout, enable lingering:
>
> ```bash
> loginctl enable-linger $USER
> ```

## macOS LaunchAgent

Use a LaunchAgent when you want `mlpcopilot gateway` to stay online after you log in, without keeping a terminal open.

**1. Get the absolute `mlpcopilot` path:**

```bash
which mlpcopilot   # e.g. /Users/youruser/.local/bin/mlpcopilot
```

Use that exact path in the plist. It keeps the Python environment from your install method.

**2. Create `~/Library/LaunchAgents/ai.mlpcopilot.gateway.plist`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.mlpcopilot.gateway</string>

  <key>ProgramArguments</key>
  <array>
    <string>/Users/youruser/.local/bin/mlpcopilot</string>
    <string>gateway</string>
    <string>--workspace</string>
    <string>/Users/youruser/.mlpcopilot/workspace</string>
  </array>

  <key>WorkingDirectory</key>
  <string>/Users/youruser/.mlpcopilot/workspace</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>

  <key>StandardOutPath</key>
  <string>/Users/youruser/.mlpcopilot/logs/gateway.log</string>

  <key>StandardErrorPath</key>
  <string>/Users/youruser/.mlpcopilot/logs/gateway.error.log</string>
</dict>
</plist>
```

**3. Load and start it:**

```bash
mkdir -p ~/Library/LaunchAgents ~/.mlpcopilot/logs
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/ai.mlpcopilot.gateway.plist
launchctl enable gui/$(id -u)/ai.mlpcopilot.gateway
launchctl kickstart -k gui/$(id -u)/ai.mlpcopilot.gateway
```

**Common operations:**

```bash
launchctl list | grep ai.mlpcopilot.gateway
launchctl kickstart -k gui/$(id -u)/ai.mlpcopilot.gateway   # restart
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/ai.mlpcopilot.gateway.plist
```

After editing the plist, run `launchctl bootout ...` and `launchctl bootstrap ...` again.

> **Note:** if startup fails with "address already in use", stop the manually started `mlpcopilot gateway` process first.
