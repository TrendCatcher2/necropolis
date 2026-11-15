"""BoundedDecoder (Req exhumer:4.2): every encoding the archive replays, with the cap on the decoded bytes."""

from __future__ import annotations

import gzip
import tracemalloc
import zlib
from collections.abc import Callable

import brotli
import pytest

from necropolis.archive import BoundedDecoder, DecodeError

BODY = b"fetch('/api/v1/users/1').then((r) => r.json());\n" * 1500  # about 73 KB
MIB = 1024 * 1024


def raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def identity(data: bytes) -> bytes:
    return data


ENCODINGS: list[tuple[str | None, Callable[[bytes], bytes]]] = [
    (None, identity),
    ("identity", identity),
    ("gzip", gzip.compress),
    ("x-gzip", gzip.compress),
    ("GZip", gzip.compress),
    ("deflate", zlib.compress),
    ("deflate", raw_deflate),  # "deflate" without the zlib wrapper, which browsers also accept
    ("br", brotli.compress),
    (" br ", brotli.compress),
]


def decode(raw: bytes, coding: str | None, cap: int, *, chunk: int = 997, sniff: bool = False) -> tuple[bytes, bool]:
    decoder = BoundedDecoder(coding, cap, sniff_gzip=sniff)
    for start in range(0, len(raw), chunk):
        if not decoder.feed(raw[start : start + chunk]):
            break
    return decoder.finish(), decoder.truncated


@pytest.mark.parametrize(("coding", "encode"), ENCODINGS)
def test_decodes_each_replayed_encoding(coding: str | None, encode: Callable[[bytes], bytes]) -> None:
    assert decode(encode(BODY), coding, cap=MIB) == (BODY, False)


@pytest.mark.parametrize(("coding", "encode"), ENCODINGS)
def test_cap_applies_to_decoded_bytes(coding: str | None, encode: Callable[[bytes], bytes]) -> None:
    assert decode(encode(BODY), coding, cap=1000) == (BODY[:1000], True)


@pytest.mark.parametrize(("coding", "encode"), ENCODINGS)
def test_one_big_chunk_is_capped_too(coding: str | None, encode: Callable[[bytes], bytes]) -> None:
    raw = encode(BODY)
    assert decode(raw, coding, cap=1000, chunk=len(raw)) == (BODY[:1000], True)


def test_a_file_exactly_at_the_cap_is_not_truncated() -> None:
    assert decode(gzip.compress(BODY), "gzip", cap=len(BODY)) == (BODY, False)
    assert decode(BODY, None, cap=len(BODY)) == (BODY, False)


def test_feed_returns_false_once_full() -> None:
    decoder = BoundedDecoder(None, 10)
    assert decoder.feed(b"12345")
    assert not decoder.feed(b"678901")
    assert not decoder.feed(b"more")
    assert decoder.finish() == b"1234567890"
    assert decoder.truncated


def test_empty_chunks_and_empty_body() -> None:
    decoder = BoundedDecoder("gzip", 10)
    assert decoder.feed(b"")
    assert decoder.finish() == b""
    assert not decoder.truncated


@pytest.mark.parametrize(
    ("coding", "compress"),
    [("gzip", gzip.compress), ("deflate", zlib.compress), ("br", brotli.compress)],
)
def test_compression_bomb_never_expands_in_memory(coding: str, compress: Callable[[bytes], bytes]) -> None:
    bomb = compress(bytes(64 * MIB))  # 64 MiB of zeros: about 64 KB as gzip, under 100 bytes as brotli
    cap = 2 * MIB
    tracemalloc.start()
    try:
        body, truncated = decode(bomb, coding, cap, chunk=64 * 1024)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert len(body) == cap
    assert truncated
    assert peak < 8 * MIB  # the cap, the slice handed back, and the decompressor's own buffers; never 64 MiB


def test_gzip_with_several_members() -> None:
    raw = gzip.compress(b"first ") + gzip.compress(b"second")
    assert decode(raw, "gzip", cap=100) == (b"first second", False)


def test_bytes_after_the_end_of_a_gzip_stream_are_ignored() -> None:
    assert decode(gzip.compress(b"body") + b"trailing junk", "gzip", cap=100) == (b"body", False)


def test_sniffs_gzip_without_a_header_only_when_asked() -> None:
    raw = gzip.compress(b'[["timestamp"]]')
    assert decode(raw, None, cap=100, sniff=True) == (b'[["timestamp"]]', False)
    assert decode(raw, None, cap=100) == (raw, False)
    assert decode(b"[]", None, cap=100, sniff=True) == (b"[]", False)


@pytest.mark.parametrize("coding", ["compress", "zstd", "gzip, br", "br, gzip", "chunked"])
def test_unsupported_or_stacked_encodings_are_refused(coding: str) -> None:
    with pytest.raises(DecodeError):
        BoundedDecoder(coding, 100)


@pytest.mark.parametrize("coding", ["gzip", "deflate", "br"])
def test_corrupt_data_is_a_decode_error(coding: str) -> None:
    with pytest.raises(DecodeError):
        decode(b"this is not compressed data at all" * 4, coding, cap=1000)
