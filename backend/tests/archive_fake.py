"""A hand-written stand-in for web.archive.org, served through httpx `MockTransport` (testing.md).

It answers CDX queries (match types, filters, `collapse=urlkey` with counters, resume keys, negative limits) and
raw `id_` snapshots (closest capture, redirects, replayed encodings), and records every request. Fixtures built on
it use example.com hosts, or our own demo domain with our own demo-site files.

Resume keys are built like the real server's: from the next row's URL key and timestamp, printed URL-encoded. So
they can hold an archived query value, and only a key sent back verbatim finds its page.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import re
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

import brotli
import httpx

from necropolis.archive import ArchiveCache, ArchiveClient, parse_timestamp

DEMO_SITE = Path(__file__).resolve().parents[2] / "demo-site" / "static"
HEADER = ["timestamp", "original", "mimetype", "statuscode"]


@dataclass(frozen=True)
class FakeCapture:
    url: str  # as archived, query included
    timestamp: str  # 14 digits
    body: bytes = b""
    mimetype: str = "text/html"
    status: int = 200
    encoding: str | None = "gzip"  # raw copies keep the encoding the site sent


def encode(body: bytes, encoding: str | None) -> bytes:
    if encoding == "gzip":
        return gzip.compress(body)
    if encoding == "deflate":
        return zlib.compress(body)
    if encoding == "br":
        return brotli.compress(body)
    return body


def respond(status: int, headers: dict[str, str] | None = None, raw: bytes = b"") -> httpx.Response:
    """A response whose body is still an unread stream, as from the network: `content=` would make httpx read and
    decode it at once, past the client's own bounded decoder."""
    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(raw))


def urlkey(url: str) -> str:
    """Roughly the archive's URL key: no scheme, no `www.`, no default port, lowercase host."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    port = f":{parts.port}" if parts.port not in (None, 80, 443) else ""
    query = f"?{parts.query}" if parts.query else ""
    return f"{host}{port}{parts.path or '/'}{query}"


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


@dataclass
class FakeArchive:
    captures: list[FakeCapture]
    page_size: int | None = None  # None: as the client asks
    counters: bool = True  # whether the CDX answers carry skipcount and endtimestamp
    redirects: dict[str, str] = field(default_factory=dict)  # archived URL -> Location to answer its snapshot with
    unavailable: Callable[[httpx.Request], bool] | None = None  # answer 503 to these requests
    hostile: bool = False  # CDX answers ignore the query's URL and list every capture, on any host
    requests: list[httpx.Request] = field(default_factory=list)
    resume_keys: dict[str, int] = field(default_factory=dict)  # key as sent -> index of the next row

    def __post_init__(self) -> None:
        self.captures = sorted(self.captures, key=lambda c: (urlkey(c.url), c.timestamp))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.unavailable is not None and self.unavailable(request):
            return respond(503)
        if request.url.path == "/cdx/search/cdx":
            return self._cdx(request)
        if request.url.path.startswith("/web/"):
            return self._snapshot(request)
        return respond(404)

    def _cdx(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        url = params["url"]
        match_type = params.get("matchType", "exact")
        if self.hostile:
            rows = list(self.captures)
        elif match_type == "exact":
            rows = [c for c in self.captures if urlkey(c.url) == urlkey(f"https://{url}")]
        elif match_type == "host":
            rows = [c for c in self.captures if _host(c.url) == url.lower().removeprefix("www.")]
        elif match_type == "domain":
            host = url.lower().removeprefix("www.")
            rows = [c for c in self.captures if _host(c.url) == host or _host(c.url).endswith(f".{host}")]
        else:
            return respond(400)
        for item in params.get_list("filter"):
            name, _, pattern = item.partition(":")
            value = {"statuscode": lambda c: str(c.status), "mimetype": lambda c: c.mimetype}[name]
            rows = [c for c in rows if re.fullmatch(pattern, value(c))]
        if "from" in params:
            rows = [c for c in rows if c.timestamp[: len(params["from"])] >= params["from"]]
        if "to" in params:
            rows = [c for c in rows if c.timestamp[: len(params["to"])] <= params["to"]]

        with_counters = self.counters and params.get("showSkipCount") == "true"
        out: list[list[str]] = []
        if params.get("collapse") == "urlkey":
            groups: dict[str, list[FakeCapture]] = {}
            for capture in rows:
                groups.setdefault(urlkey(capture.url), []).append(capture)
            for group in groups.values():
                first = group[0]
                row = [first.timestamp, first.url, first.mimetype, str(first.status)]
                if with_counters:
                    row += [str(len(group) - 1), group[-1].timestamp]
                out.append(row)
        else:
            out = [[c.timestamp, c.url, c.mimetype, str(c.status)] for c in rows]

        limit = int(params.get("limit", "150000"))
        resume: str | None = None
        if limit < 0:
            out = out[limit:]
        else:
            start = self._resume_start(request)
            if start is None:
                return respond(400)  # a key the server never printed, or one that was re-encoded
            size = self.page_size or limit
            if start + size < len(out):
                following = out[start + size]
                resume = quote_plus(f"{urlkey(following[1])} {following[0]}")
                self.resume_keys[resume] = start + size
            out = out[start : start + size]
        header = HEADER + (["skipcount", "endtimestamp"] if with_counters and params.get("collapse") else [])
        data: list[list[str]] = [header, *out] if (out or resume) else []
        if resume is not None and params.get("showResumeKey") == "true":
            data += [[], [resume]]
        return respond(200, {"Content-Encoding": "gzip"}, gzip.compress(json.dumps(data).encode()))

    def _resume_start(self, request: httpx.Request) -> int | None:
        for part in request.url.query.split(b"&"):
            name, _, value = part.partition(b"=")
            if name == b"resumeKey":
                return self.resume_keys.get(value.decode("ascii"))
        return 0

    def _snapshot(self, request: httpx.Request) -> httpx.Response:
        match = re.fullmatch(r"/web/([0-9]{14})id_/(.+)", request.url.raw_path.decode("ascii"))
        if match is None:
            return respond(404)
        stamp, url = match.groups()
        if url in self.redirects:
            return respond(302, {"Location": self.redirects[url]})
        same = [c for c in self.captures if c.url == url]
        if not same:
            return respond(404)
        wanted = parse_timestamp(stamp)
        assert wanted is not None

        def distance(capture: FakeCapture) -> tuple[float, str]:
            when = parse_timestamp(capture.timestamp)
            assert when is not None
            return abs((when - wanted).total_seconds()), capture.timestamp

        closest = min(same, key=distance)
        if closest.timestamp != stamp:
            return respond(302, {"Location": f"https://web.archive.org/web/{closest.timestamp}id_/{url}"})
        served = parse_timestamp(closest.timestamp)
        assert served is not None
        headers = {"Content-Type": closest.mimetype, "Memento-Datetime": format_datetime(served, usegmt=True)}
        if closest.encoding:
            headers["Content-Encoding"] = closest.encoding
        return respond(closest.status, headers, encode(closest.body, closest.encoding))

    def hosts_requested(self) -> set[str]:
        return {request.url.host for request in self.requests}


class FakeTime:
    """An injected clock and sleep: waiting takes no real time, and every wait is recorded."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


def make_client(
    archive: FakeArchive,
    *,
    cache: ArchiveCache | None = None,
    time: FakeTime | None = None,
    on_request: Callable[[httpx.Request], None] | None = None,
    now: Callable[[], datetime] | None = None,
) -> ArchiveClient:
    clock = time or FakeTime()
    extra = {} if now is None else {"now": now}
    return ArchiveClient(
        cache=cache,
        transport=archive.transport(),
        rps=1.0,
        sleep=clock.sleep,
        clock=clock.clock,
        on_request=on_request,
        **extra,  # type: ignore[arg-type]
    )


def demo_file(name: str) -> bytes:
    return (DEMO_SITE / name).read_bytes()


def shop_history(host: str = "shop.example.com") -> list[FakeCapture]:
    """The demo site's story on an example.com host: front end v1 in 2023, v2 since 2024 (the v1 API still up)."""
    base = f"https://{host}"
    json_type = "application/json"
    return [
        FakeCapture(f"{base}/", "20230110101636", demo_file("index.v1.html")),
        FakeCapture(f"{base}/", "20240301120000", demo_file("index.v2.html")),
        FakeCapture(f"{base}/static/app.v1.js", "20230110101636", demo_file("app.v1.js"), "application/javascript"),
        FakeCapture(f"{base}/static/app.v2.js", "20240301120000", demo_file("app.v2.js"), "application/javascript"),
        FakeCapture(f"{base}/static/style.css", "20230110101636", demo_file("style.css"), "text/css"),
        FakeCapture(f"{base}/api/v1/users/1", "20230110101636", b'{"data": {}}', json_type),
        FakeCapture(f"{base}/api/v1/users/2", "20230110102038", b'{"data": {}}', json_type),
        FakeCapture(f"{base}/api/v1/status", "20230110101636", b'{"status": "ok"}', json_type),
        FakeCapture(f"{base}/api/v1/status", "20240301120500", b'{"status": "ok"}', json_type),
    ]
