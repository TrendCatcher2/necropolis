"""CDX JSON pages -> `CaptureRow`s (Req exhumer:2.1, 2.4; exhumer design, "CDX query").

Shape, per the CDX server README (read 10 Nov 2026): a header row of field names, then one row per capture; with
`showResumeKey=true` and more results left, an empty row and a one-element row holding the resume key. An empty
result is assumed to be `[]`.
`[VERIFY: the exact JSON shape on the live API, with and without counters; freeze it into a recorded fixture.]`

Query values are removed here, before anything else sees a row (safety.md rule 5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime

from necropolis.archive.models import CDX_FIELDS, CaptureRow, CdxPage
from necropolis.archive.timestamps import parse_timestamp
from necropolis.normaliser import redact_url

COUNTER_FIELDS = ("skipcount", "endtimestamp")
MAX_ORIGINAL = 8192  # longer `original` values are malformed rows; the normaliser stops at 4,096 anyway


class CdxFormatError(ValueError):
    """The CDX answer is not the JSON shape above."""


def parse_page(body: bytes) -> CdxPage:
    try:
        data = json.loads(body)
    except (ValueError, RecursionError) as exc:  # bad UTF-8 or JSON, or absurd nesting
        raise CdxFormatError("the CDX answer is not JSON") from exc
    if not isinstance(data, list):
        raise CdxFormatError("the CDX answer is not a JSON array")
    if not data:
        return CdxPage(rows=(), malformed=0, resume_key=None, counters=False)
    header = data[0]
    if not isinstance(header, list) or not all(isinstance(name, str) for name in header):
        raise CdxFormatError("the CDX answer has no header row")
    index = {name.lower(): position for position, name in enumerate(header)}
    missing = [name for name in CDX_FIELDS if name not in index]
    if missing:
        raise CdxFormatError(f"the CDX header lacks {missing}")
    counters = all(name in index for name in COUNTER_FIELDS)

    body_rows = data[1:]
    resume_key: str | None = None
    if (
        len(body_rows) >= 2
        and body_rows[-2] == []
        and isinstance(body_rows[-1], list)
        and len(body_rows[-1]) == 1
        and isinstance(body_rows[-1][0], str)
    ):
        resume_key = body_rows[-1][0] or None
        body_rows = body_rows[:-2]

    rows: list[CaptureRow] = []
    malformed = 0
    for raw in body_rows:
        row = _row(raw, index, counters=counters)
        if row is None:
            malformed += 1
        else:
            rows.append(row)
    return CdxPage(rows=tuple(rows), malformed=malformed, resume_key=resume_key, counters=counters)


def _row(raw: object, index: dict[str, int], *, counters: bool) -> CaptureRow | None:
    if not isinstance(raw, list) or len(raw) < len(index):
        return None

    def field(name: str) -> object:
        return raw[index[name]]

    timestamp = parse_timestamp(field("timestamp"))
    original = field("original")
    if timestamp is None or not isinstance(original, str) or not original or len(original) > MAX_ORIGINAL:
        return None
    mimetype = field("mimetype")
    captures, last = _apply_counters(timestamp, field) if counters else (1, timestamp)
    redacted = redact_url(original)
    stripped = _query(original) != _query(redacted)
    return CaptureRow(
        timestamp=timestamp,
        last_timestamp=last,
        captures=captures,
        original=redacted,
        original_sha256=url_sha256(original),
        query_stripped=stripped,
        mimetype=mimetype if isinstance(mimetype, str) and mimetype not in ("", "-") else None,
        status=_status(field("statuscode")),
        raw_original=original if stripped else None,
    )


def _apply_counters(timestamp: datetime, field: Callable[[str], object]) -> tuple[int, datetime]:
    """How many captures a collapsed row stands for, and the last of them.

    Assumption: `skipcount` and `endtimestamp` describe the captures collapsed into **this** row (its own URL).
    `[VERIFY: on the recorded fixture. If the last row of each page never carries counters while the others do,
    they describe the gap before the row instead, and must be moved to the previous row.]`
    """
    skipped = field("skipcount")
    end = parse_timestamp(field("endtimestamp"))
    count = 1
    if isinstance(skipped, str) and skipped.isascii() and skipped.isdigit() and len(skipped) <= 9:
        count += int(skipped)
    elif isinstance(skipped, int) and not isinstance(skipped, bool) and 0 <= skipped < 10**9:
        count += skipped
    return count, max(timestamp, end) if end is not None else timestamp


def _status(value: object) -> int | None:
    """`"200"` -> 200. Revisit records carry `"-"`, which means unknown."""
    if isinstance(value, str) and len(value) == 3 and value.isascii() and value.isdigit():
        status = int(value)
        return status if 100 <= status <= 599 else None
    return None


def _query(url: str) -> str:
    return url.partition("#")[0].partition("?")[2]


def url_sha256(url: str) -> str:
    """Names a URL in the cache without storing it: the snapshot key for an archived URL that held a query value."""
    return hashlib.sha256(url.encode("utf-8", "surrogatepass")).hexdigest()
