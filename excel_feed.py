"""Read-only OData subset for Excel on the loopback dashboard."""

import os
import secrets
from urllib.parse import parse_qs, urlsplit

FIELDS = [
    ("listing_id", "String"),
    ("title", "String"),
    ("listing_url", "String"),
    ("currency", "String"),
    ("minimum_budget", "Double"),
    ("maximum_budget", "Double"),
    ("project_type", "String"),
    ("hourly_assessment", "String"),
    ("review_notes", "String"),
    ("description", "String"),
    ("database_updated_at", "DateTimeOffset"),
    ("proposed_bid_amount", "Double"),
    ("proposed_bid_currency", "String"),
    ("delivery_days", "Int32"),
    ("delivery_start_condition", "String"),
    ("revision_rounds", "Int32"),
    ("proposal_version", "Int32"),
    ("proposal_text", "String"),
    ("bid_status", "String"),
    ("bid_status_detail", "String"),
    ("freelancer_bid_id", "String"),
    ("attempted_bid_amount", "Double"),
    ("attempted_milestone_percentage", "Int32"),
    ("attempted_proposal_version", "Int32"),
    ("bid_status_updated_at", "DateTimeOffset"),
    ("proposal_review_url", "String"),
    ("opportunity_source", "String"),
    ("review_status", "String"),
    ("advertised_salary_text", "String"),
    ("eligible_location", "String"),
    ("earnings_basis", "String"),
    ("estimated_gross_amount", "Double"),
    ("estimated_platform_fee", "Double"),
    ("estimated_after_fee_before_tax", "Double"),
    ("earnings_currency", "String"),
    ("earnings_pay_unit", "String"),
    ("fee_policy", "String"),
    ("earnings_limitations", "String"),
    ("fee_policy_url", "String"),
]


def key(root):
    path = root.parent.parent / "demo-private/excel-feed-key"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32))
    except FileExistsError:
        pass
    return path.read_text().strip()


def route(path, token, remote):
    base = "/excel/" + token + "/odata/"
    parsed = urlsplit(path)
    if not parsed.path.startswith(base):
        return 404, {"error": "Not found"}, "application/json"
    suffix = parsed.path[len(base) :]
    root = "http://127.0.0.1:8766" + base
    if suffix == "$metadata":
        props = "".join(
            '<Property Name="'
            + n
            + '" Type="Edm.'
            + t
            + '" Nullable="'
            + ("false" if n == "listing_id" else "true")
            + '"/>'
            for n, t in FIELDS
        )
        xml = (
            '<?xml version="1.0" encoding="utf-8"?><edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx"><edmx:DataServices><Schema Namespace="Income" xmlns="http://docs.oasis-open.org/odata/ns/edm"><EntityType Name="Gig"><Key><PropertyRef Name="listing_id"/></Key>'
            + props
            + '</EntityType><EntityContainer Name="Container"><EntitySet Name="Pursue" EntityType="Income.Gig"/></EntityContainer></Schema></edmx:DataServices></edmx:Edmx>'
        )
        return 200, xml, "application/xml"
    if suffix == "":
        return (
            200,
            {
                "@odata.context": root + "$metadata",
                "value": [{"name": "Pursue", "kind": "EntitySet", "url": "Pursue"}],
            },
            "application/json",
        )
    if suffix != "Pursue":
        return 404, {"error": "Not found"}, "application/json"
    query = parse_qs(parsed.query)
    if set(query) - {"$top", "$skip", "$select", "$count", "$format"}:
        return 400, {"error": "Unsupported query option"}, "application/json"
    rows = remote({"action": "excel"})["rows"]
    total = len(rows)
    start = int(query.get("$skip", ["0"])[0])
    count = int(query.get("$top", [str(total)])[0])
    if start < 0 or count < 0:
        raise ValueError("Invalid range")
    rows = rows[start : start + count]
    if "$select" in query:
        names = query["$select"][0].split(",")
        if set(names) - {n for n, t in FIELDS}:
            raise ValueError("Invalid fields")
        rows = [{n: r.get(n) for n in names} for r in rows]
    result = {"@odata.context": root + "$metadata#Pursue", "value": rows}
    if query.get("$count") == ["true"]:
        result["@odata.count"] = total
    return 200, result, "application/json"
