"""Dedicated Unix-socket PostgreSQL mirror. Never uses ambient PG settings."""

import fcntl
import json
import os
import subprocess
from pathlib import Path

BASE = Path.home() / ".local/share/income-agent-demo-postgres"
BIN = Path("/usr/lib/postgresql/18/bin")


def sql(statement):
    # Restart this dedicated cluster on demand after an Ubuntu reboot.
    with (BASE / "startup.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if subprocess.run(
            [str(BIN / "pg_ctl"), "-D", str(BASE / "data"), "status"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode:
            subprocess.run(
                [
                    str(BIN / "pg_ctl"),
                    "-D",
                    str(BASE / "data"),
                    "-l",
                    str(BASE / "server.log"),
                    "-w",
                    "start",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=15,
            )
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env["PGCONNECT_TIMEOUT"] = "3"
    result = subprocess.run(
        [
            str(BIN / "psql"),
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(BASE / "socket"),
            "-p",
            "55439",
            "-U",
            os.environ.get("USER", "income_agent"),
            "-d",
            "income_agent",
        ],
        input=statement,
        text=True,
        capture_output=True,
        timeout=12,
        env=env,
    )
    if result.returncode:
        raise RuntimeError("Agent PostgreSQL unavailable")
    return result.stdout.strip()


def sync(rows):
    # Hex transport prevents source text from becoming SQL syntax.
    payload = json.dumps(rows, ensure_ascii=True).encode().hex()
    sql(
        "BEGIN; SELECT pg_advisory_xact_lock(481932); CREATE TABLE IF NOT EXISTS gigs(id text PRIMARY KEY, record jsonb NOT NULL, synced_at timestamptz NOT NULL DEFAULT now()); INSERT INTO gigs(id,record) SELECT r->>'id',r FROM jsonb_array_elements(convert_from(decode('"
        + payload
        + "','hex'),'UTF8')::jsonb) r ON CONFLICT(id) DO UPDATE SET record=excluded.record,synced_at=now() WHERE gigs.record IS DISTINCT FROM excluded.record; COMMIT;"
    )


def selected():
    return json.loads(
        sql(
            "SELECT coalesce(jsonb_agg(record ORDER BY id),'[]'::jsonb) FROM gigs WHERE record->>'status'='saved';"
        )
    )


def excel_rows():
    return json.loads(
        sql(
            "SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY listing_id),'[]'::jsonb) FROM public.excel_pursue p;"
        )
    )
