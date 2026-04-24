#!/usr/bin/env bash
set -e
echo "=== Starting Hermes-Perplexity MCP Server v9 ==="

if [ ! -d ".venv" ]; then
  echo "Run ./setup.sh first"
  exit 1
fi

source .venv/bin/activate

# Remove any stale Chrome locks in automation profile
for lock in chrome-profile/SingletonLock chrome-profile/SingletonCookie chrome-profile/SingletonSocket; do
  if [ -f "$lock" ]; then
    echo "[cleanup] Removing stale lock: $lock"
    rm -f "$lock"
  fi
done

echo ""
echo "  Dashboard  → http://localhost:3456/dashboard/"
echo "  SSE stream → http://localhost:3456/sse"
echo "  MCP tools  → http://localhost:3456/mcp"
echo "  Status     → http://localhost:3456/status"
echo ""
echo "  Hermes config: hermes_mcp_config.json"
echo ""
echo "  NOTE: On first run, sign into Perplexity in the browser."
echo "        Session is saved to ./chrome-profile/ for future runs."
echo ""

cd server
python -m uvicorn mcp_server:app --host 0.0.0.0 --port 3456 --reload
