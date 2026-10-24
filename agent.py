"""Local research CLI: optional read-only Jobicy fetch; no applications or external writes."""

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def item_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def validate(item):
    u = urlsplit(item["url"])
    if u.scheme != "https" or u.hostname != "example.org" or u.username or u.password:
        raise ValueError("Demo accepts only the example.org fixture source")
    if item["source"] != "demo" or not item["evidence"].strip():
        raise ValueError("Source and evidence are required")
    for key in ("hourly_usd", "weekly_hours"):
        value = item[key]
        if value is not None and (
            type(value) not in (int, float) or not math.isfinite(value) or value <= 0
        ):
            raise ValueError(f"Invalid {key}")
    if not isinstance(item["skills"], list) or not all(
        isinstance(s, str) for s in item["skills"]
    ):
        raise ValueError("Invalid skills")
    return item


def shortlist(items, profile, reviewed):
    """Conservative eligibility; missing pay/time/skills cannot become a top pick."""
    chosen, seen = [], set()
    for raw in items:
        item = validate(raw)
        ident = item_id(item["url"])
        if ident in seen or ident in reviewed:
            continue
        seen.add(ident)
        pay, hours = item["hourly_usd"], item["weekly_hours"]
        if item["kind"] not in ("freelance", "contract") or item.get("risk_flags"):
            continue
        if pay is None or hours is None or not item["skills"]:
            continue
        if pay < profile["minimum_hourly_usd"] or hours > profile["weekly_hours"]:
            continue
        required = {s.casefold() for s in item["skills"]}
        available = {s.casefold() for s in profile["skills"]}
        fit = len(required & available) / len(required)
        if fit < 1:
            continue
        # Explicit, explainable score; capped pay avoids domination by implausible claims.
        score = round(
            50 * fit
            + 30 * min(pay / (2 * profile["minimum_hourly_usd"]), 1)
            + 20 * (1 - hours / profile["weekly_hours"]),
            1,
        )
        chosen.append(
            dict(
                item,
                id=ident,
                score=score,
                skill_fit=fit,
                gross_monthly_scenario_usd=round(pay * hours * 4.33, 2),
                verification="DEMO ONLY — employer and availability unverified",
            )
        )
    return sorted(chosen, key=lambda x: (-x["score"], x["id"]))[:3]


def database(path):
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS reviewed (id TEXT PRIMARY KEY, reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    return db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Show up to three synthetic opportunities")
    sub.add_parser(
        "research", help="Read Jobicy or hourly cache; save unverified leads locally"
    )
    mark = sub.add_parser("review", help="Locally mark a displayed listing reviewed")
    mark.add_argument("id")
    sub.add_parser("history")
    args = parser.parse_args()
    if args.command == "research":
        import jobicy
        import research

        try:
            snapshot = jobicy.fetch(ROOT / "data")
            real_profile = json.loads((ROOT / "user-profile.json").read_text())
            with database(ROOT / "reviewed.sqlite3") as db:
                reviewed = {r[0] for r in db.execute("SELECT id FROM reviewed")}
            report = research.assess(snapshot, real_profile, reviewed)
            (ROOT / "latest-research.json").write_text(json.dumps(report, indent=2))
            (ROOT / "LATEST-RESEARCH.md").write_text(research.render(report))
            print(json.dumps(report, indent=2))
        except (ValueError, OSError) as error:
            parser.exit(1, f"Research failed: {error}\n")
        return
    items = json.loads((ROOT / "fixtures/listings.json").read_text())
    profile = json.loads((ROOT / "fixtures/profile.json").read_text())
    with database(ROOT / "reviewed.sqlite3") as db:
        if args.command == "review":
            known = {item_id(validate(i)["url"]) for i in items}
            report_path = ROOT / "latest-research.json"
            if report_path.exists():
                report = json.loads(report_path.read_text())
                known.update(
                    r["id"]
                    for lane in (
                        "side_income_leads",
                        "career_leads",
                        "unknown_engagement",
                    )
                    for r in report[lane]
                )
            if args.id not in known:
                parser.error("Unknown listing ID")
            db.execute("INSERT OR IGNORE INTO reviewed(id) VALUES (?)", (args.id,))
            print("Marked reviewed locally.")
        elif args.command == "history":
            print(
                json.dumps(
                    db.execute(
                        "SELECT id, reviewed_at FROM reviewed ORDER BY reviewed_at, id"
                    ).fetchall(),
                    indent=2,
                )
            )
        else:
            reviewed = {r[0] for r in db.execute("SELECT id FROM reviewed")}
            results = shortlist(items, profile, reviewed)
            print(
                json.dumps(
                    {
                        "mode": "synthetic demo; not real opportunities",
                        "profile": "example assumptions, not your personal profile",
                        "results": results,
                        "shortfall": 3 - len(results),
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
