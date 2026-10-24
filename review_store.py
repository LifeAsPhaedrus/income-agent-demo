"""SQLite connection and schema for local review decisions."""

import sqlite3


def connect(root):
    db = sqlite3.connect(root / "opportunities.sqlite3")
    db.execute(
        'CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, title TEXT, hash TEXT, status TEXT NOT NULL DEFAULT "new", note TEXT NOT NULL DEFAULT "", updated TEXT)'
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS effort (id TEXT PRIMARY KEY, hours REAL NOT NULL)"
    )
    return db
