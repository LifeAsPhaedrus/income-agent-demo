"""Read-only, single-source Jobicy client. No credentials or application actions."""

import hashlib
import ipaddress
import json
import socket
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ENDPOINT = "https://jobicy.com/api/jobs?count=100"
MAX_BYTES = 1024 * 1024


class SourceError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceError(
            "Redirect refused; only the configured Jobicy endpoint is allowed"
        )


def validate_payload(payload):
    if (
        not isinstance(payload, dict)
        or payload.get("success") is False
        or not isinstance(payload.get("jobs"), list)
    ):
        raise SourceError("Unexpected Jobicy response schema")
    if len(payload["jobs"]) > 100:
        raise SourceError("Unexpected page size")
    return payload


def download():
    addresses = socket.getaddrinfo("jobicy.com", 443, type=socket.SOCK_STREAM)
    if not addresses or any(
        not ipaddress.ip_address(a[4][0]).is_global for a in addresses
    ):
        raise SourceError("Non-public source address refused")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    req = Request(
        ENDPOINT,
        headers={
            "Accept": "application/json",
            "User-Agent": "LocalIncomeResearch/0.1 (personal read-only research)",
        },
        method="GET",
    )
    with opener.open(req, timeout=10) as response:
        if response.headers.get_content_type() != "application/json":
            raise SourceError("Expected JSON content type")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise SourceError("Response exceeds 1 MiB")
    return validate_payload(json.loads(raw))


def fetch(directory, now=None, transport=None):
    """One request per hour, including failed attempts. Concurrent runs fail closed."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    cache = directory / "jobicy-cache.json"
    state = directory / "jobicy-state.json"
    lock = directory / "jobicy.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise SourceError("Another fetch is active (or a stale lock needs inspection)")
    try:
        with handle:
            previous = json.loads(state.read_text()) if state.exists() else {}
            if now < previous.get("next_allowed", 0):
                if cache.exists():
                    saved = json.loads(cache.read_text())
                    validate_payload(saved["payload"])
                    return dict(saved, cached=True, warning=previous.get("error"))
                raise SourceError("Rate limit: wait until the next permitted fetch")
            state.write_text(json.dumps({"next_allowed": now + 3600}))
            try:
                payload = validate_payload((transport or download)())
            except Exception as error:
                delay = 3600
                if isinstance(error, HTTPError) and error.code == 429:
                    retry = error.headers.get("Retry-After", "")
                    if retry.isdigit():
                        delay = max(delay, int(retry))
                    elif retry:
                        try:
                            delay = max(
                                delay, parsedate_to_datetime(retry).timestamp() - now
                            )
                        except (ValueError, TypeError, OverflowError):
                            pass
                if isinstance(error, HTTPError):
                    error.close()
                state.write_text(
                    json.dumps({"next_allowed": now + delay, "error": str(error)})
                )
                raise SourceError(
                    f"Jobicy fetch failed; no automatic retry: {error}"
                ) from error
            saved = {
                "fetched_at": now,
                "endpoint": ENDPOINT,
                "payload": payload,
                "sha256": hashlib.sha256(
                    json.dumps(payload, sort_keys=True).encode()
                ).hexdigest(),
            }
            temp = directory / "jobicy-cache.tmp"
            temp.write_text(json.dumps(saved))
            temp.replace(cache)
            return dict(saved, cached=False, warning=None)
    finally:
        lock.unlink(missing_ok=True)
