"""Single-endpoint GET-only Freelancer search. No SDK write capabilities."""

import argparse
import json
import os
import re
import stat
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener

from file_store import write_json_atomic
from http_safety import NoRedirect as NoRedirect
from http_safety import SourceConnectionError as ConnectionError

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT.parent.parent / "demo-private/freelancer-token"
ENDPOINT = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def read_token(path=None):
    path = (
        Path(os.environ.get("INCOME_AGENT_TOKEN_FILE", str(TOKEN_FILE)))
        if path is None
        else Path(path)
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o077
            or info.st_uid != os.getuid()
        ):
            raise ConnectionError("Token must be an owner-only regular file")
        token = stream.read(4097).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.~+/=-]{28,4096}", token):
        raise ConnectionError("Invalid local token format")
    return token


def search(query, limit=10):
    if (
        not isinstance(query, str)
        or not 2 <= len(query) <= 100
        or type(limit) is not int
        or not 1 <= limit <= 20
    ):
        raise ConnectionError("Search requires 2–100 characters and limit 1–20")
    token = read_token()
    url = (
        ENDPOINT
        + "?"
        + urlencode(
            {"query": query, "limit": limit, "offset": 0, "full_description": "true"}
        )
    )
    req = Request(
        url,
        method="GET",
        headers={"Freelancer-OAuth-V1": token, "Accept": "application/json"},
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            req, timeout=15
        ) as response:
            if response.headers.get_content_type() != "application/json":
                raise ConnectionError("Expected JSON")
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ConnectionError("Response too large")
        payload = json.loads(raw)
        rows = payload.get("result", {}).get("projects")
        if payload.get("status") != "success" or not isinstance(rows, list):
            raise ConnectionError("Unexpected response schema")
        return rows
    except HTTPError as error:
        error.close()
        raise ConnectionError(
            f"Freelancer HTTP {error.code}; no automatic retry. Renew token for 401/403; wait for 429."
        ) from None
    except ConnectionError:
        raise
    except Exception:
        # Never log exception bodies or requests, which can contain authentication data.
        raise ConnectionError(
            "Freelancer connection failed; check network and trusted TLS certificates"
        ) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="Excel inventory")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    data = ROOT / "data"
    data.mkdir(exist_ok=True)
    lock = data / "freelancer.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        parser.exit(1, "Another search is active; inspect stale lock if needed.\n")
    try:
        with handle:
            state = data / "freelancer-last-attempt.json"
            now = time.time()
            if state.exists() and now - json.loads(state.read_text())["time"] < 60:
                raise ConnectionError(
                    "Wait at least 60 seconds between manual searches"
                )
            state.write_text(json.dumps({"time": now}))
            rows = search(args.query, args.limit)
            report = {
                "source": "Freelancer",
                "query": args.query,
                "fetched_at_epoch": now,
                "count": len(rows),
                "verification": "Unverified source listings; budgets are not guaranteed earnings. No bids submitted.",
                "projects": rows,
            }
            write_json_atomic(ROOT / "freelancer-results.json", report)
            print(
                f"Read-only search succeeded: {len(rows)} projects. Saved freelancer-results.json"
            )
            for row in rows[:3]:
                print(
                    json.dumps(
                        {
                            k: row.get(k)
                            for k in (
                                "id",
                                "title",
                                "type",
                                "budget",
                                "currency",
                                "seo_url",
                            )
                        },
                        ensure_ascii=True,
                    )
                )
    except (ValueError, OSError):
        parser.exit(
            1,
            "Search did not complete. Check network, token permissions/expiry, and local cooldown. No automatic retry.\n",
        )
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
