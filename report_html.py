"""Escaped static HTML rendering, independent of ranking and persistence."""

import html


def render(report):
    def e(value):
        return html.escape(str(value), quote=True)

    cards = []
    for p in report["top_three"]:
        evidence = "".join(
            "<li><b>" + e(m["skill"]) + "</b>: " + e(m["quote"]) + "</li>"
            for m in p["matches"]
        )
        gaps = "".join("<li>" + e(g) + "</li>" for g in p["gaps"])
        quotes = "".join(
            "<li>" + e(q) + "</li>" for q in p["model"].get("requirements", [])
        )
        cards.append(
            f'''<article><span class="tag">{e(p["lane"])}</span><h2><a href="{e(p["url"])}" rel="noreferrer">{e(p["title"])}</a></h2><p>{e(p["budget"]["currency"])} {e(p["budget"]["minimum"])}–{e(p["budget"]["maximum"])} · {e(p["budget"]["type"])}</p><p>{e(p["pay"])}</p><p>Relevance score {p["score"]} (heuristic, not probability): {e(p["components"])}</p><h3>Why it surfaced</h3><ul>{evidence}</ul><h3>Before pursuing</h3><ul>{gaps}</ul><h3>Qwen evidence</h3><p>{e(p["model"]["status"])}</p><ul>{quotes}</ul><p>ID: <code>{e(p["id"])}</code></p><p>Mark reviewed: <code>python3 workflow.py review {e(p["id"])} reviewed</code></p></article>'''
        )
    reviewed = "".join(
        "<li>"
        + e(p["id"])
        + " — "
        + e(p["title"])
        + " · "
        + e(p["status"])
        + (" · changed listing" if p["changed_since_last_run"] else "")
        + "</li>"
        for p in report["ranked"]
        if p["status"] != "new"
    )
    rejected = "".join(
        "<li>" + e(p["title"]) + ": " + e(", ".join(p["reasons"])) + "</li>"
        for p in report["excluded"]
    )
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Your opportunity review</title><style>body{background:#eef2f4;color:#182b37;font:17px system-ui;max-width:960px;margin:40px auto;padding:20px}article,header,section{background:white;border-radius:14px;padding:26px;margin:20px 0}h1{font-size:36px}a{color:#16676c}.tag{color:#16676c;font-weight:700}li{margin:10px 0}code{overflow-wrap:anywhere;font-size:14px}p{line-height:1.6}</style>"""
        + f"""<header><p>PERSONAL INCOME RESEARCH · MULTIPLE SOURCES</p><h1>Your opportunity review</h1><p>{len(report["top_three"])} new leads · {len(report["excluded"])} filtered out · target $50/hour</p><p>Source fetched {e(report["source_fetched"])}. {e(report["freshness"])}</p><p>These are unverified leads. No applications submitted. Fixed-fee budgets are not hourly rates.</p></header>"""
        + (
            "".join(cards)
            or "<article>No new matching leads. Review filters or run a fresh search; no filler results.</article>"
        )
        + f"<section><h2>Tracked decisions</h2><ul>{reviewed or '<li>No reviewed leads in this batch.</li>'}</ul><h2>Filtered out</h2><ul>{rejected}</ul></section></html>"
    )
