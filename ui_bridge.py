"""Private SSH interface. Local review writes only; never calls marketplace/model."""

import json
import sys
from contextlib import closing
from pathlib import Path

import workflow
from domain import REVIEW_STATUSES, valid_listing_id

ROOT = Path(__file__).resolve().parent


def dispatch(request, root=ROOT):
    action = request.get("action", "snapshot")
    if action in ("bid_prepare", "bid_submit", "bid_status"):
        import bids

        if action == "bid_prepare":
            return bids.prepare(root, request)
        if action == "bid_submit":
            return bids.submit(root, request)
        return bids.status(request.get("id"))
    if action in ("proposal_get", "proposal_save", "proposal_export"):
        import proposals

        if action == "proposal_get":
            result = proposals.get(root, request.get("id"))
            if (root / "postgres-enabled").exists():
                import bids

                bids.archive(result)
                result["submission"] = bids.status(request.get("id"))
            return result
        if action == "proposal_save":
            result = proposals.save(root, request)
            if (root / "postgres-enabled").exists():
                import bids

                bids.archive(result)
            return result
        return proposals.export(root, request.get("id"))
    if action not in ("snapshot", "review", "export", "excel"):
        raise ValueError("Unsupported action")
    with closing(workflow.connect(root)) as db, db:
        if action == "review":
            ident = request.get("id", "")
            status = request.get("status")
            note = request.get("note", "")
            if (
                not valid_listing_id(ident)
                or status not in REVIEW_STATUSES
                or not isinstance(note, str)
                or len(note) > 2000
            ):
                raise ValueError("Invalid review")
            if not db.execute("SELECT 1 FROM items WHERE id=?", (ident,)).fetchone():
                raise ValueError("Unknown gig")
            db.execute(
                "UPDATE items SET status=?,note=? WHERE id=?", (status, note, ident)
            )
        history = [
            dict(zip(("id", "title", "status", "note"), row))
            for row in db.execute(
                "SELECT id,title,status,note FROM items ORDER BY updated DESC,id"
            )
        ]
    report = json.loads((root / "PERSONALIZED-RESULTS.json").read_text())
    states = {p["id"]: p for p in history}
    for p in report["ranked"]:
        if p["id"] in states:
            p.update(status=states[p["id"]]["status"], note=states[p["id"]]["note"])
    # Keep evidence from earlier batches, even after the current report changes.
    with closing(workflow.connect(root)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        for p in report["ranked"]:
            db.execute(
                "INSERT OR REPLACE INTO evidence VALUES (?,?)", (p["id"], json.dumps(p))
            )
        evidence = {
            ident: json.loads(payload)
            for ident, payload in db.execute("SELECT id,payload FROM evidence")
        }
    records = [{**evidence.get(h["id"], {}), **h} for h in history]
    import proposals
    from earnings import estimate

    with closing(proposals.connection(root)) as db:
        for p in records:
            p.setdefault("source", p["id"].split(":")[0].title())
            if not isinstance(p.get("location"), str):
                p["location"] = None
            d = db.execute(
                "SELECT amount FROM proposals WHERE id=? ORDER BY version DESC LIMIT 1",
                (p["id"],),
            ).fetchone()
            p["earnings"] = estimate(p, d[0] if d else None)
    report["history"] = records
    report["database_status"] = "Not configured"
    if (root / "postgres-enabled").exists():
        try:
            import postgres_store

            postgres_store.sync(records)
            report["database_status"] = (
                "Opportunities and reviews synced to separate PostgreSQL instance"
            )
            if action == "excel":
                return {"rows": postgres_store.excel_rows()}
            if action == "export":
                return {"rows": postgres_store.selected()}
        except Exception:
            report["database_status"] = (
                "Review saved locally; PostgreSQL sync pending. Refresh to retry."
            )
            if action in ("export", "excel"):
                raise ValueError("PostgreSQL unavailable; export not created")
    elif action in ("export", "excel"):
        raise ValueError("PostgreSQL not configured")
    return report


if __name__ == "__main__":
    try:
        raw = sys.stdin.read(16385)
        if len(raw) > 16384:
            raise ValueError("Request too large")
        print(json.dumps(dispatch(json.loads(raw))))
    except Exception:
        print(
            json.dumps(
                {
                    "error": "Could not read results or save review. The model may still be writing the report; retry shortly."
                }
            )
        )
        sys.exit(1)
