"""Contra OAuth/MCP adapter. Exactly two read-only tools; credentials never reach Qwen."""

import fcntl
import hashlib
import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from file_store import write_json_atomic
from http_safety import NoRedirect
from research import plain

TOKEN = Path.home() / ".config/income-agent-demo/contra-oauth.json"
TOOLS = frozenset(("list_job_feed", "get_job_by_slug"))


def atomic(path, value, private=False):
    """Compatibility wrapper; all atomic JSON files are owner-only."""
    write_json_atomic(path, value)


def request(url, body, token=None, form=False):
    if url not in ("https://contra.com/mcp", "https://contra.com/api/mcp/oauth/token"):
        raise ValueError("Endpoint not permitted")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
        if form
        else "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = urlencode(body).encode() if form else json.dumps(body).encode()
    with build_opener(ProxyHandler({}), NoRedirect()).open(
        Request(url, data=data, headers=headers), timeout=20
    ) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Response too large")
    text = raw.decode()
    if text.startswith(("event:", "data:")):
        return [
            json.loads(line[5:].strip())
            for line in text.splitlines()
            if line.startswith("data:")
        ][-1]
    return json.loads(text)


def access_token(path=TOKEN):
    with path.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = json.loads(path.read_text())
        if (
            time.time()
            >= data.get("received_at", 0) + float(data.get("expires_in", 0)) - 120
        ):
            if not data.get("refresh_token"):
                raise ValueError("Contra reconnect required")
            updated = request(
                "https://contra.com/api/mcp/oauth/token",
                {
                    "grant_type": "refresh_token",
                    "refresh_token": data["refresh_token"],
                    "client_id": data["client_id"],
                    "resource": "https://contra.com/mcp",
                },
                form=True,
            )
            if not updated.get("access_token"):
                raise ValueError("Contra refresh failed")
            data.update(updated)
            data["received_at"] = time.time()
            atomic(path, data, True)
        return data["access_token"]


def call_tool(name, arguments):
    if name not in TOOLS:
        raise ValueError("Contra tool not permitted")
    if name == "list_job_feed":
        if set(arguments) - {
            "preset",
            "search",
            "first",
            "after",
            "sort",
        } or arguments.get("preset") not in ("ALL", "FOR_YOU"):
            raise ValueError("Only opportunity research permitted")
    elif set(arguments) != {"slug"}:
        raise ValueError("Invalid listing arguments")
    payload = request(
        "https://contra.com/mcp",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        access_token(),
    )
    result = payload.get("result", {})
    if payload.get("error") or result.get("isError"):
        raise ValueError("Contra read failed")
    data = result.get("structuredContent")
    if data is None:
        data = json.loads(
            next(
                c["text"] for c in result.get("content", []) if c.get("type") == "text"
            )
        )
    if not isinstance(data, dict) or data.get("ok") is False:
        raise ValueError("Invalid Contra result")
    return data


def fetch(root, query):
    cache = root / "contra-results.json"
    if cache.exists():
        prior = json.loads(cache.read_text())
        if (
            prior.get("query") == query
            and time.time() - prior.get("fetched_at_epoch", 0) < 3600
        ):
            return prior, "Connected; cached search" + (
                "; limited account feed" if prior.get("access_limited") else ""
            )
    feed = call_tool("list_job_feed", {"preset": "ALL", "search": query, "first": 20})
    jobs = []
    for entry in feed.get("entries", [])[:20]:
        job = entry.get("job", {})
        if job.get("slug"):
            detail = call_tool("get_job_by_slug", {"slug": job["slug"]})
            job = {**job, **detail.get("job", {})}
        jobs.append(job)
    result = {
        "query": query,
        "fetched_at_epoch": time.time(),
        "jobs": jobs,
        "access_limited": bool(feed.get("accessLimitedFeed")),
        "has_more": bool(feed.get("hasNextPage")),
    }
    atomic(cache, result)
    return result, "Connected; read-only" + (
        "; limited account feed" if result["access_limited"] else ""
    ) + ("; first 20 results only" if result["has_more"] else "")


def money(value):
    m = re.fullmatch(r"([A-Z]{3}):(\d+(?:\.\d+)?)", value or "")
    if not m:
        return None, None
    number = float(m[2])
    return (m[1], number) if math.isfinite(number) else (None, None)


def description_text(blocks):
    """Extract only visible text from BlockNote content; ignore IDs/metadata."""
    if not isinstance(blocks, list):
        return ""
    lines = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("text"), str):
            lines.append(block["text"])
        for key in ("content", "children"):
            value = description_text(block.get(key))
            if value:
                lines.append(value)
    return "\n".join(lines)


def normalize(jobs):
    rows = []
    for j in jobs:
        try:
            u = urlsplit(j["publicUrl"])
            if (
                u.scheme != "https"
                or u.hostname != "contra.com"
                or u.username
                or u.password
                or u.port not in (None, 443)
                or not u.path.startswith("/opportunity/")
            ):
                continue
            if not isinstance(j["jobId"], str) or not j["jobId"]:
                continue
            budget = j.get("budget") or {}
            c, low = money(budget.get("feeMin"))
            d, high = money(budget.get("feeMax"))
            if c != d:
                c, low, high = None, None, None
            kind = {
                "HourlyRateJobBudget": "hourly",
                "FixedRateJobBudget": "fixed",
                "MonthlyRateJobBudget": "monthly",
            }.get(budget.get("type"), "unknown")
            description = j.get("description")
            if not isinstance(description, str):
                description = description_text(j.get("blocknoteDescription"))
            country = (j.get("country") or {}).get("name")
            # Stable local key; never used as a Contra API job identifier.
            ident = int(hashlib.sha256(j["jobId"].encode()).hexdigest(), 16)
            rows.append(
                {
                    "id": ident,
                    "source": "Contra",
                    "source_job_id": j["jobId"],
                    "url": j["publicUrl"],
                    "title": plain(j["title"]),
                    "description": plain(description),
                    "status": "active" if j.get("status") == "POSTED" else "closed",
                    "language": None,
                    "local": False,
                    "time_submitted": datetime.fromisoformat(
                        j["createdAt"].replace("Z", "+00:00")
                    ).timestamp(),
                    "type": kind,
                    "currency": {"code": c or "unknown"},
                    "budget": {"minimum": low, "maximum": high},
                    "location": country,
                    "source_notice": "Contra account-visible feed. Location, remote eligibility and schedule require confirmation; country may describe the hirer. Fees and take-home unverified.",
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return rows
