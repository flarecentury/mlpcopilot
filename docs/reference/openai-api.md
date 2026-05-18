# OpenAI-Compatible API

mlpcopilot can expose a minimal OpenAI-compatible endpoint for local integrations:

```bash
pip install "mlpcopilot[api]"
mlpcopilot serve
```

By default, the API binds to `127.0.0.1:8900`. You can change this in `config.json`.

## Behavior

- Session isolation: pass `"session_id"` in the request body to isolate conversations; omit for a shared default session (`api:default`)
- Single-message input: each request must contain exactly one `user` message
- Fixed model: omit `model`, or pass the same model shown by `/v1/models`
- Streaming: set `stream=true` to receive Server-Sent Events (`text/event-stream`) with OpenAI-compatible delta chunks, terminated by `data: [DONE]`; omit or set `stream=false` for a single JSON response
- **File uploads**: supports images, PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx) via JSON base64 or `multipart/form-data` (max 10MB per file)
- API requests run in the synthetic `api` channel, so the `message` tool does **not** automatically deliver to Telegram/Discord/etc. To proactively send to another chat, call `message` with an explicit `channel` and `chat_id` for an enabled channel.

Example tool call for cross-channel delivery from an API session:

```json
{
  "content": "Build finished successfully.",
  "channel": "telegram",
  "chat_id": "123456789"
}
```

If `channel` points to a channel that is not enabled in your config, mlpcopilot will queue the outbound event but no platform delivery will occur.

## Endpoints

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `GET /v1/approvals`
- `GET /v1/approvals/{approval_id}`
- `POST /v1/approvals/{approval_id}/approve`
- `POST /v1/approvals/{approval_id}/reject`
- `POST /v1/approvals/{approval_id}/changes`

## Authentication

Local-only API use can keep the default bind:

```json
{
  "api": {
    "host": "127.0.0.1",
    "port": 8900
  }
}
```

For a public bind, the `mlpcopilot` profile requires one of two explicit choices.

Use `api.apiKey` when MLP Copilot should authenticate `/v1/*` routes itself:

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

Then send either `Authorization: Bearer ...`, `X-MLPCopilot-API-Key`, or `X-API-Key`:

```bash
curl http://127.0.0.1:8900/v1/models \
  -H "Authorization: Bearer $MLPCOPILOT_API_KEY"
```

Use `api.trustProxyAuth=true` only when a trusted reverse proxy performs authentication before requests reach MLP Copilot:

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

In this mode MLP Copilot does not check an API key. The proxy must block unauthenticated traffic and should not expose the backend port directly.

## Approval Workflow

API sessions use the same runtime approval store as CLI, TUI, and Telegram. When a gated action returns an approval id, approve or reject it through the runtime endpoints:

```bash
curl http://127.0.0.1:8900/v1/approvals

curl -X POST http://127.0.0.1:8900/v1/approvals/apr_abc123/approve \
  -H "Content-Type: application/json" \
  -d '{"reason": "approved by API operator"}'
```

## curl

```bash
curl http://127.0.0.1:8900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "hi"}],
    "session_id": "my-session"
  }'
```

## File Upload (JSON base64)

Send images inline using the OpenAI multimodal content format:

```bash
curl http://127.0.0.1:8900/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": [
      {"type": "text", "text": "Describe this image"},
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR..."}}
    ]}]
  }'
```

## File Upload (multipart/form-data)

Upload any supported file type (images, PDF, Word, Excel, PPT) via multipart:

```bash
# Single file
curl http://127.0.0.1:8900/v1/chat/completions \
  -F "message=Summarize this report" \
  -F "files=@report.docx"

# Multiple files with session isolation
curl http://127.0.0.1:8900/v1/chat/completions \
  -F "message=Compare these files" \
  -F "files=@chart.png" \
  -F "files=@data.xlsx" \
  -F "session_id=my-session"
```

Supported file types:
- **Images**: PNG, JPEG, GIF, WebP (sent to AI as base64 for vision analysis)
- **Documents**: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx) (text extracted and sent to AI)
- **Text**: TXT, Markdown, CSV, JSON, etc. (read directly)

## Python (`requests`)

```python
import requests

resp = requests.post(
    "http://127.0.0.1:8900/v1/chat/completions",
    json={
        "messages": [{"role": "user", "content": "hi"}],
        "session_id": "my-session",  # optional: isolate conversation
    },
    timeout=120,
)
resp.raise_for_status()
print(resp.json()["choices"][0]["message"]["content"])
```

## Python (`openai`)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8900/v1",
    api_key="dummy",
)

resp = client.chat.completions.create(
    model="MiniMax-M2.7",
    messages=[{"role": "user", "content": "hi"}],
    extra_body={"session_id": "my-session"},  # optional: isolate conversation
)
print(resp.choices[0].message.content)
```
