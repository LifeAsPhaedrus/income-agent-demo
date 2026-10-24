"""Deterministic skill, pay and eligibility ranking with source evidence."""

import hashlib
import json
import re
from datetime import datetime, timezone

from domain import SOURCES, positive
from research import SIGNALS


def rank(rows, profile, db, now):
    ranked = []
    excluded = []
    seen = set()
    for p in rows:
        if not isinstance(p, dict) or type(p.get("id")) is not int:
            continue
        source = p.get("source", "Freelancer")
        if source not in SOURCES:
            continue
        ident = source.lower() + ":" + str(p["id"])
        if ident in seen:
            continue
        seen.add(ident)
        title = p.get("title")
        text = p.get("description") or p.get("preview_description") or ""
        if not isinstance(title, str) or not isinstance(text, str):
            continue
        fingerprint = hashlib.sha256(
            (title + text + json.dumps(p.get("budget"), sort_keys=True)).encode()
        ).hexdigest()
        prior = db.execute(
            "SELECT hash,status FROM items WHERE id=?", (ident,)
        ).fetchone()
        db.execute(
            "INSERT INTO items(id,title,hash,updated) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,hash=excluded.hash,updated=excluded.updated",
            (ident, title, fingerprint, datetime.now(timezone.utc).isoformat()),
        )
        status = prior[1] if prior else "new"
        changed = bool(prior and prior[0] != fingerprint)
        reasons = []
        if p.get("status") != "active" or p.get("deleted"):
            reasons.append("Not active")
        if p.get("language") not in (None, "en"):
            reasons.append("Listing language not confirmed in profile")
        if p.get("local"):
            reasons.append("Requires local work")
        stamp = p.get("time_submitted")
        if not positive(stamp) or now - stamp > 30 * 86400 or stamp > now + 3600:
            reasons.append("Missing or out-of-range publication date")
        if re.search(r"physically in China|must be based in Brazil", text, re.I):
            reasons.append("Location requirement not supported by profile")
        if re.search(r"\bKeyence\b|\bPCI DSS\b", title, re.I):
            reasons.append("Specialist capability not established")
        matches = []
        components = {}
        for skill, (label, pattern, weight) in SIGNALS.items():
            if skill not in profile["skills"]:
                continue
            # Match Excel as the product, not the verb “excel at”.
            hay = title + "\n" + text
            if skill == "excel":
                hay = re.sub(r"\bexcel (?:at|in)\b", "", hay, flags=re.I)
            found = re.search(pattern, hay, re.I)
            if found:
                quote = next(
                    (
                        line.strip()
                        for line in hay.splitlines()
                        if re.search(pattern, line, re.I)
                    ),
                    found.group(),
                )
                matches.append({"skill": label, "quote": quote[:800]})
                components[label] = weight + (
                    4 if re.search(pattern, title, re.I) else 0
                )
        if not re.search(
            r"excel|spreadsheet|dashboard|inventory|reconcil|forecast|payout|tracking|tracker|handover|report|analyst|analytics|supply chain|operations|materials",
            title,
            re.I,
        ):
            reasons.append("Title outside core service focus")
        if not matches:
            reasons.append("No confirmed skill signal")
        if reasons:
            excluded.append({"id": ident, "title": title, "reasons": reasons})
            continue
        budget = p.get("budget") or {}
        currency = (p.get("currency") or {}).get("code", "unknown")
        kind = p.get("type", "unknown")
        low = budget.get("minimum")
        high = budget.get("maximum")
        hoursrow = db.execute(
            "SELECT hours FROM effort WHERE id=?", (ident,)
        ).fetchone()
        hours = hoursrow[0] if hoursrow else None
        effective = None
        pay = "Unknown effective hourly pay"
        if currency == "USD" and positive(low):
            if kind == "hourly":
                effective = low
            elif kind == "fixed" and hours:
                effective = low / hours
        if effective is not None:
            pay = f"Conservative gross rate: ${effective:.2f}/hour, before fees/taxes"
            components["Pay target"] = (
                5 if effective >= profile["preferred_hourly_usd"] else -3
            )
        elif kind == "fixed":
            pay = "Fixed fee: add your all-in effort estimate to evaluate hourly return"
        lane = "Review needed"
        if effective is not None:
            lane = (
                "Meets pay target; verify scope"
                if effective >= 50
                else "Below-target exception; justify simplicity"
            )
        gaps = [
            "Employer legitimacy, current availability, and full skill fit unverified",
            "Evening schedule and weekly effort must be confirmed",
        ]
        for tool in profile["unconfirmed_tools"]:
            if re.search(r"\b" + re.escape(tool) + r"\b", text, re.I):
                gaps.append(tool + " proficiency not established")
        if kind == "fixed":
            gaps.append(
                "Include setup, communication, QA, revisions and handoff in effort; automation savings unproven"
            )
        ranked.append(
            {
                "id": ident,
                "source": source,
                "salary_text": p.get("salary_text"),
                "location": p.get("location")
                if isinstance(p.get("location"), str)
                else None,
                "source_notice": p.get("source_notice"),
                "title": title,
                "url": p.get("url")
                if source in ("Remotive", "Contra", "Demo")
                else "https://www.freelancer.com/projects/" + str(p["id"]),
                "status": status,
                "changed_since_last_run": changed,
                "score": sum(components.values()),
                "components": components,
                "matches": matches,
                "budget": {
                    "minimum": low,
                    "maximum": high,
                    "currency": currency,
                    "type": kind,
                },
                "effort_hours": hours,
                "effective_hourly": effective,
                "pay": pay,
                "lane": lane,
                "gaps": gaps,
                "description": text,
                "model": {"status": "not requested"},
            }
        )
    from earnings import estimate

    for item in ranked:
        item["earnings"] = estimate(item)
        if item["source"] == "Remotive":
            item["lane"] = (
                "Career / remote contract; schedule and geography need review"
            )
    ranked.sort(key=lambda p: (-p["score"], p["id"]))
    return ranked, excluded
