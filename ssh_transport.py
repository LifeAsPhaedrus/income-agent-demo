"""Fixed remote entry points for the Mac app. Payloads travel on stdin."""

import os
from pathlib import Path

HOST = os.environ.get("INCOME_AGENT_SSH_HOST", "income-agent-server")
KEY = Path(
    os.environ.get(
        "INCOME_AGENT_SSH_KEY",
        str(Path(__file__).resolve().parent.parent.parent / "demo-private/id_ed25519"),
    )
)
SCRIPTS = frozenset(("ui_bridge.py", "search_watch.py", "proposal_draft.py"))


def command(script, key=KEY):
    if script not in SCRIPTS:
        raise ValueError("Remote entry point refused")
    return [
        "ssh",
        "-i",
        str(key),
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        HOST,
        'cd "$HOME/income-agent" && python3 -u ' + script,
    ]
