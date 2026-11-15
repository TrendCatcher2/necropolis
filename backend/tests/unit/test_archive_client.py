"""ArchiveClient (Req exhumer:3.1, 3.2, 3.4, 4.2; safety.md rules 1, 6 and 7)."""

from __future__ import annotations

import asyncio
import gzip
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from necropolis import USER_AGENT
from necropolis.archive import (
    ArchiveCache,
    ArchiveClient,
    ArchiveError,
    ArchiveHostViolation,
    ArchiveUnavailable,
    CdxQuery,
    CdxStats,
    SnapshotUnavailable,
    parse_timestamp,
)
from necropolis.archive import client as client_module
from necropolis.archive.client import _ArchiveOnly
from tests.archive_fake import FakeArchive, FakeCapture, FakeTime, make_client, respond, shop_history

WHEN = datetime(2023, 1, 10, 10, 16, 36, tzinfo=UTC)
LATER = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC)
HEADER = ["timestamp", "original", "mimetype", "statuscode"]
LISTING = CdxQuery.listing("shop.example.com", match_type="host")

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def client_for(
    handler: Handler,
    *,
    time: FakeTime | None = None,
    rps: float = 1.0,
    on_request: Callable[[httpx.Request], None] | None = None,
    cache: ArchiveCache | None = None,
) -> ArchiveClient:
    clock = time or FakeTime()
    return ArchiveClient(
        cache=cache,
        transport=httpx.MockTransport(handler),
        rps=rps,
        sleep=clock.sleep,
        clock=clock.clock,
        now=lambda: NOW,
        on_request=on_request,
    )


def replay(body: bytes = b"ok", when: datetime = WHEN, status: int = 200) -> httpx.Response:
    return respond(status, {"Memento-Datetime": format_datetime(when, usegmt=True)}, body)


def cdx(rows: list[object]) -> httpx.Response:
    return respond(200, {"Content-Encoding": "gzip"}, gzip.compress(json.dumps(rows).encode()))


# Req 3.4: web.archive.org only


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://shop.example.com/api/v1/users/1",
        "http://web.archive.org/web/20230110101636id_/https://shop.example.com/",
        "https://web.archive.org:8443/",
        "https://user:pw@web.archive.org/",
        "https://web.archive.org.example.com/",
        "https://archive.org/",
        "https://127.0.0.1/",
    ],
)
async def test_the_transport_refuses_every_other_destination(url: str) -> None:
    sent: list[httpx.Request] = []
    guard = _ArchiveOnly(httpx.MockTransport(lambda request: sent.append(request) or respond(200)))
    with pytest.raises(ArchiveHostViolation):
        await guard.handle_async_request(httpx.Request("GET", url))
    assert sent == []


async def test_the_client_itself_cannot_send_elsewhere() -> None:
    attempted: list[httpx.Request] = []
    sent: list[httpx.Request] = []
    async with client_for(lambda request: sent.append(request) or respond(200), on_request=attempted.append) as client:
        with pytest.raises(ArchiveHostViolation):
            await client._get("https://example.com/", None, max_bytes=10, truncate=True)
    assert [request.url.host for request in attempted] == ["example.com"]  # attempted, refused before sending
    assert sent == []


async def test_requests_carry_the_user_agent_and_never_a_cookie() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        response = replay()
        response.headers["Set-Cookie"] = "session=abc; Path=/; Secure"
        return response

    async with client_for(handler) as client:
        await client.snapshot(WHEN, "https://shop.example.com/a")
        await client.snapshot(WHEN, "https://shop.example.com/b")
    assert len(sent) == 2
    for request in sent:
        assert request.headers["user-agent"] == USER_AGENT
        assert "@" not in USER_AGENT  # safety.md rule 4: no personal data
        assert request.headers["accept-encoding"] == "gzip, deflate, br"
        assert "cookie" not in request.headers
        assert "authorization" not in request.headers


# Req 3.1: one request at a time, at most `rps` per second


async def test_requests_are_paced() -> None:
    time = FakeTime()
    async with client_for(lambda request: replay(), time=time, rps=0.5) as client:
        for name in ("a", "b", "c"):
            await client.snapshot(WHEN, f"https://shop.example.com/{name}")
        time.now += 60  # idle for a minute: the next request goes at once
        await client.snapshot(WHEN, "https://shop.example.com/d")
    assert time.sleeps == [2.0, 2.0]


@pytest.mark.parametrize("rps", [0, -1.0, 1.01, 2.0])
def test_the_rate_never_exceeds_one_per_second(rps: float) -> None:
    with pytest.raises(ValueError, match="rule 6"):
        ArchiveClient(rps=rps)


async def test_one_request_at_a_time_even_when_called_concurrently() -> None:
    active = peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        for _ in range(5):
            await asyncio.sleep(0)
        active -= 1
        return replay()

    async with client_for(handler) as client:
        await asyncio.gather(*(client.snapshot(WHEN, f"https://shop.example.com/{n}") for n in range(6)))
    assert peak == 1


# Req 3.2: Retry-After, then exponential backoff, then give up


async def test_429_with_retry_after_in_seconds() -> None:
    answers = iter([respond(429, {"Retry-After": "7"}), replay()])
    time = FakeTime()
    waits: list[tuple[float, int | None]] = []
    async with client_for(lambda request: next(answers), time=time) as client:
        client.add_wait_listener(lambda delay, status: waits.append((delay, status)))
        snapshot = await client.snapshot(WHEN, "https://shop.example.com/a")
    assert snapshot.body == b"ok"
    assert time.sleeps == [7.0]
    assert waits == [(7.0, 429)]


async def test_retry_after_as_an_http_date() -> None:
    answers = iter([respond(503, {"Retry-After": format_datetime(NOW + timedelta(seconds=30), usegmt=True)}), replay()])
    time = FakeTime()
    async with client_for(lambda request: next(answers), time=time) as client:
        await client.snapshot(WHEN, "https://shop.example.com/a")
    assert time.sleeps == [30.0]


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_backoff_doubles_then_the_client_gives_up(status: int) -> None:
    time = FakeTime()
    sent: list[httpx.Request] = []
    async with client_for(lambda request: sent.append(request) or respond(status), time=time) as client:
        with pytest.raises(ArchiveUnavailable, match=str(status)):
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert time.sleeps == [2.0, 4.0, 8.0, 16.0, 32.0]
    assert len(sent) == 6  # the first try and 5 retries


async def test_failed_connections_are_retried_like_a_busy_archive() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("connection refused", request=request)
        return replay()

    waits: list[tuple[float, int | None]] = []
    async with client_for(handler) as client:
        client.add_wait_listener(lambda delay, status: waits.append((delay, status)))
        assert (await client.snapshot(WHEN, "https://shop.example.com/a")).body == b"ok"
    assert waits == [(2.0, None)]


async def test_connections_that_keep_failing_end_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async with client_for(handler) as client:
        with pytest.raises(ArchiveUnavailable, match="no connection") as info:
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert isinstance(info.value.__cause__, httpx.ReadTimeout)


async def test_a_retry_after_over_two_minutes_ends_the_wait_at_once() -> None:
    time = FakeTime()
    async with client_for(lambda request: respond(429, {"Retry-After": "3600"}), time=time) as client:
        with pytest.raises(ArchiveUnavailable, match="3600"):
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert time.sleeps == []


async def test_a_replayed_503_is_the_sites_page_not_the_archive_asking_to_wait() -> None:
    sent: list[httpx.Request] = []
    async with client_for(lambda request: sent.append(request) or replay(b"down", status=503)) as client:
        with pytest.raises(SnapshotUnavailable) as info:
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert info.value.reason == "status_503"
    assert len(sent) == 1


async def test_a_removed_wait_listener_is_not_called() -> None:
    answers = iter([respond(429), replay()])
    waits: list[float] = []

    def listener(delay: float, status: int | None) -> None:
        waits.append(delay)

    async with client_for(lambda request: next(answers)) as client:
        client.add_wait_listener(listener)
        client.remove_wait_listener(listener)
        client.remove_wait_listener(listener)  # removing twice is harmless
        await client.snapshot(WHEN, "https://shop.example.com/a")
    assert waits == []


# Snapshots (Req 4.2)


async def test_raw_snapshot_request_and_served_timestamp() -> None:
    sent: list[httpx.Request] = []
    async with client_for(lambda request: sent.append(request) or replay(b"js", when=LATER)) as client:
        snapshot = await client.snapshot(WHEN, "https://shop.example.com/static/app.js?v=2#top")
    assert sent[0].url.raw_path == b"/web/20230110101636id_/https://shop.example.com/static/app.js?v=2"
    assert snapshot.timestamp == LATER  # the capture the archive served, from Memento-Datetime
    assert snapshot.url == "https://shop.example.com/static/app.js?v"
    assert (snapshot.body, snapshot.truncated) == (b"js", False)


async def test_without_memento_datetime_the_requested_capture_is_assumed() -> None:
    async with client_for(lambda request: respond(200, {}, b"x")) as client:
        assert (await client.snapshot(WHEN, "https://shop.example.com/a")).timestamp == WHEN


async def test_the_archive_serves_the_closest_capture_through_a_redirect() -> None:
    archive = FakeArchive(shop_history())
    async with make_client(archive) as client:
        snapshot = await client.snapshot(datetime(2024, 1, 1, tzinfo=UTC), "https://shop.example.com/api/v1/status")
    assert snapshot.timestamp == datetime(2024, 3, 1, 12, 5, 0, tzinfo=UTC)
    assert snapshot.body == b'{"status": "ok"}'
    assert archive.hosts_requested() == {"web.archive.org"}


@pytest.mark.parametrize(
    "location",
    [
        "/web/20240301120000id_/https://shop.example.com/a",
        "https://web.archive.org/web/20240301120000id_/https://shop.example.com/a",
        "http://web.archive.org/web/20240301120000id_/https://shop.example.com/a",  # followed over https
        "/web/20240301120000/https://shop.example.com/a",  # the archive may drop "id_" on a redirect
    ],
)
async def test_redirects_within_the_archive_are_followed(location: str) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.raw_path.startswith(b"/web/20230110101636"):
            return respond(302, {"Location": location})
        return replay(b"later", when=LATER)

    async with client_for(handler) as client:
        snapshot = await client.snapshot(WHEN, "https://shop.example.com/a")
    assert snapshot.body == b"later"
    assert sent[-1].url.raw_path == b"/web/20240301120000id_/https://shop.example.com/a"
    assert all(request.url.scheme == "https" and request.url.host == "web.archive.org" for request in sent)


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example.net/web/20240301120000id_/https://shop.example.com/a",
        "//evil.example.net/web/20240301120000id_/https://shop.example.com/a",
        "https://web.archive.org@evil.example.net/web/20240301120000id_/https://shop.example.com/a",
        "https://web.archive.org:8080/web/20240301120000id_/https://shop.example.com/a",
        "https://web.archive.org/account/login",
        "ftp://web.archive.org/web/20240301120000id_/x",
        "javascript:alert(1)",
        "",
        # Malformed: httpx itself would raise on these if it saw them (it parses Location even when not following)
        "http://[::1",
        "https://web.archive.org:99999/web/20240301120000id_/https://shop.example.com/a",
        "/web/2024/https://shop.example.com/a",
        "https://we b.archive.org/web/20240301120000id_/https://shop.example.com/a",
    ],
)
async def test_redirects_off_the_archive_are_never_followed(location: str) -> None:
    archive = FakeArchive([], redirects={"https://shop.example.com/a": location})
    async with make_client(archive) as client:
        with pytest.raises(SnapshotUnavailable) as info:
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert info.value.reason == "redirect_off_archive"
    assert archive.hosts_requested() == {"web.archive.org"}
    assert len(archive.requests) == 1


async def test_a_redirect_loop_ends() -> None:
    sent: list[httpx.Request] = []
    loop = "/web/20230110101636id_/https://shop.example.com/a"
    async with client_for(lambda request: sent.append(request) or respond(302, {"Location": loop})) as client:
        with pytest.raises(SnapshotUnavailable) as info:
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert info.value.reason == "too_many_redirects"
    assert len(sent) == 6


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (respond(404), "status_404"),
        (replay(b"gone", status=410), "status_410"),
        (respond(200, {"Content-Encoding": "gzip"}, b"not gzip at all"), "bad_encoding"),
        (respond(200, {"Content-Encoding": "zstd"}, b"x"), "bad_encoding"),
    ],
)
async def test_snapshot_failures_name_their_reason(response: httpx.Response, reason: str) -> None:
    async with client_for(lambda request: response) as client:
        with pytest.raises(SnapshotUnavailable) as info:
            await client.snapshot(WHEN, "https://shop.example.com/a")
    assert info.value.reason == reason


async def test_snapshots_are_capped_after_decoding() -> None:
    big = b"a" * (3 * 1024 * 1024)
    archive = FakeArchive([FakeCapture("https://shop.example.com/app.js", "20230110101636", big, "text/javascript")])
    async with make_client(archive) as client:
        snapshot = await client.snapshot(WHEN, "https://shop.example.com/app.js")
    assert len(snapshot.body) == 2 * 1024 * 1024
    assert snapshot.truncated


# CDX pages (Req 2.2)


async def test_pages_are_followed_with_the_resume_key_sent_back_verbatim() -> None:
    archive = FakeArchive(shop_history(), page_size=2)
    stats = CdxStats()
    async with make_client(archive) as client:
        rows = [row async for row in client.cdx_rows(LISTING, cap=100, stats=stats)]
    originals = [row.original for row in rows]
    assert len(originals) == len(set(originals)) == 7  # every URL once
    assert stats.pages == 4
    assert len(archive.requests) == 4  # a re-encoded key would have been answered 400
    assert any("%2F" in key for key in archive.resume_keys)


async def test_the_cap_stops_paging() -> None:
    archive = FakeArchive(shop_history(), page_size=2)
    stats = CdxStats()
    async with make_client(archive) as client:
        rows = [row async for row in client.cdx_rows(LISTING, cap=3, stats=stats)]
    assert len(rows) == 3
    assert stats.capped
    assert len(archive.requests) == 2


async def test_a_repeated_resume_key_is_an_error_not_a_loop() -> None:
    page = [HEADER, ["20230110101636", "https://shop.example.com/", "text/html", "200"], [], ["same"]]
    async with client_for(lambda request: cdx(page)) as client:
        with pytest.raises(ArchiveError, match="resume keys"):
            _ = [row async for row in client.cdx_rows(LISTING, cap=100)]


async def test_endless_empty_pages_end() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return cdx([HEADER, [], [f"key{len(sent)}"]])

    async with client_for(handler) as client:
        with pytest.raises(ArchiveError):
            _ = [row async for row in client.cdx_rows(LISTING, cap=10)]
    assert len(sent) == 50


async def test_counters_must_be_on_every_page() -> None:
    pages = iter(
        [
            cdx(
                [
                    [*HEADER, "skipcount", "endtimestamp"],
                    ["20230110101636", "https://shop.example.com/a", "text/html", "200", "1", "20240101000000"],
                    [],
                    ["next"],
                ]
            ),
            cdx([HEADER, ["20230110101636", "https://shop.example.com/b", "text/html", "200"]]),
        ]
    )
    stats = CdxStats()
    async with client_for(lambda request: next(pages)) as client:
        rows = [row async for row in client.cdx_rows(LISTING, cap=100, stats=stats)]
    assert len(rows) == 2
    assert stats.counters is False


async def test_a_gzipped_cdx_answer_without_a_header_is_read() -> None:
    body = gzip.compress(json.dumps([HEADER, ["20230110101636", "https://shop.example.com/", "-", "-"]]).encode())
    async with client_for(lambda request: respond(200, {}, body)) as client:
        rows = [row async for row in client.cdx_rows(LISTING, cap=100)]
    assert [row.original for row in rows] == ["https://shop.example.com/"]


@pytest.mark.parametrize(
    "response",
    [respond(400, {}, b"bad request"), respond(200, {}, b"<html>maintenance</html>"), respond(200, {}, b"{}")],
)
async def test_cdx_answers_that_are_not_listings(response: httpx.Response) -> None:
    async with client_for(lambda request: response) as client:
        with pytest.raises(ArchiveError) as info:
            await client.cdx_page(LISTING)
    assert not isinstance(info.value, ArchiveUnavailable)


async def test_an_oversized_cdx_page_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "CDX_PAGE_MAX_BYTES", 100)
    rows = [HEADER, *(["20230110101636", f"https://shop.example.com/{n}", "-", "-"] for n in range(20))]
    async with client_for(lambda request: cdx(rows)) as client:
        with pytest.raises(ArchiveError, match="over 100 bytes"):
            await client.cdx_page(LISTING)


async def test_the_newest_root_query_reads_the_last_rows() -> None:
    archive = FakeArchive(shop_history())
    async with make_client(archive) as client:
        rows = [row async for row in client.cdx_rows(CdxQuery.newest_root("shop.example.com"), cap=3)]
    assert [row.timestamp for row in rows] == [parse_timestamp("20230110101636"), parse_timestamp("20240301120000")]
    assert len(archive.requests) == 1
