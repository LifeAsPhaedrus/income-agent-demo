"""Explicitly reviewed bids only. Never called by research or Qwen."""

import fcntl
import hashlib
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

import postgres_store
import proposals
from freelancer_source import read_token
from http_safety import NoRedirect


def literal(value):
    return (
        "convert_from(decode('"
        + json.dumps(value).encode().hex()
        + "','hex'),'UTF8')::jsonb"
    )


def setup():
    postgres_store.sql(
        "CREATE TABLE IF NOT EXISTS proposal_versions(listing_id text,version integer,record jsonb NOT NULL,PRIMARY KEY(listing_id,version)); CREATE TABLE IF NOT EXISTS bid_submissions(listing_id text PRIMARY KEY,record jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now()); CREATE TABLE IF NOT EXISTS bid_events(event_id bigserial PRIMARY KEY,listing_id text,record jsonb,created_at timestamptz DEFAULT now());"
    )


def archive(s):
    setup()
    for d in s["versions"]:
        v = literal(
            {"id": s["listing"]["id"], "draft": d, "listing_url": s["listing"]["url"]}
        )
        postgres_store.sql(
            "INSERT INTO proposal_versions SELECT "
            + v
            + "->>'id',("
            + v
            + "->'draft'->>'version')::integer,"
            + v
            + " ON CONFLICT DO NOTHING;"
        )


def status(ident):
    setup()
    v = literal(ident)
    return json.loads(
        postgres_store.sql(
            "SELECT coalesce((SELECT record FROM bid_submissions WHERE listing_id="
            + v
            + "#>>'{}'),'{}'::jsonb);"
        )
    )


def record(ident, data):
    v = literal(data)
    i = literal(ident)
    postgres_store.sql(
        "BEGIN; INSERT INTO bid_events(listing_id,record) VALUES ("
        + i
        + "#>>'{}',"
        + v
        + "); INSERT INTO bid_submissions VALUES ("
        + i
        + "#>>'{}',"
        + v
        + ",now()) ON CONFLICT(listing_id) DO UPDATE SET record=excluded.record,updated_at=now(); COMMIT;"
    )


class Rejected(ValueError):
    pass


def api(path, payload=None):
    if not (
        path == "users/0.1/self/"
        or re.fullmatch(r"projects/0.1/projects/\d+/", path)
        or path.startswith("projects/0.1/bids/?")
        or path == "projects/0.1/bids/"
    ):
        raise ValueError("Endpoint refused")
    if payload is not None and path != "projects/0.1/bids/":
        raise ValueError("Write refused")
    token = read_token(Path.home() / ".config/income-agent-demo/freelancer-token")
    request = Request(
        "https://www.freelancer.com/api/" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Freelancer-OAuth-V1": token, "Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            request, timeout=15
        ) as r:
            raw = r.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("Oversized response")
        d = json.loads(raw)
        if d.get("status") != "success":
            raise ValueError("Unexpected response")
        return d["result"]
    except HTTPError as e:
        # 5xx may follow a successful write; never classify them as safe to retry.
        if e.code in (400, 401, 403, 404, 422, 429):
            try:
                d = json.loads(e.read(32768))
                message = str(d.get("message", "Request rejected"))[:600]
            except Exception:
                message = "Request rejected"
            raise Rejected("Freelancer HTTP " + str(e.code) + ": " + message) from None
        raise ValueError("Uncertain Freelancer response") from None


def prepare(root, request):
    s = proposals.get(root, request.get("id"))
    d = s["draft"]
    if type(request.get("version")) is not int or d["version"] != request["version"]:
        raise ValueError("Reload the latest saved proposal")
    terms = d.get("terms", {})
    if not terms or not d["body"] or not terms.get("days"):
        raise ValueError("Save proposal and delivery terms first")
    if request.get("milestone_percentage") != 100:
        raise ValueError("This version supports one 100% completion milestone only")
    archive(s)
    p = api("projects/0.1/projects/" + s["listing"]["id"].split(":")[1] + "/")
    if (
        p.get("status") != "active"
        or p.get("type") != "fixed"
        or p.get("currency", {}).get("code") != d["currency"]
    ):
        raise ValueError("Project is not active/fixed or currency changed")
    me = api("users/0.1/self/")
    payload = {
        "project_id": p["id"],
        "bidder_id": me["id"],
        "amount": d["amount"],
        "period": terms["days"],
        "description": d["body"],
        "milestone_percentage": 100,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {
        "fingerprint": digest,
        "version": d["version"],
        "payload": payload,
        "currency": d["currency"],
        "account": me.get("username"),
        "delivery": s["delivery"],
        "status": status(s["listing"]["id"]),
    }


def submit(root, request):
    if request.get("confirm") is not True:
        raise ValueError("Explicit submission confirmation required")
    with (root / "data/bid-submit.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ready = prepare(root, request)
        ident = request["id"]
        if request.get("fingerprint") != ready["fingerprint"]:
            raise ValueError("Bid changed; review again")
        old = ready["status"]
        if old and not (
            old.get("state") == "rejected" and request.get("retry_rejected") is True
        ):
            return {
                "submission": old,
                "message": "An attempt already exists. No second bid sent; review its receipt.",
            }
        # Paginate before sending; fail closed if we cannot inspect all existing bids.
        for offset in range(0, 2000, 100):
            result = api(
                "projects/0.1/bids/?projects%5B%5D="
                + str(ready["payload"]["project_id"])
                + "&limit=100&offset="
                + str(offset)
            )
            rows = result["bids"]
            own = [
                b for b in rows if b.get("bidder_id") == ready["payload"]["bidder_id"]
            ]
            if own:
                receipt = {
                    "state": "existing",
                    "bid_id": own[0]["id"],
                    "message": "An existing Freelancer bid was found. No new bid sent.",
                }
                record(ident, receipt)
                return {"submission": receipt}
            if len(rows) < 100:
                break
        else:
            raise ValueError("Could not finish checking existing bids")
        attempt = {**ready, "state": "submitting"}
        attempt.pop("status", None)
        record(ident, attempt)  # Durable before the only marketplace write.
        try:
            result = api("projects/0.1/bids/", ready["payload"])
            if not isinstance(result, dict) or not result.get("id"):
                raise ValueError("Missing receipt")
            attempt.update(
                state="submitted",
                bid_id=result["id"],
                receipt=result,
                message="Bid submitted successfully",
            )
        except Rejected as e:
            attempt.update(state="rejected", message=str(e))
        except Exception:
            attempt.update(
                state="unknown",
                message="Submission outcome uncertain. Check Freelancer before any further action. Automatic retry is disabled.",
            )
        record(ident, attempt)
        return {"submission": attempt}
