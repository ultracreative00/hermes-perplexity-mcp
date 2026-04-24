# Hermes ↔ Perplexity MCP Bridge v9.9.2

> **Control Perplexity AI via your real browser — no API key required. No Perplexity API is used or permitted.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Quick Start

```bash
git clone https://github.com/ultracreative00/hermes-perplexity-mcp
cd hermes-perplexity-mcp
bash install.sh
```

`bash install.sh` handles everything — dependencies, virtual environment, and first-run checks.

Then open: **http://localhost:3456/dashboard/**

---

## Starting the Server

```bash
./start.sh
```

`start.sh` does the full startup sequence automatically:

1. **Finds Chrome** on your system (`google-chrome-stable`, `chromium`, `brave-browser`, etc.)
2. **Kills any existing Chrome** on port 9222 to avoid conflicts
3. **Launches a fresh Chrome** with remote debugging enabled:
   ```
   --remote-debugging-port=9222
   --user-data-dir=~/chrome-debug-profile
   → opens https://www.perplexity.ai
   ```
4. **Checks login status** via Playwright CDP using the Perplexity nav element XPath
5. **Blocks startup** if not logged in — prints a clear error and exits:
   ```
   ❌  Perplexity isn't Logged In
   Please sign into Perplexity in the Chrome window that just opened, then re-run ./start.sh
   ```
6. **Starts the MCP server** only when Perplexity is confirmed logged in:
   ```
   ✅  Perplexity is logged in — ready to go!
   ```

> **First run?** Chrome will open Perplexity. Sign in, then re-run `./start.sh`. Your session is saved to `~/chrome-debug-profile` — you won't need to sign in again.

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
    ├─ CDP mode (default): attaches to real Chrome launched by start.sh
    │    --remote-debugging-port=9222
    │    --user-data-dir="$HOME/chrome-debug-profile"
    │
    └─ Fallback mode: Playwright persistent context (if no Chrome found)
         Dedicated profile: ./chrome-profile/
    │
    ▼
Perplexity Browser (https://www.perplexity.ai)
```

### CDP vs Fallback

| # | Mode | How | Login |
|---|------|-----|-------|
| 1 | **CDP (real Chrome)** | Connects to Chrome already running on `localhost:9222` | Uses your existing browser session — no re-login needed |
| 2 | **Playwright fallback** | Launches its own Chromium with `./chrome-profile/` | Sign in once; session saved for future runs |

Check active mode at any time:
```
GET http://localhost:3456/status  →  "mode": "CDP (real Chrome)" or "Playwright (automation)"
```

---

## Endpoints

| Endpoint | Description |
|---|---|
| `http://localhost:3456/dashboard/` | Web UI |
| `http://localhost:3456/sse` | SSE stream for Hermes |
| `http://localhost:3456/mcp` | JSON-RPC 2.0 tool calls |
| `http://localhost:3456/status` | Server status JSON |
| `http://localhost:3456/memory` | View all stored memories (GET) |
| `http://localhost:3456/upload` | Upload file (POST multipart) |
| `http://localhost:3456/download/<file>` | Download a response file |
| `http://localhost:3456/downloads` | List all downloaded files |

---

## Available Tools

### Core Tools

| Tool | Description |
|---|---|
| `send_message` | Send a message to Perplexity and get back **only the latest isolated response** (no stacking from previous answers). Memory context is auto-prepended if memories exist. Auto-reconnects if Chrome was closed mid-session. |
| `switch_model` | Change the active model |
| `upload_file` | Upload a file into the active chat |
| `get_last_response` | Retrieve the last response text |
| `screenshot` | Take a screenshot of the browser |
| `new_chat` | Navigate to Perplexity home to start a fresh conversation |
| `list_models` | List all available models and the currently active one |
| `check_login` | Verify login status and show connection mode |

### Memory Tools

Perplexity doesn't remember previous conversations. The memory system lets Hermes store facts persistently — they are automatically injected as context into every `send_message` call.

| Tool | Description |
|---|---|
| `memory_set` | Store a key-value fact (e.g. `user_name = "Ahmad"`). Pass empty value to delete. |
| `memory_get` | Retrieve a specific memory by key, or all memories if no key given. |
| `memory_delete` | Delete a memory entry by key. |

**How it works:**

When any memories are stored, every `send_message` automatically prepends:
```
[Context from memory]
- user_name: Ahmad
- user_location: Islamabad, Pakistan
- preferred_language: English

<your actual message here>
```

Memories are persisted to `memory.json` in the project root and survive server restarts.

### Available Models

| Model | Label |
|---|---|
| `Default` | Perplexity default |
| `Claude Sonnet 4.5` | claude |
| `GPT-4o` | gpt |
| `Gemini 2.0 Flash` | gemini |
| `Sonar Pro` | sonar pro |
| `Sonar` | sonar |
| `R1 1776` | r1 |

---

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

---

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

---

## Project Structure

```
hermes-perplexity-mcp/
├── server/
│   └── mcp_server.py        # FastAPI + Playwright MCP server (v9.9.2)
├── client/
│   └── hermes_mcp_client.py # CLI client for Hermes
├── dashboard/
│   └── index.html           # Web UI
├── chrome-profile/          # Playwright fallback Chrome profile
├── uploads/                 # Files uploaded to Perplexity
├── downloads/               # Responses saved from Perplexity
├── memory.json              # Persistent memory store (auto-created)
├── requirements.txt
├── install.sh               # One-command install & start
├── setup.sh
├── start.sh                 # Full startup: Chrome → login check → MCP server
└── hermes_mcp_config.json
```

---

## Changelog

### v9.9.2
- **Stale-page auto-reconnect**: Fixed `Locator.count: Target page, context or browser has been closed` error — the server now detects a dead Playwright `Page` object before every operation via `_page_alive()` health-check and automatically relaunches the browser if the page is gone
- **`_is_closed_error()` guard**: Any mid-send `TargetClosedError` or session-closed exception triggers a full browser teardown → relaunch → retry cycle instead of a hard failure
- **`_ensure_page_alive()`**: Called at the start of every tool handler so stale state never reaches Playwright locator calls
- **Broadcast on reconnect**: Dashboard receives a `browser_reconnecting` event so users see live status during recovery

### v9.9.1
- **`start.sh` auto-Chrome**: Kills old Chrome, launches fresh CDP instance, opens Perplexity automatically
- **Login gate**: `start.sh` blocks server start if Perplexity isn't logged in — prints `❌ Perplexity isn't Logged In` and exits
- **Sticky overlay click fix**: Fixed `Locator.click: Timeout` error caused by Perplexity's sticky header intercepting pointer events — now uses JS `focus()` + scroll offset instead of Playwright `.click()`

### v9.9.0
- **Isolated responses**: `send_message` now returns only the latest answer — no more stacking of previous answers in the reply
- **Memory system**: New `memory_set`, `memory_get`, `memory_delete` tools with auto-injection into every message
- **Persistent memory**: Memories saved to `memory.json` and survive server restarts
- **`/memory` endpoint**: View all stored memories via REST

### v9.x
- Auto-reconnect when browser page closes mid-session
- Stale-page detection and graceful recovery
- Baseline snapshot diffing to detect new responses accurately
- Source/citation extraction and formatting

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Locator.count: Target page, context or browser has been closed` | Fixed in v9.9.2 — server auto-detects dead page and relaunches. Pull latest and restart. |
| `❌ Perplexity isn't Logged In` on startup | Chrome opened Perplexity — sign in, then re-run `./start.sh` |
| `Locator.click: Timeout` / sticky overlay error | Fixed in v9.9.1 — pull latest and restart |
| `CDP connect failed` in logs | Chrome isn't running on port 9222 — server falls back to Playwright automatically |
| Response includes previous answers (stacking) | Fixed in v9.9.0 — pull latest and restart |
| `Permission denied` on `install.sh` | Run `bash install.sh` (not `./install.sh`) |
| Already logged in but server says not logged in | Run `check_login` tool or check `/status` to confirm CDP mode is active |
| Memory not being injected | Check `/memory` endpoint — if empty, use `memory_set` to store context first |

---

## License

MIT
