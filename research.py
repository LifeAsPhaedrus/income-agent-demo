"""Evidence-preserving first-pass matching, not employer or qualification verification."""

import json
import re
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "li", "h1", "h2", "h3", "br"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value):
    parser = TextOnly()
    parser.feed(value)
    return "\n".join(
        " ".join(line.split())
        for line in "".join(parser.parts).splitlines()
        if line.strip()
    )


SIGNALS = {
    "excel": ("Excel/spreadsheets", r"\bExcel\b|\bspreadsheets?\b", 3),
    "analytics": ("Analytics", r"\banalytics\b|\bdata analysis\b", 1),
    "dashboard creation": ("Dashboards", r"\bdashboards?\b", 3),
    "forecasting reports": ("Forecasting", r"\bforecast(?:ing|s)?\b", 3),
    "supply chain": ("Supply chain", r"\bsupply chain\b", 5),
    "materials management": ("Materials management", r"\bmaterials management\b", 5),
    "sales-to-inventory reconciliation": (
        "Inventory/reconciliation",
        r"\binventory\b|\breconcil(?:e|iation|iations|ing)\b",
        4,
    ),
    "shipment tracking": ("Shipping", r"\bshipments?\b|\blogistics\b", 3),
    "sales payout tracking and reconciliation": ("Payouts", r"\bpayouts?\b", 4),
    "graphic design": ("Graphic design", r"\bgraphic design\b", 3),
}


def assess(snapshot, profile, reviewed=()):
    counts = Counter()
    side = []
    career = []
    unknown = []
    seen = set()
    now = snapshot["fetched_at"]
    for row in snapshot["payload"]["jobs"]:
        counts["fetched"] += 1
        try:
            if not isinstance(row, dict):
                raise ValueError()
            ident = "jobicy:" + str(row["id"])
            if type(row["id"]) is not int:
                raise ValueError()
            u = urlsplit(row["url"])
            if (
                u.scheme != "https"
                or u.hostname != "jobicy.com"
                or u.port not in (None, 443)
                or u.username
                or u.password
                or not u.path.startswith("/jobs/")
            ):
                raise ValueError()
            for key in (
                "jobTitle",
                "companyName",
                "jobDescription",
                "jobGeo",
                "pubDate",
            ):
                if not isinstance(row[key], str) or not row[key].strip():
                    raise ValueError()
            types = row["jobType"]
            if not isinstance(types, list) or not all(
                isinstance(t, str) for t in types
            ):
                raise ValueError()
            date = datetime.fromisoformat(row["pubDate"].replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError()
            age = now - date.timestamp()
            if age < -3600 or age > 7 * 86400:
                counts["outside_recent_window"] += 1
                continue
        except (KeyError, ValueError, TypeError):
            counts["invalid"] += 1
            continue
        if ident in seen or ident in reviewed:
            counts["duplicate_or_reviewed"] += 1
            continue
        seen.add(ident)
        geo = row["jobGeo"].casefold()
        # Broad regions are retained for review; specific non-US locations are excluded.
        if not any(
            x in geo
            for x in (
                "usa",
                "united states",
                "anywhere",
                "worldwide",
                "north america",
                "americas",
                "global",
            )
        ):
            counts["non_us_or_unclear_location"] += 1
            continue
        description = plain(row["jobDescription"])
        title = plain(row["jobTitle"])
        relevant_role = r"analyst|analytics|analysis|insights|inventory|supply chain|materials|logistics|reconcil|billing|payout|spreadsheet|excel|reporting|forecast|graphic design|visual design|operations|accounts receivable"
        if not re.search(relevant_role, title, re.I):
            counts["role_outside_current_focus"] += 1
            continue
        evidence = []
        score = 0
        for skill, (label, pattern, weight) in SIGNALS.items():
            if skill not in profile["skills"]:
                continue
            matches = [
                line
                for line in description.splitlines()
                if re.search(pattern, line, re.I)
            ]
            if re.search(pattern, title, re.I):
                matches.insert(0, title)
                weight += 3
            if matches:
                evidence.append({"signal": label, "quote": matches[0]})
                score += weight
        if not evidence:
            counts["no_profile_signal"] += 1
            continue
        normalized = {t.casefold().replace("_", "-").replace(" ", "-") for t in types}
        lane = (
            "side_income_leads"
            if normalized & {"contract", "freelance", "part-time", "temporary"}
            else "career_leads"
            if "full-time" in normalized
            else "unknown_engagement"
        )
        salary = {
            k: row.get(k)
            for k in ("salaryMin", "salaryMax", "salaryCurrency", "salaryPeriod")
        }
        target = "Not comparable: pay missing, non-hourly, or non-USD"
        low = salary["salaryMin"]
        if (
            type(low) in (int, float)
            and low > 0
            and salary["salaryCurrency"] == "USD"
            and str(salary["salaryPeriod"]).casefold() in ("hourly", "hour")
        ):
            target = (
                "Meets preferred hourly target"
                if low >= profile["preferred_hourly_usd"]
                else "Below target; simple/automatable-work exception needs review"
            )
        checks = [
            line
            for line in description.splitlines()
            if re.search(
                r"\brequir|\bmust\b|\byears\b|\bSQL\b|\bPython\b|\bSAP\b|\bdegree\b|\bexcept\b|\bshift\b|\btime zone\b",
                line,
                re.I,
            )
        ]
        result = {
            "id": ident,
            "title": title,
            "company": plain(row["companyName"]),
            "url": row["url"],
            "source": "Jobicy",
            "published_at": row["pubDate"],
            "location": row["jobGeo"],
            "engagement": types,
            "lane": lane,
            "relevance_score": score,
            "evidence": evidence,
            "salary": salary,
            "pay_assessment": target,
            "requirements_to_review": checks[:12],
            "unknowns": [
                "Employer legitimacy and current opening not independently verified",
                "Full qualifications and location/state eligibility need review",
                "Evening compatibility and weekly hours not established",
                "Fixed-fee effort and automation savings not estimated",
            ],
            "next_step": "Read source listing and check requirements, schedule, and scope before deciding whether to pursue.",
        }
        {
            "side_income_leads": side,
            "career_leads": career,
            "unknown_engagement": unknown,
        }[lane].append(result)
    for group in (side, career, unknown):
        group.sort(key=lambda r: (-r["relevance_score"], r["id"]))
    return {
        "source": "Jobicy",
        "endpoint": snapshot["endpoint"],
        "fetched_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "cached": snapshot["cached"],
        "warning": snapshot.get("warning"),
        "coverage": "First page only, at most 100 recent listings; not an exhaustive search",
        "has_more": snapshot["payload"].get("hasMore"),
        "counts": dict(counts),
        "verified_opportunities": [],
        "verified_shortfall": 3,
        "side_income_leads": side[:3],
        "career_leads": career[:3],
        "unknown_engagement": unknown[:3],
        "matching_method": "Deterministic profile keyword relevance, not skill sufficiency or employer verification; no Ollama yet",
    }


def render(report):
    lines = [
        "# Jobicy first-pass research",
        "",
        f"Fetched: {report['fetched_at']}",
        "",
        report["coverage"],
        "",
        "These are unverified leads, not confirmed suitable opportunities. Pay/hour requirements and full qualifications need human review.",
        "",
        f"Counts: {json.dumps(report['counts'])}",
        "",
    ]
    for key, title in [
        ("side_income_leads", "Potential side-income work"),
        ("career_leads", "Separate remote career options"),
        ("unknown_engagement", "Engagement unclear"),
    ]:
        lines += ["## " + title, ""]
        if not report[key]:
            lines += ["No leads found in this page.", ""]
        for r in report[key]:
            lines += [
                f"### {r['title']} — {r['company']}",
                "",
                f"Source: {r['url']}",
                f"ID: {r['id']} | {', '.join(r['engagement'])} | {r['location']}",
                f"Salary fields: {json.dumps(r['salary'])}",
                r["pay_assessment"],
                "",
                "Matching evidence:",
            ]
            lines += ["- " + e["signal"] + ": " + e["quote"] for e in r["evidence"]]
            lines += ["", "Requirements and restrictions to review:"] + [
                "- " + v for v in r["requirements_to_review"]
            ]
            lines += ["", "Unknowns:"] + ["- " + v for v in r["unknowns"]] + [""]
    lines[2:2] = [
        f"Cached response: {report['cached']}. Fetch warning: {report['warning'] or 'none'}. More source pages available: {report['has_more']}.",
        "",
    ]
    return "\n".join(lines) + "\n"
