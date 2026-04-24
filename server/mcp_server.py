import asyncio, json, logging, os, time, uuid, traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from playwright.async_api import async_playwright, BrowserContext, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("mcp")

BASE_DIR     = Path(__file__).parent.parent
UPLOADS      = BASE_DIR / "uploads"
DOWNLOADS    = BASE_DIR / "downloads"
AUTO_PROFILE = BASE_DIR / "chrome-profile"
DEBUG_PROFILE = Path.home() / "chrome-debug-profile"
CDP_URL       = "http://localhost:9222"

UPLOADS.mkdir(exist_ok=True)
DOWNLOADS.mkdir(exist_ok=True)
AUTO_PROFILE.mkdir(exist_ok=True)
DEBUG_PROFILE.mkdir(exist_ok=True)

def find_chrome_exe() -> str:
    for c in [
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
        "/usr/bin/brave-browser",
        "/usr/bin/microsoft-edge",
    ]:
        if Path(c).exists():
            log.info(f"[CHROME] Found system Chrome: {c}")
            return c
    log.info("[CHROME] No system Chrome found — will use Playwright bundled Chromium")
    return ""

CHROME_EXE = find_chrome_exe()

MODELS = [
    "Default", "Claude Sonnet 4.5", "GPT-4o",
    "Gemini 2.0 Flash", "Sonar Pro", "Sonar", "R1 1776",
]
MODEL_LABEL = {
    "Default": None, "Claude Sonnet 4.5": "Claude", "GPT-4o": "GPT-4o",
    "Gemini 2.0 Flash": "Gemini", "Sonar Pro": "Sonar Pro",
    "Sonar": "Sonar", "R1 1776": "R1",
}

class State:
    pw = None
    ctx: BrowserContext | None = None
    page: Page | None = None
    current_model = "Default"
    detected_model = ""
    last_attr = ""
    last_resp = ""
    ready = False
    logged_in = False
    cdp_mode = False
    pending_attach: str = ""   # original filename of last uploaded file

st = State()
clients: list[asyncio.Queue] = []

async def broadcast(t: str, d: dict):
    msg = json.dumps({"type": t, "data": d, "ts": time.time()})
    for q in clients:
        await q.put(msg)

# ---------------------------------------------------------------------------
# Page health-check + auto-reconnect
# ---------------------------------------------------------------------------
async def _page_alive() -> bool:
    if st.page is None:
        return False
    try:
        await st.page.evaluate("()=>1", timeout=3_000)
        return True
    except Exception:
        return False

async def _ensure_page_alive():
    if await _page_alive():
        return
    log.warning("[RECONNECT] Page is dead — relaunching browser...")
    await broadcast("browser_reconnecting", {"note": "Browser page was closed. Reconnecting..."})
    for obj, method in [(st.ctx, "close"), (st.pw, "stop")]:
        if obj is not None:
            try:
                await getattr(obj, method)()
            except Exception:
                pass
    st.pw      = None
    st.ctx     = None
    st.page    = None
    st.ready   = False
    st.cdp_mode = False
    await launch_browser()

# ---------------------------------------------------------------------------

async def _try_cdp_connect() -> bool:
    try:
        st.pw = await async_playwright().start()
        browser = await st.pw.chromium.connect_over_cdp(CDP_URL, timeout=5_000)
        log.info(f"[LAUNCH] ✓ Connected to real Chrome via CDP at {CDP_URL}")
        st.cdp_mode = True
        contexts = browser.contexts
        st.ctx = contexts[0] if contexts else await browser.new_context()
        pages = st.ctx.pages
        st.page = pages[0] if pages else await st.ctx.new_page()
        if "perplexity.ai" not in st.page.url:
            for attempt in range(1, 4):
                try:
                    await st.page.goto("https://www.perplexity.ai", wait_until="load", timeout=30_000)
                    break
                except Exception as e:
                    log.warning(f"[LAUNCH] Nav attempt {attempt}/3 failed: {e}")
                    await asyncio.sleep(2)
        await asyncio.sleep(3)
        return True
    except Exception as e:
        log.info(f"[LAUNCH] CDP connect failed ({e}) — falling back to Playwright launch")
        try:
            if st.pw: await st.pw.stop()
        except:
            pass
        st.pw = st.ctx = st.page = None
        st.cdp_mode = False
        return False

async def _launch_playwright_context():
    profile = str(AUTO_PROFILE)
    log.info("=" * 55)
    log.info("[LAUNCH] Mode     = Playwright persistent context (fallback)")
    log.info(f"[LAUNCH] Profile  = {profile}")
    log.info(f"[LAUNCH] Chrome   = {CHROME_EXE or 'playwright bundled chromium'}")
    log.info(f"[LAUNCH] UID      = {os.getuid()}")
    log.info("=" * 55)
    for lock in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lp = AUTO_PROFILE / lock
        if lp.exists():
            lp.unlink()
            log.info(f"[LAUNCH] Removed stale lock: {lp.name}")
    st.pw = await async_playwright().start()
    args = [
        "--password-store=basic", "--use-mock-keychain", "--no-first-run",
        "--no-default-browser-check", "--disable-default-apps",
        "--disable-infobars", "--window-size=1280,900",
    ]
    if os.getuid() == 0:
        args.append("--no-sandbox")
    kw: dict = dict(
        user_data_dir=profile, headless=False,
        viewport={"width": 1280, "height": 900},
        args=args, ignore_default_args=["--enable-automation"], timeout=60_000,
    )
    if CHROME_EXE:
        kw["executable_path"] = CHROME_EXE
    st.ctx = await st.pw.chromium.launch_persistent_context(**kw)
    await asyncio.sleep(1)
    pages = st.ctx.pages
    st.page = pages[0] if pages else await st.ctx.new_page()
    for attempt in range(1, 4):
        try:
            await st.page.goto("https://www.perplexity.ai", wait_until="load", timeout=30_000)
            break
        except Exception as e:
            log.warning(f"[LAUNCH] Nav attempt {attempt}/3 failed: {e}")
            await asyncio.sleep(2)
    await asyncio.sleep(3)

async def launch_browser():
    try:
        cdp_ok = await _try_cdp_connect()
        if not cdp_ok:
            await _launch_playwright_context()
        st.logged_in = await _check_login()
        st.ready = True
        mode = "CDP (real Chrome)" if st.cdp_mode else "Playwright (automation)"
        log.info(f"[LAUNCH] READY — mode={mode} logged_in={st.logged_in}")
        note = (
            "✓ Connected to your real Chrome via CDP. Already logged in!"
            if (st.cdp_mode and st.logged_in) else
            "⚠ Connected to real Chrome via CDP but not logged in. Please sign in."
            if (st.cdp_mode and not st.logged_in) else
            "✓ Already logged in (Playwright mode)"
            if st.logged_in else
            ("⚠ First run: please sign into Perplexity in the browser window — "
             "session will be saved to ./chrome-profile/\n\n"
             "TIP: For a better experience, launch Chrome first:\n"
             f'  google-chrome-stable --remote-debugging-port=9222 --user-data-dir="{DEBUG_PROFILE}"\n'
             "Then restart the MCP server.")
        )
        await broadcast("browser_ready", {
            "logged_in": st.logged_in,
            "url": st.page.url,
            "mode": mode,
            "note": note,
        })
    except Exception as e:
        log.error(f"[LAUNCH] FATAL: {e}")
        log.error(traceback.format_exc())
        await broadcast("browser_error", {"error": str(e), "traceback": traceback.format_exc()})

async def _check_login() -> bool:
    """
    Robust login detection for Perplexity.ai.
    Strategy (in order of reliability):
      1. JS cookie scan — pplx_auth, __session, next-auth.session-token, pplx_user
      2. JS localStorage scan — pplx.user, user, auth, session
      3. Wide DOM selector scan — avatars, account menus, profile links
      4. Absence of Sign-in button (last resort)
    Returns True if any signal confirms a logged-in session.
    """
    try:
        # 1. Cookie-based check (most reliable)
        has_auth_cookie = await st.page.evaluate("""() => {
            const cookieStr = document.cookie;
            const authKeys = ['pplx_auth', '__session', 'next-auth.session-token',
                              'pplx_user', 'pplx-session', '__Secure-next-auth',
                              'auth_token', 'user_id', 'session'];
            return authKeys.some(k => cookieStr.includes(k));
        }""")
        if has_auth_cookie:
            log.info("[LOGIN] ✓ Detected via auth cookie")
            return True

        # 2. localStorage-based check
        has_local_storage = await st.page.evaluate("""() => {
            try {
                const keys = ['pplx.user', 'user', 'auth', 'session',
                              'next-auth.session-token', 'pplx_user', 'currentUser'];
                return keys.some(k => {
                    const v = localStorage.getItem(k);
                    return v && v.length > 0;
                });
            } catch(e) { return false; }
        }""")
        if has_local_storage:
            log.info("[LOGIN] ✓ Detected via localStorage")
            return True

        # 3. Wide DOM selector scan
        logged_in_selectors = [
            # Avatar / profile images
            'img[alt*="avatar" i]',
            'img[alt*="profile" i]',
            'img[alt*="user" i]',
            'img[src*="googleusercontent"]',
            'img[src*="avatar"]',
            'img[src*="profile"]',
            # Account / user UI elements
            'button[aria-label*="account" i]',
            'button[aria-label*="user" i]',
            'button[aria-label*="profile" i]',
            'button[aria-label*="menu" i]',
            '[data-testid*="user" i]',
            '[data-testid*="avatar" i]',
            '[data-testid*="account" i]',
            '[data-testid*="profile" i]',
            # Settings / account links
            'a[href*="/settings"]',
            'a[href*="/account"]',
            'a[href*="/profile"]',
            # Class-based (common React patterns)
            'div[class*="UserAvatar"]',
            'div[class*="userAvatar"]',
            'div[class*="Avatar"]',
            'div[class*="ProfilePic"]',
            'div[class*="accountMenu"]',
            'div[class*="userMenu"]',
            # Perplexity-specific patterns
            '[class*="UserCircle"]',
            '[class*="userCircle"]',
            'button[class*="account"]',
            'span[class*="username"]',
        ]
        for sel in logged_in_selectors:
            try:
                loc = st.page.locator(sel).first
                if await loc.count() > 0:
                    log.info(f"[LOGIN] ✓ Detected via DOM selector: {sel}")
                    return True
            except Exception:
                continue

        # 4. Absence of Sign-in button (last resort — weakest signal)
        signin_visible = False
        for sel in [
            'a:has-text("Sign in")', 'button:has-text("Sign in")',
            'a:has-text("Log in")', 'button:has-text("Log in")',
            'a:has-text("Sign up")', 'button:has-text("Sign up")',
        ]:
            try:
                el = st.page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    signin_visible = True
                    break
            except Exception:
                continue

        # If no sign-in button found, assume logged in
        if not signin_visible:
            log.info("[LOGIN] ✓ No sign-in button visible — assuming logged in")
            return True

        log.info("[LOGIN] ✗ Not logged in — sign-in button found and no auth signals detected")
        return False

    except Exception as e:
        log.warning(f"[LOGIN] check error: {e}")
        return False

async def _ensure():
    if not st.ready:
        await launch_browser()
    await _ensure_page_alive()

async def _input():
    for sel in ['[role="textbox"]', "textarea", 'div[contenteditable="true"]']:
        el = st.page.locator(sel).first
        if await el.count() > 0:
            return el
    return None

async def _type(text: str):
    el = await _input()
    if not el:
        raise RuntimeError("No chat input found on page")
    await el.click()
    await st.page.keyboard.press("Control+a")
    await el.fill(text)

async def _submit():
    for sel in ['button[aria-label*="Submit" i]', 'button[type="submit"]', 'button[aria-label*="Ask" i]']:
        b = st.page.locator(sel).first
        if await b.count() > 0:
            await b.click()
            return
    await st.page.keyboard.press("Enter")

ATTR_PATTERNS = ["Prepared using", "Generated by", "Powered by", "Answer by", "Using model", "with ", "via "]

async def _extract() -> tuple[str, str]:
    best = ""
    for sel in [
        '[data-testid="answer-text"]', 'div[class*="prose"]', 'div[class*="answer"]',
        'div[class*="markdown"]', '.markdown-content', 'main p',
    ]:
        try:
            els = st.page.locator(sel)
            count = await els.count()
            if count == 0:
                continue
            parts = []
            for i in range(count):
                try:
                    t = (await els.nth(i).inner_text()).strip()
                    if t:
                        parts.append(t)
                except:
                    continue
            combined = "\n\n".join(parts).strip()
            if len(combined) > len(best):
                best = combined
        except:
            continue

    attr = ""
    for sel in [
        '[data-testid*="attribution"]', '[class*="attribution"]',
        '[class*="model-label"]', '[class*="ModelTag"]',
        'span[class*="source"]', 'div[class*="footer"] span',
    ]:
        try:
            el = st.page.locator(sel).first
            if await el.count() > 0:
                txt = (await el.inner_text()).strip()
                if txt:
                    attr = txt
                    break
        except:
            continue

    if not attr:
        try:
            body = await st.page.evaluate("()=>document.body.innerText")
            for line in body.splitlines():
                ls = line.strip()
                if any(p.lower() in ls.lower() for p in ATTR_PATTERNS) and len(ls) < 120:
                    attr = ls
                    break
        except:
            pass

    if attr:
        for m in MODELS:
            if m.lower() in attr.lower():
                st.detected_model = m
                break
    return best, attr

async def _wait_resp(timeout: int = 90) -> tuple[str, str]:
    await asyncio.sleep(2)
    deadline = time.time() + timeout
    prev = ""
    stable = 0
    while time.time() < deadline:
        await asyncio.sleep(1.5)
        sv = False
        try:
            sv = await st.page.locator('button[aria-label*="Stop" i],button:has-text("Stop")').first.is_visible()
        except:
            pass
        text, attr = await _extract()
        if text and text == prev:
            stable += 1
            if stable >= 3 or (not sv and stable >= 1):
                return text, attr
        else:
            stable = 0
            prev = text
    return await _extract()

async def _switch_model(model: str) -> dict:
    r: dict = {"success": False, "model": model, "note": ""}
    if "perplexity.ai" not in st.page.url:
        await st.page.goto("https://www.perplexity.ai", wait_until="load")
        await asyncio.sleep(2)
    btn = None
    for sel in [
        'button[data-testid*="model" i]', '[aria-label*="model" i]',
        'button:has-text("Default")', 'button:has-text("Claude")',
        'button:has-text("GPT")', 'button:has-text("Gemini")',
        'button:has-text("Sonar")', 'button:has-text("R1")',
        'div[class*="toolbar"] button', '.grow button',
        'form button:not([aria-label*="submit" i])',
    ]:
        try:
            loc = st.page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                lbl = (await loc.get_attribute("aria-label") or "").lower()
                txt = (await loc.inner_text() or "").lower()
                if any(x in lbl or x in txt for x in ["send", "submit", "attach", "upload", "search"]):
                    continue
                btn = loc
                break
        except:
            continue
    if not btn:
        fn = str(DOWNLOADS / "debug_model_btn.png")
        await st.page.screenshot(path=fn)
        r["note"] = "Model button not found — screenshot saved as debug_model_btn.png"
        return r
    await btn.click()
    await asyncio.sleep(1.5)
    pt = MODEL_LABEL.get(model)
    if not pt:
        await st.page.keyboard.press("Escape")
        st.current_model = "Default"
        r.update({"success": True, "note": "Default active"})
        return r
    clicked = False
    for sel in [
        f'[role="option"]:has-text("{pt}")', f'li:has-text("{pt}")',
        f'button:has-text("{pt}")', f'div[role="menuitem"]:has-text("{pt}")',
        f'[role="radio"]:has-text("{pt}")', f'label:has-text("{pt}")',
    ]:
        try:
            opt = st.page.locator(sel).first
            if await opt.count() > 0 and await opt.is_visible():
                await opt.click()
                await asyncio.sleep(1)
                st.current_model = model
                r.update({"success": True, "note": f"Selected {pt}"})
                clicked = True
                break
        except:
            continue
    if not clicked:
        fn = str(DOWNLOADS / "debug_model_picker.png")
        await st.page.screenshot(path=fn)
        await st.page.keyboard.press("Escape")
        r["note"] = f"Picker opened but option '{pt}' not found — check debug_model_picker.png"
    return r

async def tool_send_message(p: dict) -> dict:
    await _ensure()
    msg = p.get("message", "").strip()
    if not msg:
        return {"error": "message is required"}
    attach = st.pending_attach
    st.pending_attach = ""
    await broadcast("tool_start", {"tool": "send_message", "msg": msg[:80], "attach": attach})
    try:
        await _type(msg)
        await _submit()
        await broadcast("tool_progress", {"status": "waiting for response"})
        resp, attr = await _wait_resp(p.get("timeout", 90))
        st.last_resp = resp
        st.last_attr = attr
        mdl = st.detected_model or st.current_model
        fname = f"response_{int(time.time())}.txt"
        async with aiofiles.open(DOWNLOADS / fname, "w") as f:
            await f.write(f"Model: {mdl}\nAttribution: {attr}\n{'─'*60}\n{resp}")
        await broadcast("response_ready", {
            "preview": resp[:300],
            "full": resp,
            "model": mdl,
            "file": fname,
        })
        return {"response": resp, "model": mdl, "attribution": attr, "saved_as": fname}
    except Exception as e:
        await broadcast("tool_error", {"error": str(e)})
        return {"error": str(e)}

async def tool_switch_model(p: dict) -> dict:
    await _ensure()
    m = p.get("model", "Default")
    if m not in MODELS:
        return {"error": f"Unknown model: {m}. Valid: {MODELS}"}
    r = await _switch_model(m)
    await broadcast("model_switched", r)
    return r

async def tool_upload_file(p: dict) -> dict:
    await _ensure()
    fn = p.get("filename", "")
    fp = UPLOADS / fn
    if not fp.exists():
        return {"error": f"File not found in uploads/: {fn}"}
    original = p.get("original", fn)
    st.pending_attach = original
    for sel in ['button[aria-label*="ttach" i]', 'input[type="file"]']:
        loc = st.page.locator(sel).first
        if await loc.count() == 0:
            continue
        tag = await loc.evaluate("el=>el.tagName.toLowerCase()")
        if tag == "input":
            await loc.set_input_files(str(fp))
        else:
            async with st.page.expect_file_chooser(timeout=5000) as fc:
                await loc.click()
            await (await fc.value).set_files(str(fp))
        await broadcast("file_sent_to_browser", {"file": original})
        return {"success": True, "file": original}
    return {"error": "No file upload control found on page"}

async def tool_get_last_response(p: dict) -> dict:
    return {"response": st.last_resp, "attribution": st.last_attr, "model": st.detected_model or st.current_model}

async def tool_screenshot(p: dict) -> dict:
    await _ensure()
    fn = f"screenshot_{int(time.time())}.png"
    await st.page.screenshot(path=str(DOWNLOADS / fn), full_page=p.get("full_page", False))
    await broadcast("screenshot_ready", {"file": fn})
    return {"file": fn}

async def tool_new_chat(p: dict) -> dict:
    await _ensure()
    await st.page.goto("https://www.perplexity.ai", wait_until="load")
    await asyncio.sleep(2)
    st.last_resp = st.last_attr = st.detected_model = st.pending_attach = ""
    await broadcast("new_chat", {"status": "ok"})
    return {"success": True}

async def tool_list_models(p: dict) -> dict:
    return {"models": MODELS, "current": st.current_model, "detected": st.detected_model}

async def tool_check_login(p: dict) -> dict:
    await _ensure()
    li = await _check_login()
    st.logged_in = li
    mode = "CDP (real Chrome)" if st.cdp_mode else "Playwright (automation)"
    note = (
        "✓ Logged in successfully!"
        if li else
        "⚠ Not logged in. Please sign into Perplexity in the browser window."
    )
    await broadcast("browser_ready", {
        "logged_in": li,
        "url": st.page.url,
        "mode": mode,
        "note": note,
    })
    return {
        "logged_in": li, "mode": mode, "cdp_url": CDP_URL,
        "debug_profile": str(DEBUG_PROFILE), "automation_profile": str(AUTO_PROFILE),
        "chrome": CHROME_EXE or "playwright bundled chromium",
        "tip": (
            None if st.cdp_mode else
            f'Launch real Chrome first: google-chrome-stable --remote-debugging-port=9222 --user-data-dir="{DEBUG_PROFILE}" && restart server'
        ),
    }

TOOLS = {
    "send_message":      tool_send_message,
    "switch_model":      tool_switch_model,
    "upload_file":       tool_upload_file,
    "get_last_response": tool_get_last_response,
    "screenshot":        tool_screenshot,
    "new_chat":          tool_new_chat,
    "list_models":       tool_list_models,
    "check_login":       tool_check_login,
}

MCP_TOOL_DEFS = [
    {"name": "send_message", "description": "Type a message into Perplexity and return the AI response",
     "inputSchema": {"type": "object", "properties": {"message": {"type": "string"}, "timeout": {"type": "integer", "default": 90}}, "required": ["message"]}},
    {"name": "switch_model", "description": "Switch the active Perplexity model",
     "inputSchema": {"type": "object", "properties": {"model": {"type": "string", "enum": MODELS}}, "required": ["model"]}},
    {"name": "upload_file", "description": "Upload a file from uploads/ folder into the Perplexity chat",
     "inputSchema": {"type": "object", "properties": {"filename": {"type": "string"}, "original": {"type": "string"}}, "required": ["filename"]}},
    {"name": "get_last_response", "description": "Retrieve the last response received from Perplexity",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "screenshot", "description": "Take a screenshot of the current browser state",
     "inputSchema": {"type": "object", "properties": {"full_page": {"type": "boolean", "default": False}}}},
    {"name": "new_chat", "description": "Navigate to Perplexity home to start a fresh conversation",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_models", "description": "List all available Perplexity models and the currently active one",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "check_login", "description": "Check whether Perplexity is currently logged in and show connection mode",
     "inputSchema": {"type": "object", "properties": {}}},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(launch_browser())
    def _done(t):
        if not t.cancelled() and t.exception():
            log.error(f"[LIFESPAN] Browser task crashed: {t.exception()}")
    task.add_done_callback(_done)
    yield
    if not task.done(): task.cancel()
    if st.ctx and not st.cdp_mode:
        try: await st.ctx.close()
        except: pass
    if st.pw:
        try: await st.pw.stop()
        except: pass

app = FastAPI(title="Hermes-Perplexity MCP", version="9.5.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/sse")
async def sse_ep(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    clients.append(q)
    await q.put(json.dumps({"type": "mcp_init", "version": "9.5.1", "tools": MCP_TOOL_DEFS, "models": MODELS}))
    async def gen():
        try:
            while True:
                if await request.is_disconnected(): break
                try:
                    yield {"data": await asyncio.wait_for(q.get(), timeout=25)}
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"type": "ping", "ts": time.time()})}
        finally:
            if q in clients: clients.remove(q)
    return EventSourceResponse(gen())

class MCPReq(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: dict = {}

@app.post("/mcp")
async def mcp_ep(req: MCPReq):
    if req.method == "initialize":
        return {"jsonrpc": "2.0", "id": req.id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hermes-perplexity", "version": "9.5.1"}}}
    if req.method == "tools/list":
        return {"jsonrpc": "2.0", "id": req.id, "result": {"tools": MCP_TOOL_DEFS}}
    if req.method == "tools/call":
        nm = req.params.get("name")
        ag = req.params.get("arguments", {})
        if nm not in TOOLS:
            return {"jsonrpc": "2.0", "id": req.id, "error": {"code": -32601, "message": f"Unknown tool: {nm}"}}
        r = await TOOLS[nm](ag)
        return {"jsonrpc": "2.0", "id": req.id, "result": {"content": [{"type": "text", "text": json.dumps(r)}]}}
    return {"jsonrpc": "2.0", "id": req.id, "error": {"code": -32601, "message": f"Unknown method: {req.method}"}}

@app.post("/upload")
async def up_ep(file: UploadFile = File(...)):
    safe = f"{uuid.uuid4().hex}_{file.filename}"
    content = await file.read()
    async with aiofiles.open(UPLOADS / safe, "wb") as f:
        await f.write(content)
    await broadcast("file_uploaded", {"filename": safe, "original": file.filename, "size": len(content)})
    return {"filename": safe, "original": file.filename, "size": len(content)}

@app.get("/download/{filename}")
async def dl_ep(filename: str):
    p = DOWNLOADS / filename
    if not p.exists(): raise HTTPException(404, "File not found")
    return FileResponse(str(p), filename=filename)

@app.get("/downloads")
async def dls_ep():
    files = sorted(
        [{"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime}
         for f in DOWNLOADS.iterdir() if f.is_file()],
        key=lambda x: -x["modified"])
    return {"files": files}

@app.get("/status")
async def status_ep():
    return {
        "browser_ready": st.ready, "logged_in": st.logged_in,
        "mode": "CDP (real Chrome)" if st.cdp_mode else "Playwright (automation)",
        "cdp_url": CDP_URL, "current_model": st.current_model,
        "detected_model": st.detected_model, "sse_clients": len(clients),
        "chrome_exe": CHROME_EXE or "playwright bundled chromium",
        "debug_profile": str(DEBUG_PROFILE), "automation_profile": str(AUTO_PROFILE),
        "last_response_length": len(st.last_resp), "version": "9.5.1",
    }

@app.get("/screenshot/latest")
async def latest_shot():
    shots = sorted(DOWNLOADS.glob("screenshot_*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not shots: raise HTTPException(404, "No screenshots yet")
    return FileResponse(str(shots[0]))

DASHBOARD_DIR = BASE_DIR / "dashboard"
app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mcp_server:app", host="0.0.0.0", port=3456, reload=False)
