"""Which archived scripts to mine (Req exhumer:4.1, 4.7), and the `<script src>` list of a root page."""

from __future__ import annotations

import html
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field

from necropolis.archive import CaptureRow
from necropolis.exhumer.models import Capture
from necropolis.normaliser import EndpointKey

SCRIPT_LIMIT = 50  # Req 4.1; safety.md rule 7
MAX_SCRIPT_TAGS = 500
# Bounded patterns over hostile HTML (safety.md rule 7): no nested quantifiers, every repeat capped. A tag's
# attributes stop at the next "<" too, so an unclosed "<script" costs only the distance to the next tag: with "[^>]",
# 2 MiB of "<script " took 7 s.
_SCRIPT_TAG = re.compile(r"<script\b([^<>]{0,2000})>", re.IGNORECASE)
_SRC = re.compile(
    r"""(?:^|[\s"'/])src\s*=\s*(?:"([^"]{1,2000})"|'([^']{1,2000})'|([^\s"'=<>`]{1,2000}))""", re.IGNORECASE
)


class ScriptCandidate(BaseModel):
    """One script capture that could be fetched."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: EndpointKey  # the script's own key
    timestamp: datetime  # the capture to ask for; the archive serves the closest one
    url: str  # redacted
    url_sha256: str  # of the URL as archived: names the snapshot in the cache
    base_host: str  # host[:port] that relative paths in it resolve against (Req 4.5)
    current: bool = False  # loaded by the newest root-page capture (Req 4.7): always picked first
    # The URL as archived, in memory only (safety.md rule 5). None when only the cache can serve it.
    fetch_url: str | None = Field(default=None, exclude=True, repr=False)


def candidates_from(rows: Iterable[tuple[CaptureRow, Capture]]) -> list[ScriptCandidate]:
    """Script captures from the CDX listing. A collapsed row offers its first capture and, with counters, its last."""
    found: list[ScriptCandidate] = []
    for row, capture in rows:
        if capture.endpoint.kind != "script" or row.status not in (200, None):
            continue
        key = capture.endpoint.key
        base_host = key.host if key.port is None else f"{key.host}:{key.port}"
        for timestamp in sorted({row.timestamp, row.last_timestamp}):
            found.append(
                ScriptCandidate(
                    key=key,
                    timestamp=timestamp,
                    url=row.original,
                    url_sha256=row.original_sha256,
                    base_host=base_host,
                    fetch_url=row.address(),
                )
            )
    return found


def pick_scripts(candidates: Sequence[ScriptCandidate], limit: int = SCRIPT_LIMIT) -> list[ScriptCandidate]:
    """Req 4.1 and 4.7: the root-page scripts, then the newest and the oldest capture of each script key, then the
    rest spread evenly over time. At most `limit`, no capture twice."""
    unique: dict[tuple[str, datetime], ScriptCandidate] = {}
    for candidate in candidates:
        seen = unique.get(_identity(candidate))
        if seen is None or (candidate.current and not seen.current):
            unique[_identity(candidate)] = candidate
    pinned = [candidate for candidate in unique.values() if candidate.current]
    others = [candidate for candidate in unique.values() if not candidate.current]

    groups: defaultdict[EndpointKey, list[ScriptCandidate]] = defaultdict(list)
    for candidate in others:
        groups[candidate.key].append(candidate)
    newest = sorted(
        (max(group, key=_by_time) for group in groups.values()),
        key=lambda candidate: (candidate.timestamp, _key_order(candidate.key)),
        reverse=True,
    )
    oldest = [min(groups[candidate.key], key=_by_time) for candidate in newest]

    picked: dict[tuple[str, datetime], ScriptCandidate] = {}
    for candidate in [*pinned, *newest, *oldest]:
        picked.setdefault(_identity(candidate), candidate)
    if len(picked) >= limit:
        return list(picked.values())[:limit]
    rest = sorted((c for c in others if _identity(c) not in picked), key=_by_time)
    return [*picked.values(), *_spread(rest, limit - len(picked))]


def script_srcs(page: str, page_url: str) -> list[str]:
    """Req 4.7: the `src` of each `<script>` tag, resolved against the page; absolute http(s) URLs, unique, in order.

    The page is parsed as text with bounded patterns and never rendered (safety.md rule 7).
    """
    found: dict[str, None] = {}
    for count, tag in enumerate(_SCRIPT_TAG.finditer(page)):
        if count >= MAX_SCRIPT_TAGS:
            break
        attribute = _SRC.search(tag.group(1))
        if attribute is None:
            continue
        src = html.unescape(next(group for group in attribute.groups() if group)).strip()
        try:
            absolute = urljoin(page_url, src)
        except ValueError:
            continue
        if absolute.startswith(("https://", "http://")):
            found.setdefault(absolute.partition("#")[0], None)
    return list(found)


def _identity(candidate: ScriptCandidate) -> tuple[str, datetime]:
    return candidate.url_sha256, candidate.timestamp


def _by_time(candidate: ScriptCandidate) -> tuple[datetime, str, str]:
    return candidate.timestamp, candidate.url, candidate.url_sha256


def _key_order(key: EndpointKey) -> tuple[str, int, str, str]:
    return key.host, key.port or 0, key.path_template, key.crypt


def _spread(items: Sequence[ScriptCandidate], count: int) -> list[ScriptCandidate]:
    """`count` items spread evenly over a time-sorted list."""
    total = len(items)
    if count >= total:
        return list(items)
    return [items[(2 * index + 1) * total // (2 * count)] for index in range(count)]
