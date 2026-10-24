"""Load saved source snapshots without making network calls."""

import json

from contra_source import normalize as normalize_contra
from remotive_source import normalize as normalize_remotive

MAX_SNAPSHOT_AGE = 86400


def load_candidates(root, query, now):
    freelancer_path = root / "freelancer-results.json"
    source = (
        json.loads(freelancer_path.read_text())
        if freelancer_path.exists()
        else {"projects": [], "fetched_at_epoch": 0}
    )
    active_query = query or source.get("query", "Excel dashboard")
    rows = list(source["projects"])
    # A failed search must not label a previous, different query as current results.
    if query and source.get("query") not in (None, query):
        rows = []
    for filename, normalize, requires_same_query in (
        ("remotive-results.json", normalize_remotive, False),
        ("contra-results.json", normalize_contra, True),
    ):
        path = root / filename
        if not path.exists():
            continue
        snapshot = json.loads(path.read_text())
        if not 0 <= now - snapshot["fetched_at_epoch"] <= MAX_SNAPSHOT_AGE:
            continue
        if requires_same_query and snapshot.get("query") != active_query:
            continue
        rows.extend(
            normalize(snapshot["jobs"])
            if requires_same_query
            else normalize(snapshot["jobs"], active_query)
        )
    return source, rows
