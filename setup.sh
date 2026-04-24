#!/usr/bin/env bash
set -e
echo "=== Hermes-Perplexity MCP Setup ==="

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found"; exit 1
fi

if [ ! -d ".venv" ]; then
  echo "[1/4] Creating virtual environment..."
  python3 -m venv .venv
fi

echo "[2/4] Activating venv and installing dependencies..."
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "[3/4] Installing Playwright browsers..."
python -m playwright install chromium
python -m playwright install-deps chromium 2>/dev/null || true

mkdir -p uploads downloads chrome-profile

echo "[4/4] Setup complete!"
echo ""
echo "Run: ./start.sh"
echo "Dashboard: http://localhost:3456/dashboard/"
echo "SSE endpoint: http://localhost:3456/sse"
