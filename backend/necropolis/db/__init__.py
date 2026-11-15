"""SQLite connection and numbered migrations (tech.md: stdlib `sqlite3`, WAL mode, one database file)."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

__all__ = ["connect", "migrate"]

_MIGRATION_NAME = re.compile(r"(\d{4})_([a-z0-9_]+)\.sql")


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database (creating its folder), switch to WAL mode and apply pending migrations."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> list[int]:
    """Apply `migrations/NNNN_name.sql` files not applied yet, each in its own transaction. Returns their numbers."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    done: list[int] = []
    for version, name, sql in _migrations():
        if version in applied:
            continue
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        # executescript() cannot take parameters. version, name and stamp come from our own packaged file names
        # (checked against _MIGRATION_NAME) and the clock, never from input.
        conn.executescript(
            f"BEGIN;\n{sql}\n"
            f"INSERT INTO schema_migrations (version, name, applied_at) VALUES ({version}, '{name}', '{stamp}');\n"
            "COMMIT;"
        )
        done.append(version)
    return done


def _migrations() -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    for entry in resources.files("necropolis.db").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.fullmatch(entry.name)
        if match is None:
            continue
        found.append((int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8")))
    found.sort()
    versions = [version for version, _, _ in found]
    if len(set(versions)) != len(versions):
        raise RuntimeError("two migrations share a number")
    return found
