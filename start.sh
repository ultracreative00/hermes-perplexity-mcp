#!/usr/bin/env bash
set -e

echo "=== Hermes-Perplexity MCP Server v9.9.1 ==="
echo ""

if [ ! -d ".venv" ]; then
  echo "[error] Run ./setup.sh first"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Kill any existing Chrome instances and launch a fresh one with CDP
# ---------------------------------------------------------------------------
CHROME_BIN=""
for c in \
  "google-chrome-stable" \
  "google-chrome" \
  "chromium-browser" \
  "chromium" \
  "brave-browser" \
  "microsoft-edge"; do
  if command -v "$c" &>/dev/null; then
    CHROME_BIN="$c"
    break
  fi
done

if [ -z "$CHROME_BIN" ]; then
  echo "[warn] No system Chrome found — server will fall back to Playwright bundled Chromium."
else
  echo "[chrome] Found: $CHROME_BIN"
  echo "[chrome] Closing any existing Chrome windows..."
  pkill -f "remote-debugging-port=9222" 2>/dev/null || true
  sleep 1

  PROFILE_DIR="$HOME/chrome-debug-profile"
  mkdir -p "$PROFILE_DIR"

  # Remove stale locks
  for lock in SingletonLock SingletonCookie SingletonSocket; do
    [ -f "$PROFILE_DIR/$lock" ] && rm -f "$PROFILE_DIR/$lock" && echo "[chrome] Removed stale lock: $lock"
  done

  echo "[chrome] Launching with remote debugging on port 9222..."
  "$CHROME_BIN" \
    --remote-debugging-port=9222 \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --disable-default-apps \
    --window-size=1280,900 \
    "https://www.perplexity.ai" \
    &>/dev/null &

  CHROME_PID=$!
  echo "[chrome] PID=$CHROME_PID — waiting for Chrome to load Perplexity..."
  sleep 5

  # ---------------------------------------------------------------------------
  # Step 2: Login check via CDP/Playwright
  # Check for the XPath element that confirms Perplexity is logged in:
  # /html/body/div[1]/div/div/div/div/nav/div/div[1]/div[3]/div/div[2]/div/div/div/button/div/div/div/div/div/div/div[1]/div
  # ---------------------------------------------------------------------------
  echo "[login] Checking Perplexity login status..."

  source .venv/bin/activate

  LOGIN_STATUS=$(python3 - <<'PYEOF'
import asyncio, sys
from playwright.async_api import async_playwright

LOGIN_XPATH = (
    "/html/body/div[1]/div/div/div/div/nav"
    "/div/div[1]/div[3]/div/div[2]/div/div/div"
    "/button/div/div/div/div/div/div/div[1]/div"
)

async def check():
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222", timeout=10_000)
            ctx = browser.contexts[0] if browser.contexts else None
            if not ctx:
                print("NO_CONTEXT")
                return
            page = ctx.pages[0] if ctx.pages else None
            if not page:
                print("NO_PAGE")
                return
            # Wait up to 10s for Perplexity to finish loading
            try:
                await page.wait_for_load_state("load", timeout=10_000)
            except Exception:
                pass
            try:
                el = page.locator(f"xpath={LOGIN_XPATH}").first
                count = await el.count()
                if count > 0:
                    print("LOGGED_IN")
                else:
                    print("NOT_LOGGED_IN")
            except Exception as e:
                print(f"CHECK_ERROR:{e}")
    except Exception as e:
        print(f"CONNECT_ERROR:{e}")

asyncio.run(check())
PYEOF
  )

  echo "[login] Result: $LOGIN_STATUS"

  if echo "$LOGIN_STATUS" | grep -q "LOGGED_IN"; then
    echo ""
    echo "  ✅  Perplexity is logged in — ready to go!"
    echo ""
  else
    echo ""
    echo "  ❌  Perplexity isn't Logged In"
    echo ""
    echo "  Please sign into Perplexity in the Chrome window that just opened,"
    echo "  then re-run ./start.sh"
    echo ""
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Step 3: Remove stale automation profile locks
# ---------------------------------------------------------------------------
for lock in chrome-profile/SingletonLock chrome-profile/SingletonCookie chrome-profile/SingletonSocket; do
  if [ -f "$lock" ]; then
    echo "[cleanup] Removing stale lock: $lock"
    rm -f "$lock"
  fi
done

# ---------------------------------------------------------------------------
# Step 4: Start the MCP server
# ---------------------------------------------------------------------------
echo "  Dashboard  → http://localhost:3456/dashboard/"
echo "  SSE stream → http://localhost:3456/sse"
echo "  MCP tools  → http://localhost:3456/mcp"
echo "  Status     → http://localhost:3456/status"
echo "  Memory     → http://localhost:3456/memory"
echo ""
echo "  Hermes config: hermes_mcp_config.json"
echo ""

source .venv/bin/activate
cd server
python -m uvicorn mcp_server:app --host 0.0.0.0 --port 3456 --reload
