# Hermes ↔ Perplexity MCP Bridge v9

> **Control Perplexity AI via your real browser — no API key required. No Perplexity API is used or permitted.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Quick Start

```bash
git clone https://github.com/ultracreative00/hermes-perplexity-mcp
cd hermes-perplexity-mcp
./setup.sh       # first time only
./start.sh
```

Then open: **http://localhost:3456/dashboard/**

## Architecture

```
Hermes Agent
    │
    │  SSE  (http://localhost:3456/sse)
    │  JSON-RPC 2.0  (http://localhost:3456/mcp)
    ▼
MCP Server (FastAPI + Playwright)
    │
    │  Browser automation (launch_persistent_context)
    │  Dedicated profile: ./chrome-profile/
    ▼
Perplexity Browser (https://www.perplexity.ai)
```

## Why v9 Works on Chrome 136+

Chrome 136 silently disabled `--remote-debugging-port` when pointed at the
default profile (`~/.config/google-chrome`).

**v9 uses a dedicated automation profile at `./chrome-profile/`** via
`launch_persistent_context()` — the only reliable approach on Chrome 136+ Linux.

- **First run:** Chrome opens fresh — sign into Perplexity once
- **All future runs:** Session saved in `./chrome-profile/` — no sign-in needed

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
| `check_login` | Verify login status |

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
│   └── mcp_server.py        # FastAPI + Playwright MCP server
├── client/
│   └── hermes_mcp_client.py # CLI client for Hermes
├── dashboard/
│   └── index.html           # Web UI
├── chrome-profile/          # Dedicated Chrome automation profile
├── uploads/                 # Files uploaded to Perplexity
├── downloads/               # Responses saved from Perplexity
├── requirements.txt
├── setup.sh
├── start.sh
└── hermes_mcp_config.json
```

## License

MIT
