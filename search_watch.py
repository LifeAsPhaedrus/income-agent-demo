"""Fixed, read-only research pipeline invoked through SSH."""

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from file_store import write_json_atomic

ROOT = Path(__file__).resolve().parent


def main():
    request = json.loads(sys.stdin.read(8193))
    query = request.get("query", "Excel dashboard")
    if (
        not isinstance(query, str)
        or not 2 <= len(query) <= 100
        or any(ord(c) < 32 for c in query)
    ):
        raise ValueError("Invalid query")
    with (ROOT / "research-run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another window search is already running.", flush=True)
            return 1
        os.environ["INCOME_AGENT_TOKEN_FILE"] = str(
            Path.home() / ".config/income-agent-demo/freelancer-token"
        )
        print("Searching Freelancer (read-only)…", flush=True)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "freelancer_source.py",
                    "--query",
                    query,
                    "--limit",
                    "20",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=40,
            )
            freelancer_ok = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            freelancer_ok = False
        if not freelancer_ok:
            print(
                "Freelancer unavailable; retaining its previous snapshot.", flush=True
            )
        statuses = {
            "Freelancer": "Connected"
            if freelancer_ok
            else "Refresh failed; previous matching-query snapshot retained"
        }
        print("Searching Remotive (public API; six-hour cache)…", flush=True)
        try:
            from remotive_source import fetch

            _, statuses["Remotive"] = fetch(ROOT)
        except Exception:
            statuses["Remotive"] = (
                "Refresh failed or cooldown; previous fresh snapshot retained"
            )
        print("Searching Contra (authorized read-only job feed)…", flush=True)
        try:
            from contra_source import fetch as fetch_contra

            _, statuses["Contra"] = fetch_contra(ROOT, query)
        except Exception:
            statuses["Contra"] = (
                "Refresh failed; check authorization. Previous fresh matching-query snapshot retained."
            )
        write_json_atomic(ROOT / "source-status.json", statuses)
        print(json.dumps(statuses), flush=True)
        print(
            "Listings received. Ranking for your skills; Qwen is extracting source evidence…",
            flush=True,
        )
        import workflow

        report = workflow.build(ROOT, use_model=True, watch=True, query=query)
        print(
            "\nComplete: "
            + str(len(report["top_three"]))
            + " new shortlisted leads. Refreshing your results.",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(
            "Research stopped safely. Previous completed results are still available.",
            flush=True,
        )
        sys.exit(1)
