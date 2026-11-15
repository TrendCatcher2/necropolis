"""Recorded archive exchanges (exhumer task 1.3, testing.md "fixture mode").

`RecordingTransport` sits inside `ArchiveClient`'s host check and keeps each raw answer; `scripts/record_fixtures.py`
uses it, by hand, on our own demo domain only. `ReplayTransport` serves the recorded answers and never opens a
connection, so tests and the demo replay the archive with no load on it (safety.md rule 6).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

MANIFEST = "manifest.json"
KEPT_HEADERS = ("content-type", "content-encoding", "location", "memento-datetime", "retry-after")
MAX_RECORDED_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Exchange:
    method: str
    target: str  # raw path and query, exactly as sent
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes  # raw, still encoded as the archive sent it


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.exchanges: list[Exchange] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        chunks: list[bytes] = []
        size = 0
        try:
            async for chunk in response.stream:  # type: ignore[union-attr]
                size += len(chunk)
                if size > MAX_RECORDED_BYTES:
                    raise RuntimeError("an archive answer is too large to record")
                chunks.append(chunk)
        finally:
            await response.aclose()
        body = b"".join(chunks)
        headers = tuple(
            (name.lower(), value) for name, value in response.headers.items() if name.lower() in KEPT_HEADERS
        )
        self.exchanges.append(
            Exchange(request.method, request.url.raw_path.decode("ascii"), response.status_code, headers, body)
        )
        # stream=, not content=: content= would make httpx read and decode the body now, past the client's own
        # bounded decoder.
        return httpx.Response(
            response.status_code, headers=list(headers), stream=httpx.ByteStream(body), request=request
        )

    async def aclose(self) -> None:
        await self._inner.aclose()


def write_fixtures(folder: Path, exchanges: list[Exchange], meta: dict[str, object]) -> Path:
    """Write the manifest and one body file per exchange. Returns the manifest path."""
    bodies = folder / "bodies"
    bodies.mkdir(parents=True, exist_ok=True)
    entries = []
    for number, exchange in enumerate(exchanges, start=1):
        name = f"{number:04d}.bin"
        (bodies / name).write_bytes(exchange.body)
        entries.append(
            {
                "method": exchange.method,
                "target": exchange.target,
                "status": exchange.status,
                "headers": [list(pair) for pair in exchange.headers],
                "body": f"bodies/{name}",
            }
        )
    manifest = folder / MANIFEST
    manifest.write_text(json.dumps({**meta, "exchanges": entries}, indent=2) + "\n", encoding="utf-8")
    return manifest


class ReplayTransport(httpx.AsyncBaseTransport):
    """Serves recorded exchanges by method and raw target. Anything not recorded is a 404, listed in `misses`."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder
        manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
        self.meta = {key: value for key, value in manifest.items() if key != "exchanges"}
        self._index = {(entry["method"], entry["target"]): entry for entry in manifest["exchanges"]}
        self.misses: list[str] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        target = request.url.raw_path.decode("ascii")
        entry = self._index.get((request.method, target))
        if entry is None:
            self.misses.append(target)
            return httpx.Response(404, request=request)
        body = (self._folder / entry["body"]).read_bytes()
        headers = [(str(name), str(value)) for name, value in entry["headers"]]
        return httpx.Response(entry["status"], headers=headers, stream=httpx.ByteStream(body), request=request)
