"""`ArchiveClient`: the only HTTP client of the exhumer and `wayback-mcp`. Passive: `web.archive.org` only.

Req exhumer:3.1 to 3.4; safety.md rules 1, 6 and 7.
"""

from __future__ import annotations

import asyncio
import email.utils
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from urllib.parse import quote, urlencode

import httpx

from necropolis import USER_AGENT
from necropolis.archive.cache import ArchiveCache, cache_key, dump_listing, load_listing, utc_now
from necropolis.archive.cdx import CdxFormatError, parse_page, url_sha256
from necropolis.archive.decode import BoundedDecoder, DecodeError
from necropolis.archive.models import CDX_PAGE_ROWS, CaptureRow, CdxPage, CdxQuery, CdxStats, Snapshot
from necropolis.archive.timestamps import format_timestamp, parse_timestamp
from necropolis.normaliser import redact_url
from necropolis.settings import get_settings

ARCHIVE_HOST = "web.archive.org"
ARCHIVE_BASE = f"https://{ARCHIVE_HOST}"
CDX_PATH = "/cdx/search/cdx"
SNAPSHOT_MAX_BYTES = 2 * 1024 * 1024  # Req 4.2 and 4.7; safety.md rule 7
CDX_PAGE_MAX_BYTES = 32 * 1024 * 1024
BACKOFF_S = (2.0, 4.0, 8.0, 16.0, 32.0)  # Req 3.2; after the fifth retry, give up
MAX_RETRY_AFTER_S = 120.0  # a longer Retry-After ends the run as partial instead of hanging it
# 429 and 503 per Req 3.2. 502 and 504, and connections that fail or time out, are retried the same way: they are
# the archive's gateway saying the same thing.
RETRY_STATUSES = frozenset({429, 502, 503, 504})
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_WAYBACK_PATH = re.compile(r"/web/([0-9]{14})(?:[a-z]{2}_)?/(.+)", re.DOTALL)
_LOCATION = "x-necropolis-location"  # where the host check moves a redirect's Location (see _ArchiveOnly)

WaitListener = Callable[[float, int | None], None]


class ArchiveError(Exception):
    """The archive answered, but not with what was asked for."""


class ArchiveUnavailable(ArchiveError):
    """The archive still failed after the retries (Req 3.2). The run ends `partial` (Req 6.2)."""


class UndecodableResponse(ArchiveError):
    """The body did not match its `Content-Encoding`."""


class SnapshotUnavailable(ArchiveError):
    """This one snapshot cannot be had. The run skips it and counts it (exhumer design, "Error handling")."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ArchiveHostViolation(Exception):  # the spec's name
    """A request for a host other than web.archive.org (Req 3.4). A bug: never caught and counted."""


class _ArchiveOnly(httpx.AsyncBaseTransport):
    """The transport-level host check (Req 3.4). It sees every request the client sends, each hop included."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        if url.scheme != "https" or url.host != ARCHIVE_HOST or url.port not in (None, 443) or url.userinfo:
            raise ArchiveHostViolation(f"refused {url.host!r}: the archive client talks to {ARCHIVE_HOST} only")
        for name in ("cookie", "authorization", "proxy-authorization"):
            request.headers.pop(name, None)
        response = await self._inner.handle_async_request(request)
        # httpx parses a redirect's Location even with follow_redirects=False, and a malformed one raises an error
        # that would be retried like a failed connection. Hidden from httpx here, it is read by the client itself.
        location = response.headers.get("location")
        if location is not None:
            del response.headers["location"]
            response.headers[_LOCATION] = location
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


@dataclass(frozen=True, slots=True)
class _Fetched:
    status: int
    headers: httpx.Headers
    url: httpx.URL
    body: bytes
    truncated: bool


@dataclass(frozen=True, slots=True)
class _Retry:
    status: int | None  # None: the connection failed or timed out
    retry_after: float | None


class ArchiveClient:
    """One request at a time, at most `rps` per second, cached, retried politely (safety.md rule 6).

    Inject `transport` (an httpx `MockTransport` in tests), `sleep`, `clock` and `now` to test without waiting.
    `on_request` sees every request before the host check, so a test can prove nothing else was even attempted.
    """

    def __init__(
        self,
        *,
        cache: ArchiveCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        rps: float | None = None,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utc_now,
        on_request: Callable[[httpx.Request], None] | None = None,
    ) -> None:
        rate = get_settings().archive_rps if rps is None else rps
        if not 0 < rate <= 1:
            raise ValueError("the archive rate must be above 0 and at most 1 request per second (safety.md rule 6)")
        self._interval = 1.0 / rate
        self._cache = cache
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._lock = asyncio.Lock()
        self._next_start: float | None = None
        self._wait_listeners: list[WaitListener] = []
        hooks: dict[str, list[Callable[[httpx.Request], Awaitable[None]]]] = {}
        if on_request is not None:
            observe = on_request

            async def hook(request: httpx.Request) -> None:
                observe(request)

            hooks["request"] = [hook]
        self._http = httpx.AsyncClient(
            base_url=ARCHIVE_BASE,
            transport=_ArchiveOnly(transport if transport is not None else httpx.AsyncHTTPTransport()),
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate, br"},
            follow_redirects=False,  # redirects are followed by hand, and only within the archive
            timeout=TIMEOUT,
            trust_env=False,  # no proxy, netrc or certificate settings from the environment
            event_hooks=hooks,
        )

    async def __aenter__(self) -> ArchiveClient:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def add_wait_listener(self, listener: WaitListener) -> None:
        """`listener(delay_s, status)` is called before each backoff (status None: the connection failed)."""
        self._wait_listeners.append(listener)

    def remove_wait_listener(self, listener: WaitListener) -> None:
        if listener in self._wait_listeners:
            self._wait_listeners.remove(listener)

    # CDX

    async def cdx_page(self, query: CdxQuery, resume_key: str | None = None) -> CdxPage:
        fetched = await self._get(
            cdx_target(query, resume_key), None, max_bytes=CDX_PAGE_MAX_BYTES, truncate=False, sniff_gzip=True
        )
        if fetched.status != 200:
            raise ArchiveError(f"the CDX API answered {fetched.status}")
        try:
            return parse_page(fetched.body)
        except CdxFormatError as exc:
            raise ArchiveError(str(exc)) from exc

    async def cdx_rows(self, query: CdxQuery, *, cap: int, stats: CdxStats | None = None) -> AsyncIterator[CaptureRow]:
        """Every row of a query, page by page via resume keys (Req 2.2), stopping at `cap` rows (Req 2.3).

        A complete listing is cached whole and served from there for 7 days (Req 3.3).
        """
        stats = CdxStats() if stats is None else stats
        key = cache_key("cdx", f"cap={cap}", urlencode(query.params()))
        cached = self._cache.get(key) if self._cache is not None else None
        if cached is not None:
            try:
                rows, saved = load_listing(cached.body)
            except (ValueError, KeyError, TypeError):
                rows = None
            if rows is not None:
                stats.from_cache = True
                stats.pages += saved.pages
                stats.malformed += saved.malformed
                stats.capped = saved.capped
                stats.counters = saved.counters
                for row in rows:
                    stats.rows += 1
                    yield row
                return

        rows = []
        resume: str | None = None
        seen_keys: set[str] = set()
        max_pages = cap // CDX_PAGE_ROWS + 50  # a server that keeps sending empty pages cannot keep us forever
        while True:
            page = await self.cdx_page(query, resume)
            stats.pages += 1
            stats.malformed += page.malformed
            if page.rows or page.malformed:
                stats.counters = page.counters if stats.counters is None else stats.counters and page.counters
            for row in page.rows:
                if len(rows) >= cap:
                    stats.capped = True
                    break
                rows.append(row)
                stats.rows += 1
                yield row
            if stats.capped or page.resume_key is None:
                break
            if len(rows) >= cap:
                stats.capped = True
                break
            if page.resume_key in seen_keys or stats.pages >= max_pages:
                raise ArchiveError("the CDX API kept sending resume keys without new results")
            seen_keys.add(page.resume_key)
            resume = page.resume_key
        if self._cache is not None:
            self._cache.put(key, dump_listing(rows, stats), {"kind": "cdx_listing"})

    # Snapshots

    def cached_snapshot(
        self, timestamp: datetime, url_hash: str, *, max_bytes: int = SNAPSHOT_MAX_BYTES
    ) -> Snapshot | None:
        """A snapshot from the cache only, by the SHA-256 of its archived URL. Never sends a request."""
        return self._cached_snapshot(cache_key("snapshot", format_timestamp(timestamp), url_hash), max_bytes)

    async def snapshot(
        self,
        timestamp: datetime,
        url: str,
        *,
        max_bytes: int = SNAPSHOT_MAX_BYTES,
        url_hash: str | None = None,
    ) -> Snapshot:
        """The raw archived copy (`id_`) of `url` closest to `timestamp`, decoded, at most `max_bytes` (Req 4.2).

        `url` is the URL as archived, query values included. It only goes into the request, never into the cache
        or a log: the cache names it by `url_hash`, its SHA-256 by default.
        """
        stamp = format_timestamp(timestamp)
        key = cache_key("snapshot", stamp, url_hash or url_sha256(url))
        cached = self._cached_snapshot(key, max_bytes)
        if cached is not None:
            return cached
        hop_stamp, hop_url = stamp, url.partition("#")[0]
        for _ in range(MAX_REDIRECTS + 1):
            try:
                fetched = await self._get(f"/web/{hop_stamp}id_/{hop_url}", None, max_bytes=max_bytes, truncate=True)
            except UndecodableResponse as exc:
                raise SnapshotUnavailable("bad_encoding") from exc
            except httpx.InvalidURL as exc:
                raise SnapshotUnavailable("bad_url") from exc
            if 300 <= fetched.status < 400:
                hop = _archive_redirect(fetched.headers.get(_LOCATION), fetched.url)
                if hop is None:
                    raise SnapshotUnavailable("redirect_off_archive")  # never followed (Req 3.4)
                hop_stamp, hop_url = hop
                continue
            if fetched.status != 200:
                raise SnapshotUnavailable(f"status_{fetched.status}")
            served = _memento_datetime(fetched.headers) or parse_timestamp(hop_stamp) or timestamp
            snapshot = Snapshot(
                timestamp=served,
                url=redact_url(hop_url),
                content_type=fetched.headers.get("content-type"),
                body=fetched.body,
                truncated=fetched.truncated,
            )
            if self._cache is not None:
                self._cache.put(
                    key,
                    snapshot.body,
                    {
                        "kind": "snapshot",
                        "timestamp": format_timestamp(served),
                        "url": snapshot.url,
                        "content_type": snapshot.content_type,
                        "truncated": snapshot.truncated,
                        "max_bytes": max_bytes,
                    },
                )
            return snapshot
        raise SnapshotUnavailable("too_many_redirects")

    def _cached_snapshot(self, key: str, max_bytes: int) -> Snapshot | None:
        entry = self._cache.get(key) if self._cache is not None else None
        if entry is None:
            return None
        meta = entry.meta
        stored_cap = meta.get("max_bytes")
        if meta.get("truncated") and not (isinstance(stored_cap, int) and stored_cap >= max_bytes):
            return None  # it was cut shorter than this caller may read
        served = parse_timestamp(meta.get("timestamp"))
        content_type = meta.get("content_type")
        if served is None:
            return None
        return Snapshot(
            timestamp=served,
            url=str(meta.get("url", "")),
            content_type=content_type if isinstance(content_type, str) else None,
            body=entry.body[:max_bytes],
            truncated=bool(meta.get("truncated")) or len(entry.body) > max_bytes,
        )

    # HTTP

    async def _get(
        self,
        path: str,
        params: list[tuple[str, str]] | None,
        *,
        max_bytes: int,
        truncate: bool,
        sniff_gzip: bool = False,
    ) -> _Fetched:
        async with self._lock:  # Req 3.1: one request at a time, including its retries and its body
            last: _Retry | None = None
            cause: BaseException | None = None
            for attempt in range(len(BACKOFF_S) + 1):
                await self._pace()
                try:
                    outcome = await self._attempt(
                        path, params, max_bytes=max_bytes, truncate=truncate, sniff_gzip=sniff_gzip
                    )
                    cause = None
                except httpx.TransportError as exc:
                    outcome, cause = _Retry(status=None, retry_after=None), exc
                if isinstance(outcome, _Fetched):
                    return outcome
                last = outcome
                if attempt == len(BACKOFF_S):
                    break
                delay = BACKOFF_S[attempt] if outcome.retry_after is None else outcome.retry_after
                if delay > MAX_RETRY_AFTER_S:
                    raise ArchiveUnavailable(f"the archive asked us to wait {delay:.0f} s") from cause
                for listener in list(self._wait_listeners):
                    listener(delay, outcome.status)
                await self._sleep(delay)
            status = "no connection" if last is None or last.status is None else str(last.status)
            raise ArchiveUnavailable(f"the archive still failed after {len(BACKOFF_S)} retries ({status})") from cause

    async def _pace(self) -> None:
        now = self._clock()
        start = now if self._next_start is None else max(now, self._next_start)
        if start > now:
            await self._sleep(start - now)
        self._next_start = start + self._interval

    async def _attempt(
        self,
        path: str,
        params: list[tuple[str, str]] | None,
        *,
        max_bytes: int,
        truncate: bool,
        sniff_gzip: bool,
    ) -> _Fetched | _Retry:
        request = self._http.build_request("GET", path, params=None if params is None else tuple(params))
        response = await self._http.send(request, stream=True)
        try:
            # `id_` replays the status the site sent, so a replayed 503 page carries Memento-Datetime and is not the
            # archive asking us to wait. [VERIFY: Memento-Datetime on replayed copies, on the recorded fixture.]
            if response.status_code in RETRY_STATUSES and "memento-datetime" not in response.headers:
                return _Retry(response.status_code, _retry_after(response.headers.get("retry-after"), self._now()))
            body, truncated = b"", False
            if response.status_code == 200:
                if response.is_stream_consumed:
                    # Only an in-memory transport hands over a body httpx has already read and decoded.
                    body, truncated = response.content[:max_bytes], len(response.content) > max_bytes
                else:
                    try:
                        coding = response.headers.get("content-encoding")
                        decoder = BoundedDecoder(coding, max_bytes, sniff_gzip=sniff_gzip)
                        async for chunk in response.aiter_raw():  # raw: the cap is on our own decoder's output
                            if not decoder.feed(chunk):
                                break
                        body = decoder.finish()
                    except DecodeError as exc:
                        raise UndecodableResponse(str(exc)) from exc
                    truncated = decoder.truncated
                if truncated and not truncate:
                    raise ArchiveError(f"the archive's answer is over {max_bytes} bytes")
            return _Fetched(response.status_code, response.headers, request.url, body, truncated)
        finally:
            await response.aclose()


def cdx_target(query: CdxQuery, resume_key: str | None = None) -> str:
    """The CDX request path and query.

    The resume key goes back verbatim: the server prints it already URL-encoded (CDX server README, "Resumption
    Key"), so encoding it again would change it. Only characters outside the URL-safe set are escaped.
    `[VERIFY: on the recorded fixture, page 2 continues where page 1 stopped.]`
    """
    text = urlencode(query.params())
    if resume_key is not None:
        text += "&resumeKey=" + quote(resume_key, safe="%+")
    return f"{CDX_PATH}?{text}"


def _retry_after(value: str | None, now: datetime) -> float | None:
    """Seconds to wait, from `Retry-After` as seconds or as an HTTP date."""
    if value is None:
        return None
    text = value.strip()
    if text.isascii() and text.isdigit() and len(text) <= 9:
        return float(int(text))
    try:
        when = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


def _memento_datetime(headers: httpx.Headers) -> datetime | None:
    value = headers.get("memento-datetime")
    if not value:
        return None
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return when.astimezone(UTC) if when.tzinfo else when.replace(tzinfo=UTC)


def _archive_redirect(location: str | None, base: httpx.URL) -> tuple[str, str] | None:
    """A redirect to another raw copy in the archive: (timestamp, archived URL). None if it leaves the archive."""
    if not location:
        return None
    try:
        target = base.join(location)
    except httpx.InvalidURL:
        return None
    if target.host != ARCHIVE_HOST or target.scheme not in ("http", "https") or target.port not in (None, 80, 443):
        return None
    match = _WAYBACK_PATH.fullmatch(target.raw_path.decode("ascii", "replace"))
    if match is None:
        return None
    return match.group(1), match.group(2)
