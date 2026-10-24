"""Public GET-only Remotive feed, cached at least six hours; no credentials."""

import json
import signal
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from file_store import write_json_atomic
from http_safety import NoRedirect
from research import plain


def fetch(root):
    path = root / "remotive-results.json"
    state = root / "data/remotive-last-attempt.json"
    now = time.time()
    if state.exists() and now - json.loads(state.read_text())["time"] < 21600:
        if path.exists():
            return json.loads(path.read_text()), "Cached feed (six-hour refresh limit)"
        raise ValueError("Remotive cooldown after prior attempt")
    state.parent.mkdir(exist_ok=True)
    state.write_text(json.dumps({"time": now}))
    req = Request(
        "https://remotive.com/api/remote-jobs",
        headers={
            "Accept": "application/json",
            "User-Agent": "PersonalOpportunityResearch/1.0",
        },
    )

    def expired(*_):
        raise TimeoutError("Remotive overall deadline exceeded")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(45)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=20) as r:
            raw = r.read(20 * 1024 * 1024 + 1)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Feed too large")
    data = json.loads(raw)
    if not isinstance(data.get("jobs"), list):
        raise ValueError("Unexpected feed")
    result = {"fetched_at_epoch": now, "jobs": data["jobs"]}
    write_json_atomic(path, result)
    return result, "Connected; source listings delayed 24 hours"


def normalize(rows, query=""):
    result = []
    for p in rows:
        try:
            if type(p["id"]) is not int:
                continue
            u = urlsplit(p["url"])
            if (
                u.scheme != "https"
                or u.hostname not in ("remotive.com", "www.remotive.com")
                or u.username
                or u.password
                or u.port not in (None, 443)
            ):
                continue
            text = plain(p["description"])
            title = plain(p["title"])
            # Local keyword filtering avoids extra API requests. Accept any query word.
            words = [w.lower() for w in query.split() if len(w) > 2]
            if words and not any(w in (title + " " + text).lower() for w in words):
                continue
            date = datetime.fromisoformat(p["publication_date"].replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            location = p.get("candidate_required_location", "")
            import re

            allowed = bool(
                re.search(
                    r"worldwide|anywhere|united states|\busa\b|\bus\b|north america",
                    location,
                    re.I,
                )
            )
            result.append(
                {
                    "id": p["id"],
                    "source": "Remotive",
                    "url": p["url"],
                    "title": title,
                    "description": text,
                    "status": "active",
                    "language": "en",
                    "local": not allowed,
                    "time_submitted": date.timestamp(),
                    "type": p.get("job_type") or "unknown",
                    "currency": {"code": "unknown"},
                    "budget": {},
                    "salary_text": p.get("salary") or "Not disclosed",
                    "location": location,
                    "company": p.get("company_name"),
                    "source_notice": "Remotive public API: listings delayed 24 hours. Confirm employer, geography and current availability.",
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return result
