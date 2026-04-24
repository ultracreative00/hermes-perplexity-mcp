# Hermes ↔ Perplexity MCP Bridge v9.1

> **Control Perplexity AI via your real browser — no API key required. No Perplexity API is used or permitted.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Quick Start

```bash
git clone https://github.com/ultracreative00/hermes-perplexity-mcp
cd hermes-perplexity-mcp
bash install.sh
```

`bash install.sh` handles everything — dependencies, permissions, virtual environment setup, and first-run checks. No need to run `setup.sh` or `start.sh` manually on first install.

Then open: **http://localhost:3456/dashboard/**

---

## Recommended: Launch Real Chrome First (Avoids Bot Detection)

Perplexity detects automated browsers and may block the login screen. To avoid this, launch your **real Chrome** with remote debugging enabled **before** starting the MCP server:

```bash
google-chrome-stable \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile"
```

Sign into Perplexity in that window (first time only — session is saved to `~/chrome-debug-profile`).

Then start the server in a second terminal:

```bash
bash install.sh
```

The server will log `✓ Connected to real Chrome via CDP` and operate fully logged in.

> **If you skip this step**, the server falls back to a Playwright-managed browser. It still works, but you may need to sign in manually on the first run.

---

## Architecture

```
Hermes Agent
    │
    │  SSE  (http://localhost:3456/sse)
    │  JSON-RPC 2.0  (http://localhost:3456/mcp)
    ▼
MCP Server (FastAPI + Playwright)
    │
    ├─ CDP mode (preferred): attaches to real Chrome on port 9222
    │    google-chrome-stable --remote-debugging-port=9222
    │    --user-data-dir="$HOME/chrome-debug-profile"
    │
    └─ Fallback mode: Playwright persistent context
         Dedicated profile: ./chrome-profile/
    │
    ▼
Perplexity Browser (https://www.perplexity.ai)
```

## How the CDP / Fallback Logic Works

On every startup the server tries two strategies in order:

| # | Mode | How | Login |
|---|------|-----|-------|
| 1 | **CDP (real Chrome)** | Connects to Chrome already running on `localhost:9222` | Uses your existing browser session — no re-login needed |
| 2 | **Playwright fallback** | Launches its own Chromium with `./chrome-profile/` | Sign in once; session is saved for future runs |

Check which mode is active at any time:

```
GET http://localhost:3456/status   →  "mode": "CDP (real Chrome)" or "Playwright (automation)"
```

---

## Endpoints

| Endpoint | Description |
|---|---|
| `http://localhost:3456/dashboard/` | Web UI |
| `http://localhost:3456/sse` | SSE stream for Hermes |
| `http://localhost:3456/mcp` | JSON-RPC 2.0 tool calls |
| `http://localhost:3456/status` | Server status JSON |
| `http://localhost:3456/upload` | Upload file (POST multipart) |
| `http://localhost:3456/download/<file>` | Download response file |
| `http://localhost:3456/downloads` | List all downloads |

## Available Tools

| Tool | Description |
|---|---|
| `send_message` | Send message to Perplexity, get response |
| `switch_model` | Change model (Default / Claude Sonnet 4.5 / GPT-4o / Gemini 2.0 Flash / Sonar Pro / Sonar / R1 1776) |
| `upload_file` | Upload a file into the active chat |
| `get_last_response` | Retrieve last response text |
| `screenshot` | Screenshot the browser |
| `new_chat` | Start a fresh conversation |
| `list_models` | List available models |
| `check_login` | Verify login status and show connection mode |

## Hermes Agent Config

Add `hermes_mcp_config.json` to your Hermes agent:

```json
{
  "mcpServers": {
    "perplexity-browser": {
      "url": "http://localhost:3456/sse",
      "transport": "sse"
    }
  }
}
```

## CLI Client

```bash
source .venv/bin/activate

# Status
python client/hermes_mcp_client.py --status

# Send message
python client/hermes_mcp_client.py --message "What is quantum entanglement?"

# Switch model then ask
python client/hermes_mcp_client.py --model "GPT-4o" --message "Explain it simply"

# Upload file + ask
python client/hermes_mcp_client.py --upload ~/docs/paper.pdf --message "Summarise this"

# New chat
python client/hermes_mcp_client.py --new-chat
```

## Project Structure

```
hermes-perplexity-mcp/
├── server/
│   └── mcp_server.py        # FastAPI + Playwright MCP server (v9.1)
├── client/
│   └── hermes_mcp_client.py # CLI client for Hermes
├── dashboard/
│   └── index.html           # Web UI
├── chrome-profile/          # Playwright fallback Chrome profile
├── uploads/                 # Files uploaded to Perplexity
├── downloads/               # Responses saved from Perplexity
├── requirements.txt
├── install.sh               # One-command install & start
├── setup.sh
├── start.sh
└── hermes_mcp_config.json
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Perplexity opens but no login option visible | Launch real Chrome with `--remote-debugging-port=9222` first (see above) |
| `CDP connect failed` in logs | Chrome isn't running on port 9222 — server falls back to Playwright automatically |
| `Permission denied` on `install.sh` | Run `bash install.sh` (not `./install.sh`) — no chmod needed |
| Already logged in but server says not logged in | Run `check_login` tool or check `/status` to confirm CDP mode is active |

## License

MIT
