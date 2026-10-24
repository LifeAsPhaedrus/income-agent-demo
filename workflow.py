"""Coordinate multi-source ranking, optional Qwen evidence and review CLI."""

import argparse
import json
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from domain import positive as positive
from file_store import write_json_atomic
from ranking import rank as rank
from report_html import render as render
from review_store import connect as connect
from source_snapshots import load_candidates

ROOT = Path(__file__).resolve().parent


def build(root, use_model=False, watch=False, query=None):
    profile = json.loads((root / "user-profile.json").read_text())
    now = time.time()
    source, rows = load_candidates(root, query, now)
    age = now - source["fetched_at_epoch"]
    with closing(connect(root)) as db, db:
        ranked, excluded = rank(rows, profile, db, now)
    top = [
        p
        for p in ranked
        if p["status"] == "new"
        and (p["source"] in ("Remotive", "Contra") or age <= 86400)
    ][:3]
    if use_model:
        from ollama_local import extract

        for p in top:
            try:
                if watch:
                    print("\nQwen 3.5 4B | " + p["id"] + " | " + p["title"], flush=True)

                    def show(chunk):
                        print(
                            "".join(
                                c
                                for c in chunk
                                if c in "\n\t" or ord(c) >= 32 and ord(c) != 127
                            ),
                            end="",
                            flush=True,
                        )

                    result = extract(p["description"], on_chunk=show)
                    print("\nEvidence validated.\n", flush=True)
                else:
                    result = extract(p["description"])
                p["model"] = {
                    "status": "Qwen exact quotes; relevance still needs human review",
                    **result,
                }
            except Exception as error:
                p["model"] = {
                    "status": "Qwen unavailable or invalid evidence; rules-only result retained",
                    "error_type": type(error).__name__,
                }
                if watch:
                    print(
                        "\nModel evidence rejected or unavailable ("
                        + type(error).__name__
                        + "); keeping rules-only result.",
                        flush=True,
                    )
    source_status = (
        json.loads((root / "source-status.json").read_text())
        if (root / "source-status.json").exists()
        else {}
    )
    for name in ("Freelancer", "Remotive", "Contra"):
        if name in source_status:
            source_status[name] += (
                "; "
                + str(sum(p["source"] == name for p in ranked))
                + " matching opportunities"
            )
    report = {
        "sources": source_status,
        "source_fetched": datetime.fromtimestamp(
            source["fetched_at_epoch"], timezone.utc
        ).isoformat(),
        "freshness": "Saved snapshot, not rechecked live"
        if age <= 86400
        else "Stale snapshot (>24h): fresh shortlist withheld",
        "top_three": top,
        "ranked": ranked,
        "excluded": excluded,
    }
    write_json_atomic(root / "PERSONALIZED-RESULTS.json", report)
    (root / "OPPORTUNITIES.html").write_text(render(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("report")
    run.add_argument("--qwen", action="store_true")
    run.add_argument(
        "--watch",
        action="store_true",
        help="Stream Qwen output to terminal; implies --qwen",
    )
    review = sub.add_parser("review")
    review.add_argument("id")
    review.add_argument("status", choices=["reviewed", "saved", "dismissed", "new"])
    review.add_argument("--note", default="")
    effort = sub.add_parser("effort")
    effort.add_argument("id")
    effort.add_argument("hours", type=float)
    sub.add_parser("history")
    args = parser.parse_args()
    if args.cmd == "report":
        report = build(ROOT, args.qwen or args.watch, args.watch)
        print(
            f"Report ready: {len(report['top_three'])} new leads. Open OPPORTUNITIES.html"
        )
        return
    with closing(connect(ROOT)) as db, db:
        if args.cmd == "history":
            print(
                json.dumps(
                    db.execute(
                        'SELECT id,title,status,note FROM items WHERE status!="new"'
                    ).fetchall(),
                    indent=2,
                )
            )
            return
        if not db.execute("SELECT 1 FROM items WHERE id=?", (args.id,)).fetchone():
            parser.error("Unknown listing ID; generate a report first")
        if args.cmd == "review":
            db.execute(
                "UPDATE items SET status=?,note=? WHERE id=?",
                (args.status, args.note, args.id),
            )
        else:
            if not positive(args.hours):
                parser.error("Effort must be finite and greater than zero")
            db.execute(
                "INSERT OR REPLACE INTO effort VALUES (?,?)", (args.id, args.hours)
            )
    build(ROOT)
    print("Saved locally and refreshed report.")


if __name__ == "__main__":
    main()
