"""Run the public demo with fictional data and no marketplace or SSH connections."""

import argparse
import json
import secrets
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import mac_dashboard
import ui_bridge
import workflow
from file_store import write_json_atomic

ROOT = Path(__file__).resolve().parent


def prepare(directory, use_model=False):
    directory = Path(directory)
    marker = directory / "synthetic-demo.marker"
    if directory.exists() and any(directory.iterdir()) and not marker.exists():
        raise ValueError(
            "Refusing an existing non-demo directory; choose a new output folder"
        )
    directory.mkdir(parents=True, exist_ok=True)
    marker.write_text("Fictional demonstration state only.\n")
    if (directory / "postgres-enabled").exists():
        raise ValueError("PostgreSQL cannot be enabled in the public demo")
    profile = json.loads((ROOT / "fixtures/demo-profile.json").read_text())
    projects = json.loads((ROOT / "fixtures/demo-projects.json").read_text())
    now = time.time()
    for project in projects:
        project["time_submitted"] = now
    write_json_atomic(directory / "user-profile.json", profile)
    write_json_atomic(
        directory / "freelancer-results.json",
        {"query": "synthetic demo", "fetched_at_epoch": now, "projects": projects},
    )
    write_json_atomic(
        directory / "source-status.json",
        {"Demo": "Fictional data; no marketplace connection"},
    )
    return workflow.build(directory, use_model=use_model)


def dispatch(request, directory):
    action = request.get("action")
    if (directory / "postgres-enabled").exists():
        raise ValueError("PostgreSQL is disabled in the demo")
    if action in ("snapshot", "review"):
        result = ui_bridge.dispatch(request, directory)
        result["database_status"] = (
            "SYNTHETIC DEMO — decisions saved only in this demo's SQLite file"
        )
        return result
    if action == "progress":
        return {
            "running": False,
            "status": "Offline demo",
            "log": "Fictional listings. No applications, SSH or live sources.",
        }
    if action == "start":
        prepare(directory)
        return {
            "running": False,
            "status": "Samples refreshed",
            "log": "Reloaded fictional sample listings.",
        }
    if action == "export":
        return {
            "rows": [
                p
                for p in dispatch({"action": "snapshot"}, directory)["history"]
                if p["status"] == "saved"
            ]
        }
    raise ValueError(
        "This public demo supports local review only; live actions are disabled"
    )


def refuse_remote(*args, **kwargs):
    raise ValueError("Remote connections are disabled in the public demo")


def serve(directory, port):
    mac_dashboard.PORT = port
    mac_dashboard.local_action = lambda request: dispatch(request, directory)
    mac_dashboard.remote = refuse_remote
    server = ThreadingHTTPServer(("127.0.0.1", port), mac_dashboard.Handler)
    server.csrf = secrets.token_urlsafe(32)
    # Never reads the private app's Excel key or serves its data.
    server.excel_key = secrets.token_urlsafe(32)
    print(f"Synthetic review demo: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".demo")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument(
        "--qwen",
        action="store_true",
        help="Optionally send fictional text to local Ollama; never to a cloud model",
    )
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535")
    report = prepare(args.output, args.qwen)
    print(
        json.dumps(
            {
                "mode": "synthetic demo",
                "shortlisted": len(report["top_three"]),
                "report": str(args.output / "OPPORTUNITIES.html"),
            },
            indent=2,
        )
    )
    if args.serve:
        serve(args.output, args.port)


if __name__ == "__main__":
    main()
