"""Initialize only a dedicated user-owned cluster; no existing services touched."""

import os
import subprocess

from postgres_store import BASE, BIN

BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(BASE, 0o700)
data = BASE / "data"
socket = BASE / "socket"
socket.mkdir(exist_ok=True, mode=0o700)
if not (data / "PG_VERSION").exists():
    subprocess.run(
        [
            str(BIN / "initdb"),
            "-D",
            str(data),
            "--auth-local=peer",
            "--auth-host=reject",
            "--encoding=UTF8",
            "--no-locale",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    with (data / "postgresql.conf").open("a") as f:
        f.write(
            "\nlisten_addresses = ''\nport = 55439\nunix_socket_directories = '"
            + str(socket)
            + "'\nunix_socket_permissions = 0700\nmax_connections = 10\nshared_buffers = '32MB'\n"
        )
if subprocess.run(
    [str(BIN / "pg_ctl"), "-D", str(data), "status"], stdout=subprocess.DEVNULL
).returncode:
    subprocess.run(
        [
            str(BIN / "pg_ctl"),
            "-D",
            str(data),
            "-l",
            str(BASE / "server.log"),
            "-w",
            "start",
        ],
        check=True,
    )
# createdb is confined to this socket. Existing database is left intact.
r = subprocess.run(
    [
        str(BIN / "psql"),
        "-XAt",
        "-h",
        str(socket),
        "-p",
        "55439",
        "-d",
        "postgres",
        "-c",
        "SELECT 1 FROM pg_database WHERE datname='income_agent'",
    ],
    capture_output=True,
    text=True,
    check=True,
)
if r.stdout.strip() != "1":
    subprocess.run(
        [str(BIN / "createdb"), "-h", str(socket), "-p", "55439", "income_agent"],
        check=True,
    )
print("Dedicated income-agent PostgreSQL ready (private Unix socket only).")
