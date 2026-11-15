"""The exhume job: validate -> page CDX -> normalise -> pick scripts -> mine JS -> aggregate -> save.

Req exhumer:6.1 to 6.4. Passive: every request goes through `ArchiveClient` (safety.md rule 1). The job keeps what
it has gathered when the archive fails (`partial`) or the user cancels (`cancelled`).
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from necropolis.archive import (
    ArchiveClient,
    ArchiveError,
    ArchiveUnavailable,
    CaptureRow,
    CdxQuery,
    CdxStats,
    Snapshot,
    SnapshotUnavailable,
    url_sha256,
)
from necropolis.archive.cache import utc_now
from necropolis.exhumer.aggregate import aggregate
from necropolis.exhumer.captures import CDX_CAP, cdx_captures, to_capture
from necropolis.exhumer.miner import mine_js
from necropolis.exhumer.models import (
    Capture,
    ExhumeResult,
    FrontendRef,
    Phase,
    ScriptCapture,
    ScriptStats,
    Source,
    Target,
)
from necropolis.exhumer.scripts import SCRIPT_LIMIT, ScriptCandidate, candidates_from, pick_scripts, script_srcs
from necropolis.exhumer.store import save_run
from necropolis.jobs import EventType, JobBus, JobEvent
from necropolis.normaliser import EndpointKey, Normalised, Rejected, normalise, redact_url, registrable_domain

HEARTBEAT_S = 1.0  # Req 6.1: a progress event at least every 2 s
MAX_ROOT_HOSTS = 10  # domain scope: the root pages of at most this many hosts are fetched (Req 4.7)


@dataclass
class ExhumeJob:
    target: Target
    client: ArchiveClient
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    years: tuple[int, int] | None = None
    db: sqlite3.Connection | None = None
    bus: JobBus | None = None
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    now: Callable[[], datetime] = utc_now
    heartbeat_s: float = HEARTBEAT_S
    cap: int = CDX_CAP
    script_limit: int = SCRIPT_LIMIT


class _Run:
    """Everything gathered so far."""

    def __init__(self, job: ExhumeJob) -> None:
        self.job = job
        self.phase: Phase = "cdx"
        self.cdx = CdxStats()
        self.captures: list[Capture] = []
        self.script_rows: list[tuple[CaptureRow, Capture]] = []
        self.refs: dict[FrontendRef, None] = {}
        self.scripts: list[ScriptCapture] = []
        self.rejected: Counter[str] = Counter()
        self.keys: set[EndpointKey] = set()
        self.picked = self.mined = self.failed_scripts = 0
        self.failed_phase: Phase | None = None
        self.empty = False

    def emit(self, kind: EventType, data: dict[str, object]) -> None:
        if self.job.bus is not None:
            self.job.bus.publish(JobEvent(job_id=self.job.id, type=kind, data=data))

    def progress(self, **extra: object) -> None:
        self.emit(
            "progress",
            {
                "phase": self.phase,
                "pages": self.cdx.pages,
                "captures": self.cdx.rows,
                "endpoints": len(self.keys),
                "scripts_mined": self.mined,
                "scripts_failed": self.failed_scripts,
                "rejected": sum(self.rejected.values()) + self.cdx.malformed,
                **extra,
            },
        )

    def on_wait(self, delay: float, status: int | None) -> None:
        self.progress(waiting_s=delay, message=f"The archive asked us to wait. Retrying in {delay:.0f} s.")

    def found(self, endpoint: Normalised, seen: datetime, source: Source) -> None:
        if endpoint.key in self.keys:
            return
        self.keys.add(endpoint.key)
        self.emit(
            "endpoint",
            {
                "key": endpoint.key.model_dump(mode="json"),
                "kind": endpoint.kind,
                "seen": seen.isoformat(),
                "source": source,
            },
        )

    def add_row(self, row: CaptureRow) -> None:
        capture = to_capture(row, self.job.target)
        if isinstance(capture, str):
            self.rejected[capture] += 1
            return
        self.captures.append(capture)
        if capture.endpoint.kind == "script":
            self.script_rows.append((row, capture))
        self.found(capture.endpoint, capture.first_seen, "cdx")

    def add_script(self, pick: ScriptCandidate, snapshot: Snapshot, endpoints: list[Normalised]) -> None:
        self.scripts.append(ScriptCapture(key=pick.key, seen_at=snapshot.timestamp, current=pick.current))
        for endpoint in endpoints:
            self.refs.setdefault(FrontendRef(endpoint=endpoint, script_key=pick.key, seen_at=snapshot.timestamp), None)
            self.found(endpoint, snapshot.timestamp, "js")
        self.mined += 1

    def result(self, *, cancelled: bool) -> ExhumeResult:
        rejected = dict(self.rejected)
        if self.cdx.malformed:
            rejected["malformed_row"] = self.cdx.malformed
        if cancelled:
            status = "cancelled"
        elif self.failed_phase is not None:
            status = "partial"
        elif self.empty:
            status = "empty"
        else:
            status = "complete"
        return ExhumeResult(
            status=status,
            failed_phase=None if cancelled else self.failed_phase,
            endpoints=aggregate(self.captures, list(self.refs), self.scripts),
            rejected=rejected,
            capped=self.cdx.capped,
            dating="full" if self.cdx.counters else "first_capture_only",
            scripts=ScriptStats(picked=self.picked, mined=self.mined, failed=self.failed_scripts),
        )


async def run_exhume(job: ExhumeJob) -> ExhumeResult:
    run = _Run(job)
    started = job.now()
    job.client.add_wait_listener(run.on_wait)
    work = asyncio.create_task(_phases(run))
    stop = asyncio.create_task(job.cancel.wait())
    beat = asyncio.create_task(_heartbeat(run))
    cancelled = False
    try:
        await asyncio.wait({work, stop}, return_when=asyncio.FIRST_COMPLETED)
        if not work.done():
            cancelled = True  # Req 6.4
            work.cancel()
        try:
            await work
        except asyncio.CancelledError:
            if not cancelled:
                raise
    except BaseException:
        run.emit("error", {"message": "The exhume run stopped unexpectedly."})
        raise
    finally:
        for task in (work, stop, beat):
            task.cancel()
        await asyncio.gather(work, stop, beat, return_exceptions=True)
        job.client.remove_wait_listener(run.on_wait)

    result = run.result(cancelled=cancelled)
    if job.db is not None:
        try:
            save_run(
                job.db,
                run_id=job.id,
                target=job.target,
                years=job.years,
                result=result,
                refs=run.refs,
                started_at=started,
                finished_at=job.now(),
            )
        except sqlite3.Error:
            if result.status != "cancelled":
                result = result.model_copy(update={"status": "partial", "failed_phase": "save"})
    run.emit(
        "done",
        {
            "status": result.status,
            "failed_phase": result.failed_phase,
            "endpoints": len(result.endpoints),
            "capped": result.capped,
            "dating": result.dating,
        },
    )
    return result


async def _heartbeat(run: _Run) -> None:
    while True:
        run.progress()
        await asyncio.sleep(run.job.heartbeat_s)


async def _phases(run: _Run) -> None:
    job = run.job
    try:
        async for row in cdx_captures(job.client, job.target, job.years, stats=run.cdx, cap=job.cap):
            run.add_row(row)
    except ArchiveError:
        run.failed_phase = "cdx"  # Req 6.2
        return
    if run.cdx.rows == 0 and run.cdx.malformed == 0:
        run.empty = True  # Req 6.3
        return

    run.phase = "frontend"
    run.progress()
    try:
        pinned = await _root_page_scripts(run)
    except ArchiveUnavailable:
        run.failed_phase = "frontend"
        return

    run.phase = "scripts"
    run.progress()
    picks = pick_scripts([*pinned, *candidates_from(run.script_rows)], limit=job.script_limit)
    run.picked = len(picks)
    for pick in picks:
        try:
            snapshot = await _fetch_script(job.client, pick)
        except ArchiveUnavailable:
            run.failed_phase = "scripts"
            return
        except ArchiveError:  # SnapshotUnavailable included: skipped and counted
            run.failed_scripts += 1
            continue
        # Off the event loop, so progress keeps flowing while a large file is scanned (Req 6.1). A cancel does not
        # stop a running thread: the miner's own bounds (miner.MAX_CANDIDATES) keep it short.
        endpoints = await asyncio.to_thread(_mine, snapshot, pick, job.target)
        run.add_script(pick, snapshot, endpoints)


def _mine(snapshot: Snapshot, pick: ScriptCandidate, target: Target) -> list[Normalised]:
    return mine_js(snapshot.body.decode("utf-8", "replace"), pick.url, target, base_host=pick.base_host)


async def _root_page_scripts(run: _Run) -> list[ScriptCandidate]:
    """Req 4.7: for each in-scope host, the newest root-page capture and the same-site scripts it loads."""
    job = run.job
    pinned: list[ScriptCandidate] = []
    for host in _root_hosts(run):
        try:
            rows = [row async for row in job.client.cdx_rows(CdxQuery.newest_root(host), cap=3)]
        except ArchiveUnavailable:
            raise
        except ArchiveError:
            continue
        usable = [row for row in rows if row.address() is not None]
        if not usable:
            continue
        newest = max(usable, key=lambda row: (row.timestamp, row.original))
        address = newest.address()
        if address is None:  # usable rows always have an address
            raise RuntimeError("usable capture without an address")
        try:
            page = await job.client.snapshot(newest.timestamp, address, url_hash=newest.original_sha256)
        except ArchiveUnavailable:
            raise
        except ArchiveError:
            continue
        page_endpoint = normalise(page.url)
        if isinstance(page_endpoint, Rejected):
            continue
        page_key = page_endpoint.key
        base_host = page_key.host if page_key.port is None else f"{page_key.host}:{page_key.port}"
        for src in script_srcs(page.body.decode("utf-8", "replace"), page.url):
            script = normalise(src)
            if isinstance(script, Rejected) or registrable_domain(script.key.host) != job.target.registrable_domain:
                continue  # same-site scripts only
            pinned.append(
                ScriptCandidate(
                    key=script.key,
                    timestamp=page.timestamp,  # the archive serves the script capture closest to the page's
                    url=redact_url(src),
                    url_sha256=url_sha256(src),
                    base_host=base_host,  # a script's relative fetch() resolves against the page, not the script
                    current=True,
                    fetch_url=src,
                )
            )
    return pinned


def _root_hosts(run: _Run) -> list[str]:
    target = run.job.target
    if target.scope == "host":
        return [target.host]
    counts = Counter(capture.endpoint.key.host for _, capture in run.script_rows)
    ordered = sorted(counts, key=lambda host: (-counts[host], host))
    hosts = [target.host, *(host for host in ordered if host != target.host)]
    return hosts[:MAX_ROOT_HOSTS]


async def _fetch_script(client: ArchiveClient, pick: ScriptCandidate) -> Snapshot:
    if pick.fetch_url is not None:
        return await client.snapshot(pick.timestamp, pick.fetch_url, url_hash=pick.url_sha256)
    # Served from the cache, the row kept only its redacted URL (safety.md rule 5). The snapshot can still come from
    # the cache by its hash; asking the archive for the redacted URL could return a different file.
    cached = client.cached_snapshot(pick.timestamp, pick.url_sha256)
    if cached is None:
        raise SnapshotUnavailable("not_cached")
    return cached
