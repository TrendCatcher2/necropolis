"""Correctness properties of .kiro/specs/exhumer/design.md.

Property 1: Exhumer is passive (this file).
Properties 2-6: to be added in subsequent tasks.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from necropolis.archive import ArchiveClient, ArchiveHostViolation
from necropolis.archive.client import ARCHIVE_HOST
from necropolis.exhumer.models import Target
from necropolis.exhumer.run import ExhumeJob, run_exhume
from tests.archive_fake import FakeTime

# ---------------------------------------------------------------------------
# Shared Hypothesis strategies
# ---------------------------------------------------------------------------

_LOWER_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_labels = st.text(_LOWER_ALNUM + "-", min_size=1, max_size=12).filter(
    lambda s: s[0] != "-" and s[-1] != "-"
)


@st.composite
def _hostile_domains(draw: st.DrawFn) -> str:
    """A valid registrable domain that is NOT web.archive.org.

    Uses .com, .net, .org and .io: all on the Public Suffix List so the normaliser accepts them,
    but none of them is web.archive.org.
    """
    tld = draw(st.sampled_from(["com", "net", "org", "io"]))
    label = draw(_labels)
    candidate = f"{label}.{tld}"
    if candidate == "archive.org":  # archive.org is not web.archive.org, but skip it to be clear
        return "hostile-domain.com"
    return candidate


@st.composite
def _hostile_url(draw: st.DrawFn) -> str:
    """An absolute https URL on a non-archive registrable domain."""
    domain = draw(_hostile_domains())
    path_parts = draw(st.lists(st.text(_LOWER_ALNUM + "-", min_size=1, max_size=10), min_size=1, max_size=4))
    path = "/api/" + "/".join(path_parts)
    return f"https://{domain}{path}"


@st.composite
def _hostile_js_body(draw: st.DrawFn) -> str:
    """A JS snippet containing absolute URLs on arbitrary non-archive hosts, fetch() context.

    The miner only keeps paths whose registrable domain matches the target, so this tests
    that none of these "hostile" URLs trigger real HTTP requests.
    """
    urls = draw(st.lists(_hostile_url(), min_size=1, max_size=10))
    lines = []
    for url in urls:
        style = draw(st.sampled_from(["fetch", "axios", "get", "post", "url"]))
        if style == "fetch":
            lines.append(f'fetch("{url}")')
        elif style == "axios":
            lines.append(f'axios.get("{url}")')
        elif style == "get":
            lines.append(f'client.get("{url}")')
        elif style == "post":
            lines.append(f'client.post("{url}")')
        else:
            lines.append(f'url: "{url}"')
        # Also embed as a template literal with an interpolation (Req 4.4)
        lines.append(f"fetch(`{url}/${{userId}}/data`)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Recording transport for the passivity test
# ---------------------------------------------------------------------------

HEADER = ["timestamp", "original", "mimetype", "statuscode"]

# The target domain used for the entire test: a real registrable domain that the
# normaliser accepts and that the fake archive can answer for.
_TARGET_HOST = "shop.example.com"
_TARGET = Target(host=_TARGET_HOST, registrable_domain="example.com", scope="host")


def _cdx_response(rows: list[list[str]], resume_key: str | None = None) -> httpx.Response:
    """A minimal CDX JSON response, gzip-compressed, optionally with a resume key."""
    data: list[list[str]] = [HEADER, *rows]
    if resume_key is not None:
        data += [[], [resume_key]]
    body = gzip.compress(json.dumps(data).encode())
    return httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(body))


def _snapshot_response(body: bytes) -> httpx.Response:
    from email.utils import format_datetime

    when = datetime(2023, 1, 10, 10, 16, 36, tzinfo=UTC)
    headers = {
        "Content-Type": "application/javascript",
        "Memento-Datetime": format_datetime(when, usegmt=True),
    }
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


class RecordingTransport(httpx.AsyncBaseTransport):
    """Answers every CDX and snapshot request with minimal synthetic data, and records every URL seen.

    The JS body injected into snapshot responses is configurable so hostile external URLs can be tested.
    """

    def __init__(self, js_body: str = "") -> None:
        self.requested_urls: list[str] = []
        self._js_body = js_body.encode("utf-8")

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Record the full URL *before* any filtering - we want to prove the guard fires before this.
        self.requested_urls.append(str(request.url))
        path = request.url.path

        if path == "/cdx/search/cdx":
            # Return one minimal CDX row (a script on the target host) so the pipeline
            # advances into the JS-mining phase where hostile URLs would be constructed.
            ts = "20230110101636"
            script_url = f"https://{_TARGET_HOST}/static/app.js"
            return _cdx_response([[ts, script_url, "application/javascript", "200"]])

        if path.startswith("/web/") and "id_" in path:
            return _snapshot_response(self._js_body)

        # Root-page fetch: return a minimal HTML page with no <script> tags so the
        # frontend phase completes quickly without spawning more snapshot requests.
        if (path.startswith("/web/") and path.endswith("id_/")) or "/web/-3" in path:
            return httpx.Response(200, stream=httpx.ByteStream(b""))

        # CDX query for the newest root page (negative limit)
        # Return empty so the frontend phase skips gracefully.
        return _cdx_response([])

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Property 1: Exhumer is passive
# Validates: Requirements 3.4; safety rule 1
# ---------------------------------------------------------------------------

# Feature: exhumer, Property 1: Exhumer is passive
# Validates: Req exhumer:3.4; safety rule 1
@given(js_body=_hostile_js_body())
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_every_request_goes_to_the_archive_only(js_body: str) -> None:
    """For any generated CDX data and JS bodies (including absolute URLs to arbitrary hosts),
    every request the exhumer makes goes to web.archive.org and nowhere else.

    **Validates: Requirements 3.4**
    """
    asyncio.run(_run_passivity_check(js_body))


async def _run_passivity_check(js_body: str) -> None:
    transport = RecordingTransport(js_body=js_body)
    fake_time = FakeTime()

    client = ArchiveClient(
        transport=transport,
        rps=1.0,
        sleep=fake_time.sleep,
        clock=fake_time.clock,
    )
    job = ExhumeJob(
        target=_TARGET,
        client=client,
        heartbeat_s=9999.0,  # suppress heartbeat tasks from slowing the test
    )
    async with client:
        await run_exhume(job)

    # Every URL the transport recorded must be on web.archive.org.
    for raw_url in transport.requested_urls:
        host = urlsplit(raw_url).hostname or ""
        assert host == ARCHIVE_HOST, (
            f"Exhumer sent a request to {host!r} instead of {ARCHIVE_HOST!r}.\n"
            f"Full URL: {raw_url}\n"
            f"JS body that triggered it:\n{js_body[:500]}"
        )


# ---------------------------------------------------------------------------
# Unit test: the transport guard raises ArchiveHostViolation for every non-archive host
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://evil.com/api/v1/users",
        "http://web.archive.org/web/20230101000000id_/https://example.com/",  # http, not https
        "https://web.archive.org.evil.com/",
        "https://127.0.0.1/",
        "https://archive.org/",
    ],
)
def test_transport_guard_raises_for_non_archive_hosts(url: str) -> None:
    """The _ArchiveOnly transport refuses requests to any host other than web.archive.org."""
    from necropolis.archive.client import _ArchiveOnly

    inner_requests: list[httpx.Request] = []

    async def _run() -> None:
        guard = _ArchiveOnly(httpx.MockTransport(lambda r: inner_requests.append(r) or httpx.Response(200)))
        with pytest.raises(ArchiveHostViolation):
            await guard.handle_async_request(httpx.Request("GET", url))

    asyncio.run(_run())
    # The guard must have blocked the request before it reached the inner transport.
    assert inner_requests == [], f"Request for {url!r} leaked past the host guard"


def test_transport_guard_allows_archive_host() -> None:
    """The _ArchiveOnly transport forwards requests to web.archive.org."""
    from necropolis.archive.client import _ArchiveOnly

    sent: list[httpx.Request] = []

    async def _run() -> None:
        guard = _ArchiveOnly(
            httpx.MockTransport(
                lambda r: sent.append(r) or httpx.Response(200, stream=httpx.ByteStream(b"ok"))
            )
        )
        response = await guard.handle_async_request(
            httpx.Request("GET", f"https://{ARCHIVE_HOST}/cdx/search/cdx?url=example.com")
        )
        assert response.status_code == 200

    asyncio.run(_run())
    assert len(sent) == 1
