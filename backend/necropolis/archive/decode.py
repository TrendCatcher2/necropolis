"""Bounded decoding of the `Content-Encoding` the archive replays (Req exhumer:4.2).

Raw `id_` copies keep the encoding the site sent (gzip on the demo site, 10 Nov 2026). The cap applies to the
**decoded** bytes, and every decompress call is limited to the room that is left, so a compression bomb never
expands in memory first. httpx's own decoding is not used for this reason: it inflates a whole chunk at once.
"""

from __future__ import annotations

import zlib

import brotli

GZIP_MAGIC = bytes((0x1F, 0x8B))
_GZIP_WBITS = 16 + zlib.MAX_WBITS
_MAX_GZIP_MEMBERS = 64


class DecodeError(ValueError):
    """The body is not valid for its `Content-Encoding`, or the encoding is not supported."""


class BoundedDecoder:
    """Feed raw chunks with `feed()`, then call `finish()`. Keeps at most `max_bytes` decoded bytes.

    `truncated` is True when the decoded file was longer than the cap. `sniff_gzip` decodes a gzip body that came
    without a `Content-Encoding` header (the CDX server gzips its answers by default).
    """

    def __init__(self, content_encoding: str | None, max_bytes: int, *, sniff_gzip: bool = False) -> None:
        codings = [part.strip().lower() for part in (content_encoding or "").split(",")]
        codings = [part for part in codings if part and part != "identity"]
        if len(codings) > 1:
            raise DecodeError(f"stacked encodings are not supported: {content_encoding!r}")
        coding = codings[0] if codings else ""
        if coding not in ("", "gzip", "x-gzip", "deflate", "br"):
            raise DecodeError(f"unsupported Content-Encoding {coding!r}")
        self._coding = "gzip" if coding == "x-gzip" else coding
        self._sniff = sniff_gzip and not coding
        self._max = max_bytes
        self._out = bytearray()
        self._zlib: zlib._Decompress | None = None
        self._raw_deflate_tried = False
        self._brotli: brotli.Decompressor | None = None
        self._members = 1
        self._started = False
        self.truncated = False

    @property
    def full(self) -> bool:
        return len(self._out) > self._max

    def _room(self) -> int:
        return self._max + 1 - len(self._out)  # one byte more than the cap shows that the file was longer

    def feed(self, chunk: bytes) -> bool:
        """Decode one raw chunk. Returns False once the cap is reached, so the caller stops reading."""
        if self.full:
            return False
        if not chunk:
            return True
        if not self._started:
            self._started = True
            if self._sniff and chunk.startswith(GZIP_MAGIC):
                self._coding = "gzip"
        try:
            if self._coding == "":
                self._out += chunk[: self._room()]
            elif self._coding == "br":
                self._feed_brotli(chunk)
            else:
                self._feed_zlib(chunk)
        except (zlib.error, brotli.error) as exc:
            raise DecodeError(f"{self._coding} data is corrupt: {exc}") from exc
        return not self.full

    def finish(self) -> bytes:
        if self._zlib is not None and not self.full:
            try:
                self._out += self._zlib.flush()
            except zlib.error as exc:
                raise DecodeError(f"{self._coding} data is corrupt: {exc}") from exc
        self.truncated = self.full
        with memoryview(self._out) as view:  # one copy, not a slice and then a copy
            return bytes(view[: self._max])

    def _feed_zlib(self, data: bytes) -> None:
        if self._zlib is None:
            self._zlib = zlib.decompressobj(_GZIP_WBITS if self._coding == "gzip" else zlib.MAX_WBITS)
        try:
            self._inflate(data)
        except zlib.error:
            # "deflate" is sent both with and without the zlib wrapper; browsers accept both. Retry raw once.
            if self._coding != "deflate" or self._raw_deflate_tried or self._out:
                raise
            self._raw_deflate_tried = True
            self._zlib = zlib.decompressobj(-zlib.MAX_WBITS)
            self._inflate(data)

    def _inflate(self, data: bytes) -> None:
        if self._zlib is None:
            raise RuntimeError("inflate called before the gzip header was read")
        while data and not self.full:
            self._out += self._zlib.decompress(data, self._room())
            data = self._zlib.unconsumed_tail
            if self._zlib.eof:
                rest = self._zlib.unused_data
                if self._coding == "gzip" and rest.startswith(GZIP_MAGIC) and self._members < _MAX_GZIP_MEMBERS:
                    self._members += 1  # a gzip file may hold several members, one after the other
                    self._zlib = zlib.decompressobj(_GZIP_WBITS)
                    data = rest
                else:
                    break  # anything after the end of the stream is ignored

    def _feed_brotli(self, data: bytes) -> None:
        if self._brotli is None:
            self._brotli = brotli.Decompressor()
        self._out += self._brotli.process(data, output_buffer_limit=self._room())
        # brotli >= 1.2: with an output limit, the rest comes out of later calls with empty input.
        while not self.full and not self._brotli.can_accept_more_data():
            more = self._brotli.process(b"", output_buffer_limit=self._room())
            if not more:
                break
            self._out += more
