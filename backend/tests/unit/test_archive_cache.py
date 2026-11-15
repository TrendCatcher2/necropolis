"""The archive cache (Req exhumer:3.3; safety.md rules 5 and 6)."""

from __future__ import annotations

import json
import sqlite3
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from necropolis.archive import (
    TTL,
    ArchiveCache,
    ArchiveUnavailable,
    CaptureRow,
    CdxQuery,
    CdxStats,
    cache_key,
    parse_page,
    parse_timestamp,
)
from necropolis.archive.cache import dump_listing, load_listing
from necropolis.db import connect
from tests.archive_fake import FakeArchive, FakeCapture, make_client, shop_history

T0 = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
SECRET = "SECRETVALUE"  # noqa: S105 (a marker string, not a credential)


class Clock:
    def __init__(self, when: datetime = T0) -> None:
        self.when = when

    def __call__(self) -> datetime:
        return self.when


@pytest.fixture
def conn() -> sqlite3.Connection:
    return connect(":memory:")


def test_entries_live_for_seven_days(conn: sqlite3.Connection) -> None:
    clock = Clock()
    cache = ArchiveCache(conn, now=clock)
    cache.put("k", b"body", {"kind": "test"})
    clock.when = T0 + TTL - timedelta(seconds=1)
    entry = cache.get("k")
    assert entry is not None
    assert (entry.body, entry.meta, entry.fetched_at) == (b"body", {"kind": "test"}, T0)
    clock.when = T0 + TTL
    assert cache.get("k") is None
    assert conn.execute("SELECT count(*) FROM archive_cache").fetchone() == (0,)  # deleted once found expired


def test_an_entry_from_the_future_is_not_trusted(conn: sqlite3.Connection) -> None:
    clock = Clock()
    ArchiveCache(conn, now=clock).put("k", b"body", {})
    clock.when = T0 - timedelta(minutes=1)  # the clock went back
    assert ArchiveCache(conn, now=clock).get("k") is None


def test_corrupt_entries_are_dropped(conn: sqlite3.Connection) -> None:
    cache = ArchiveCache(conn, now=Clock())
    cache.put("k", b"body", {})
    conn.execute("UPDATE archive_cache SET body = ?", (b"not zlib",))
    assert cache.get("k") is None
    cache.put("k", b"body", {})
    conn.execute("UPDATE archive_cache SET meta = '[1, 2]'")
    assert cache.get("k") is None
    assert conn.execute("SELECT count(*) FROM archive_cache").fetchone() == (0,)


def test_purge_expired(conn: sqlite3.Connection) -> None:
    clock = Clock()
    cache = ArchiveCache(conn, now=clock)
    cache.put("old", b"1", {})
    clock.when = T0 + timedelta(days=5)
    cache.put("new", b"2", {})
    clock.when = T0 + timedelta(days=8)
    assert cache.purge_expired() == 1
    assert cache.get("new") is not None


def test_bodies_are_stored_compressed(conn: sqlite3.Connection) -> None:
    ArchiveCache(conn, now=Clock()).put("k", b"a" * 10_000, {})
    (stored,) = conn.execute("SELECT body FROM archive_cache").fetchone()
    assert len(stored) < 1000
    assert zlib.decompress(stored) == b"a" * 10_000


def test_cache_keys_keep_their_parts_apart() -> None:
    assert cache_key("a", "bc") != cache_key("ab", "c")
    assert cache_key("cdx", "x") == cache_key("cdx", "x")
    assert len(cache_key("snapshot", "20230110101636", "f" * 64)) == 64


def test_listing_round_trip_without_raw_urls() -> None:
    rows_in = _rows()
    assert any(row.raw_original for row in rows_in)
    stats = CdxStats(pages=2, rows=len(rows_in), malformed=1, capped=False, counters=True)
    body = dump_listing(rows_in, stats)
    rows_out, saved = load_listing(body)
    assert [row.model_dump() for row in rows_out] == [row.model_dump() for row in rows_in]
    assert all(row.raw_original is None for row in rows_out)  # never written, so never read back
    assert SECRET.encode() not in body
    assert (saved.pages, saved.malformed, saved.capped, saved.counters) == (2, 1, False, True)


def test_unknown_listing_versions_are_refused() -> None:
    with pytest.raises(ValueError, match="version"):
        load_listing(json.dumps({"version": 99, "rows": []}).encode())


async def test_a_complete_listing_serves_the_next_run(conn: sqlite3.Connection) -> None:
    archive = FakeArchive(shop_history(), page_size=2)
    query = CdxQuery.listing("shop.example.com", match_type="host")
    first_stats, second_stats = CdxStats(), CdxStats()
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        first = [row async for row in client.cdx_rows(query, cap=100, stats=first_stats)]
    sent = len(archive.requests)
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        second = [row async for row in client.cdx_rows(query, cap=100, stats=second_stats)]
    assert len(archive.requests) == sent  # Req 3.3: the repeated run asked the archive nothing
    assert [row.model_dump() for row in second] == [row.model_dump() for row in first]
    assert second_stats.from_cache
    assert (second_stats.pages, second_stats.rows, second_stats.counters) == (first_stats.pages, len(first), True)


async def test_the_cache_key_includes_the_cap(conn: sqlite3.Connection) -> None:
    archive = FakeArchive(shop_history())
    query = CdxQuery.listing("shop.example.com", match_type="host")
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        capped = [row async for row in client.cdx_rows(query, cap=2)]
        full = [row async for row in client.cdx_rows(query, cap=100)]
    assert len(capped) == 2
    assert len(full) > 2


async def test_an_interrupted_listing_warms_nothing(conn: sqlite3.Connection) -> None:
    archive = FakeArchive(shop_history(), page_size=2)
    archive.unavailable = lambda request: b"resumeKey=" in request.url.query  # page 2 never comes
    query = CdxQuery.listing("shop.example.com", match_type="host")
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        with pytest.raises(ArchiveUnavailable):
            _ = [row async for row in client.cdx_rows(query, cap=100)]
    assert conn.execute("SELECT count(*) FROM archive_cache").fetchone() == (0,)


async def test_an_expired_listing_is_fetched_again(conn: sqlite3.Connection) -> None:
    archive = FakeArchive(shop_history())
    clock = Clock()
    query = CdxQuery.listing("shop.example.com", match_type="host")
    async with make_client(archive, cache=ArchiveCache(conn, now=clock)) as client:
        _ = [row async for row in client.cdx_rows(query, cap=100)]
        sent = len(archive.requests)
        clock.when = T0 + TTL
        _ = [row async for row in client.cdx_rows(query, cap=100)]
    assert len(archive.requests) == 2 * sent


async def test_snapshots_are_cached_by_the_hash_of_their_url(conn: sqlite3.Connection) -> None:
    script = FakeCapture(
        "https://shop.example.com/static/app.js?v=" + SECRET, "20230110101636", b"js", "text/javascript"
    )
    archive = FakeArchive([script])
    when = parse_timestamp(script.timestamp)
    assert when is not None
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        fetched = await client.snapshot(when, script.url)
        again = await client.snapshot(when, script.url)
        (row,) = [row async for row in client.cdx_rows(CdxQuery.listing("shop.example.com", match_type="host"), cap=9)]
        by_hash = client.cached_snapshot(when, row.original_sha256)
    assert sum(request.url.path.startswith("/web/") for request in archive.requests) == 1
    assert fetched.body == again.body == b"js"
    assert by_hash is not None
    assert by_hash.body == b"js"
    assert SECRET not in fetched.url
    assert fetched.url == "https://shop.example.com/static/app.js?v"


async def test_a_truncated_snapshot_is_not_served_to_a_reader_that_may_read_more(conn: sqlite3.Connection) -> None:
    capture = FakeCapture("https://shop.example.com/big.js", "20230110101636", b"x" * 500, "text/javascript")
    archive = FakeArchive([capture])
    when = parse_timestamp(capture.timestamp)
    assert when is not None
    async with make_client(archive, cache=ArchiveCache(conn, now=Clock())) as client:
        short = await client.snapshot(when, capture.url, max_bytes=100)
        shorter = await client.snapshot(when, capture.url, max_bytes=50)  # from the cache, cut again
        longer = await client.snapshot(when, capture.url, max_bytes=200)  # fetched again
    assert (short.truncated, len(short.body)) == (True, 100)
    assert (shorter.truncated, len(shorter.body)) == (True, 50)
    assert (longer.truncated, len(longer.body)) == (True, 200)
    assert sum(request.url.path.startswith("/web/") for request in archive.requests) == 2


async def test_no_query_value_is_ever_written_to_the_database(tmp_path: Path) -> None:
    """safety.md rule 5: a planted query value never reaches the database file, its WAL, or a stored body."""
    db_path = tmp_path / "necropolis.db"
    conn = connect(db_path)
    base = "https://shop.example.com"
    captures = [
        FakeCapture(f"{base}/", "20240301120000", b'<script src="/static/app.js"></script>'),
        FakeCapture(f"{base}/static/app.js?token={SECRET}", "20240301120000", b"fetch('/api/v2/x')", "text/javascript"),
        FakeCapture(f"{base}/api/v1/reset?token={SECRET}&email=victim%40example.org", "20230110101636", b"{}"),
        FakeCapture(f"{base}/api/v1/users/1?session={SECRET}", "20230110101636", b"{}", "application/json"),
        FakeCapture(f"{base}/api/v1/users/2", "20230110101636", b"{}", "application/json"),
    ]
    archive = FakeArchive(captures, page_size=1)  # every resume key is built from the next row's URL
    cache = ArchiveCache(conn, now=Clock())
    async with make_client(archive, cache=cache) as client:
        rows = [row async for row in client.cdx_rows(CdxQuery.listing("shop.example.com", match_type="host"), cap=99)]
        for row in rows:
            address = row.address()
            assert address is not None
            await client.snapshot(row.timestamp, address, url_hash=row.original_sha256)
    assert any(SECRET in key for key in archive.resume_keys)  # the hostile part really was there
    conn.close()

    for path in tmp_path.iterdir():  # the database, and its -wal and -shm files if any are left
        assert SECRET.encode() not in path.read_bytes(), path.name
    check = sqlite3.connect(db_path)
    stored = check.execute("SELECT req_hash, body, meta FROM archive_cache").fetchall()
    check.close()
    assert len(stored) == 1 + len(captures)  # the listing, and every snapshot
    for req_hash, body, meta in stored:
        assert SECRET not in req_hash
        assert SECRET.encode() not in zlib.decompress(body)
        assert SECRET not in meta
    assert any(zlib.decompress(body).startswith(b'{"version":1') for _, body, _ in stored)


def _rows() -> list[CaptureRow]:
    header = ["timestamp", "original", "mimetype", "statuscode", "skipcount", "endtimestamp"]
    rows = [
        header,
        ["20230110101636", "https://shop.example.com/", "text/html", "200", "3", "20240301120000"],
        ["20230110101636", f"https://shop.example.com/static/app.js?v={SECRET}", "text/javascript", "200", "0", "-"],
        ["20230110102038", "https://shop.example.com/api/v1/users/2", "-", "-", "0", "20230110102038"],
    ]
    return list(parse_page(json.dumps(rows).encode()).rows)
