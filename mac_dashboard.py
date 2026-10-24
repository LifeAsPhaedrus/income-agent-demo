"""Mac-only loopback dashboard. Uses SSH to the private Ubuntu review bridge."""

import argparse
import json
import secrets
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import excel_feed
from domain import valid_listing_id
from ssh_transport import KEY
from ssh_transport import command as ssh_command

ROOT = Path(__file__).resolve().parent

PORT = 8766
LOCK = threading.Lock()
JOB_LOCK = threading.Lock()
JOB = {"running": False, "log": "", "status": "Ready"}


def research(query, proposal=False):
    def append(text):
        with JOB_LOCK:
            JOB["log"] = (JOB["log"] + text)[-60000:]

    try:
        command = ssh_command(
            "proposal_draft.py" if proposal else "search_watch.py", KEY
        )
        with subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        ) as process:
            process.stdin.write(json.dumps(query if proposal else {"query": query}))
            process.stdin.close()
            timer = threading.Timer(600, process.kill)
            timer.start()
            try:
                while True:
                    chunk = process.stdout.read(1)
                    if not chunk:
                        break
                    append(chunk)
                code = process.wait()
            finally:
                timer.cancel()
        with JOB_LOCK:
            JOB["status"] = "Complete" if code == 0 else "Stopped — see progress below"
    except Exception:
        append("Connection interrupted. Refresh to check the latest completed results.")
        with JOB_LOCK:
            JOB["status"] = "Connection failed"
    finally:
        with JOB_LOCK:
            JOB["running"] = False


def local_action(request):
    action = request.get("action")
    if action == "proposal_start":
        if (
            not valid_listing_id(request.get("id"), "freelancer")
            or type(request.get("version")) is not int
        ):
            raise ValueError("Invalid proposal request")
        with JOB_LOCK:
            if JOB["running"]:
                raise ValueError("Another search or draft is running")
            JOB.update(running=True, log="", status="Drafting with Qwen")
        threading.Thread(target=research, args=(request, True), daemon=True).start()
        with JOB_LOCK:
            return dict(JOB)
    if action == "start":
        query = request.get("query", "Excel dashboard")
        if (
            not isinstance(query, str)
            or not 2 <= len(query) <= 100
            or any(ord(c) < 32 for c in query)
        ):
            raise ValueError("Enter a search of 2–100 characters")
        with JOB_LOCK:
            if JOB["running"]:
                raise ValueError("A search is already running")
            JOB.update(running=True, log="", status="Searching")
        threading.Thread(target=research, args=(query,), daemon=True).start()
    if action in ("start", "progress"):
        with JOB_LOCK:
            return dict(JOB)
    return remote(request)


def remote(request):
    with LOCK:
        result = subprocess.run(
            ssh_command("ui_bridge.py", KEY),
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=120,
        )
    if result.returncode:
        raise ValueError(
            "Ubuntu connection unavailable or report not ready. Check that the configured server is awake and reachable."
        )
    return json.loads(result.stdout)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, kind="application/json"):
        payload = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("OData-Version", "4.0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.end_headers()
        self.wfile.write(payload)

    def host_ok(self):
        return self.headers.get("Host") == f"127.0.0.1:{PORT}"

    def do_GET(self):
        if not self.host_ok():
            return self.send(403, {"error": "Invalid host"})
        if self.path.startswith("/excel/"):
            try:
                code, body, kind = excel_feed.route(
                    self.path, self.server.excel_key, remote
                )
                return self.send(code, body, kind)
            except Exception:
                return self.send(
                    503,
                    {
                        "error": "Could not refresh from Ubuntu PostgreSQL. Check the agent and server connection."
                    },
                )
        if self.path == "/":
            return self.send(200, (ROOT / "dashboard.html").read_text(), "text/html")
        if self.path.split("?")[0] == "/proposal.html":
            return self.send(200, (ROOT / "proposal.html").read_text(), "text/html")
        if self.path == "/proposal.js":
            return self.send(200, (ROOT / "proposal.js").read_text(), "text/javascript")
        if self.path == "/app.js":
            return self.send(
                200, (ROOT / "dashboard.js").read_text(), "text/javascript"
            )
        if self.path == "/session":
            return self.send(200, {"token": self.server.csrf})
        if self.path == "/health":
            return self.send(200, {"app": "income-agent-local"})
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        if (
            not self.host_ok()
            or self.headers.get("Origin") != f"http://127.0.0.1:{PORT}"
            or not secrets.compare_digest(
                self.headers.get("X-Review-Token", ""), self.server.csrf
            )
        ):
            return self.send(403, {"error": "Request refused"})
        if self.path != "/api":
            return self.send(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Invalid request size")
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict) or request.get("action") not in (
                "snapshot",
                "review",
                "start",
                "progress",
                "export",
                "proposal_get",
                "proposal_save",
                "proposal_export",
                "proposal_start",
                "bid_prepare",
                "bid_submit",
                "bid_status",
            ):
                raise ValueError("Invalid request")
            self.send(200, local_action(request))
        except Exception as error:
            self.send(
                503,
                {
                    "error": str(error)
                    if isinstance(error, ValueError)
                    else "Could not reach Ubuntu. Try again."
                },
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.csrf = secrets.token_urlsafe(32)
    server.excel_key = excel_feed.key(ROOT)
    print(
        f"Income Opportunities: http://127.0.0.1:{PORT} — Ctrl+C closes this local window service.",
        flush=True,
    )
    if args.open:
        threading.Timer(
            0.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")
        ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
