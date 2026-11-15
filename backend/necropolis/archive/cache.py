"""SQLite archive cache (Req exhumer:3.3, safety.md rule 6): 7-day TTL, keyed by a SHA-256 of the request.

What is stored never holds a query value from an archived URL (safety.md rule 5):
- a CDX listing is stored whole, once complete, with its rows already redacted. It is not stored page by page,
  because a page's resume key is built from an archived URL and can carry its query value. So an interrupted or
  cancelled listing warms nothing;
- a snapshot is named by the SHA-256 of the archived URL, not by the URL itself. Its body is the archived file, which
  rule 6 says to cache.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from necropolis.archive.models import CaptureRow, CdxStats
from necropolis.archive.timestamps import format_timestamp, parse_timestamp

TTL = timedelta(days=7)
_SEPARATOR = chr(31)
_LISTING_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(UTC)


def cache_key(*parts: str) -> str:
    return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8", "surrogatepass")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheEntry:
    body: bytes
    meta: dict[str, object]
    fetched_at: datetime


class ArchiveCache:
    """Entries older than `ttl` are never served, and are deleted when they are found."""

    def __init__(
        self, conn: sqlite3.Connection, *, ttl: timedelta = TTL, now: Callable[[], datetime] = utc_now
    ) -> None:
        self._conn = conn
        self._ttl = ttl
        self._now = now

    def get(self, key: str) -> CacheEntry | None:
        row = self._conn.execute(
            "SELECT body, meta, fetched_at FROM archive_cache WHERE req_hash = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        try:
            fetched_at = datetime.fromisoformat(row[2])
            age = self._now() - fetched_at
            if not timedelta(0) <= age < self._ttl:
                raise ValueError("expired")
            meta = json.loads(row[1])
            if not isinstance(meta, dict):
                raise ValueError("bad meta")
            body = zlib.decompress(row[0])
        except (ValueError, TypeError, zlib.error):
            self._delete(key)
            return None
        return CacheEntry(body=body, meta=meta, fetched_at=fetched_at)

    def put(self, key: str, body: bytes, meta: dict[str, object]) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO archive_cache (req_hash, body, meta, fetched_at) VALUES (?, ?, ?, ?)",
                (key, zlib.compress(body, 6), json.dumps(meta, sort_keys=True), self._now().isoformat()),
            )

    def purge_expired(self) -> int:
        cutoff = (self._now() - self._ttl).isoformat()
        with self._conn:
            return self._conn.execute("DELETE FROM archive_cache WHERE fetched_at <= ?", (cutoff,)).rowcount

    def _delete(self, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM archive_cache WHERE req_hash = ?", (key,))


def dump_listing(rows: Sequence[CaptureRow], stats: CdxStats) -> bytes:
    """A complete listing, redacted rows only: `raw_original` is never written."""
    return json.dumps(
        {
            "version": _LISTING_VERSION,
            "pages": stats.pages,
            "malformed": stats.malformed,
            "capped": stats.capped,
            "counters": stats.counters,
            "rows": [
                [
                    format_timestamp(row.timestamp),
                    format_timestamp(row.last_timestamp),
                    row.captures,
                    row.original,
                    row.original_sha256,
                    row.query_stripped,
                    row.mimetype,
                    row.status,
                ]
                for row in rows
            ],
        },
        separators=(",", ":"),
    ).encode("utf-8")


def load_listing(body: bytes) -> tuple[list[CaptureRow], CdxStats]:
    data = json.loads(body)
    if data.get("version") != _LISTING_VERSION:
        raise ValueError("unknown listing version")
    rows = []
    for first, last, captures, original, sha, stripped, mimetype, status in data["rows"]:
        first_at, last_at = parse_timestamp(first), parse_timestamp(last)
        if first_at is None or last_at is None:
            raise ValueError("bad timestamp in a cached listing")
        rows.append(
            CaptureRow(
                timestamp=first_at,
                last_timestamp=last_at,
                captures=captures,
                original=original,
                original_sha256=sha,
                query_stripped=stripped,
                mimetype=mimetype,
                status=status,
            )
        )
    stats = CdxStats(
        pages=data["pages"], malformed=data["malformed"], capped=data["capped"], counters=data["counters"]
    )
    return rows, stats
