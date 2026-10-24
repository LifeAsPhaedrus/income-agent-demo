"""Shared domain validation; no I/O or credentials."""

import math
import re

SOURCES = ("Freelancer", "Remotive", "Contra", "Demo")
REVIEW_STATUSES = frozenset(("new", "saved", "reviewed", "dismissed"))


def valid_listing_id(value, source=None):
    if not isinstance(value, str):
        return False
    prefixes = (source,) if source else tuple(name.lower() for name in SOURCES)
    return any(re.fullmatch(re.escape(prefix) + r":\d+", value) for prefix in prefixes)


def positive(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0
