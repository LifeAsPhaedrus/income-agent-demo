"""Start a detached Mac dashboard and open the default browser."""

import argparse
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8766"


def alive():
    try:
        with build_opener(ProxyHandler({})).open(URL + "/health", timeout=1) as r:
            return json.load(r).get("app") == "income-agent-local"
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-open", action="store_true")
    args = p.parse_args()
    if not alive():
        with (ROOT / "dashboard.log").open("a") as log:
            subprocess.Popen(
                [sys.executable, str(ROOT / "mac_dashboard.py")],
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                close_fds=True,
            )
        for _ in range(30):
            if alive():
                break
            time.sleep(0.2)
        else:
            raise SystemExit(
                "Could not start dashboard. See dashboard.log; port 8766 may be in use."
            )
    if not args.no_open:
        webbrowser.open(URL)
    print("Income Opportunities is running independently at " + URL)


if __name__ == "__main__":
    main()
