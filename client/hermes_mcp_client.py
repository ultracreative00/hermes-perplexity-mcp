"""
Hermes MCP Client v9
Usage:
  python hermes_mcp_client.py
  python hermes_mcp_client.py --message "What is quantum computing?"
  python hermes_mcp_client.py --model "GPT-4o" --message "Explain relativity"
  python hermes_mcp_client.py --upload /path/to/file.pdf --message "Summarise this"
"""
import argparse, json
import httpx

BASE = "http://localhost:3456"

def call(method: str, name: str, arguments: dict = {}) -> dict:
    r = httpx.post(f"{BASE}/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": method,
        "params": {"name": name, "arguments": arguments},
    }, timeout=120)
    j = r.json()
    if "error" in j:
        return {"error": j["error"]}
    return json.loads(j["result"]["content"][0]["text"])

def upload(path: str) -> str:
    with open(path, "rb") as f:
        r = httpx.post(f"{BASE}/upload", files={"file": f}, timeout=30)
    return r.json()["filename"]

def main():
    ap = argparse.ArgumentParser(description="Hermes → Perplexity MCP Client v9")
    ap.add_argument("--message",  "-m", help="Message to send")
    ap.add_argument("--model",    "-M", help="Model to use",
                    choices=["Default","Claude Sonnet 4.5","GPT-4o",
                             "Gemini 2.0 Flash","Sonar Pro","Sonar","R1 1776"])
    ap.add_argument("--upload",   "-u", help="File to upload before sending")
    ap.add_argument("--status",   "-s", action="store_true", help="Show server status")
    ap.add_argument("--models",   "-l", action="store_true", help="List models")
    ap.add_argument("--new-chat", "-n", action="store_true", help="Start new chat")
    ap.add_argument("--screenshot", action="store_true", help="Take screenshot")
    args = ap.parse_args()

    if args.status:
        r = httpx.get(f"{BASE}/status", timeout=10).json()
        print(json.dumps(r, indent=2)); return
    if args.models:
        r = call("tools/call", "list_models")
        print("Available:", r["models"])
        print("Current  :", r["current"]); return
    if args.new_chat:
        print("New chat:", call("tools/call", "new_chat")); return
    if args.screenshot:
        print("Screenshot:", call("tools/call", "screenshot")); return
    if args.model:
        print(f"Switching model → {args.model}")
        print("Result:", call("tools/call", "switch_model", {"model": args.model}))
    if args.upload:
        print(f"Uploading {args.upload} …")
        fname = upload(args.upload)
        print(f"Uploaded as: {fname}")
        print("Sent to browser:", call("tools/call", "upload_file", {"filename": fname}))
    if args.message:
        print(f"Sending: {args.message[:60]}…")
        r = call("tools/call", "send_message", {"message": args.message})
        if "error" in r:
            print("Error:", r["error"]); return
        print(f"\n── Response [{r.get('model','?')}] ──")
        print(r.get("response", ""))
        if r.get("attribution"):
            print(f"\n[{r['attribution']}]")
        return
    ap.print_help()

if __name__ == "__main__":
    main()
