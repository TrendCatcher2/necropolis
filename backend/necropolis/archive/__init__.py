"""Passive access to the Internet Archive (spec: .kiro/specs/exhumer, Requirement 3; safety.md rules 1 and 6).

Everything here talks to `web.archive.org` only, through `ArchiveClient`. Never import netguard, ownership or
prober from here (structure.md).
"""

from __future__ import annotations

from necropolis.archive.cache import TTL, ArchiveCache, cache_key
from necropolis.archive.cdx import CdxFormatError, parse_page, url_sha256
from necropolis.archive.client import (
    ARCHIVE_BASE,
    ARCHIVE_HOST,
    BACKOFF_S,
    SNAPSHOT_MAX_BYTES,
    ArchiveClient,
    ArchiveError,
    ArchiveHostViolation,
    ArchiveUnavailable,
    SnapshotUnavailable,
    cdx_target,
)
from necropolis.archive.decode import BoundedDecoder, DecodeError
from necropolis.archive.models import CaptureRow, CdxPage, CdxQuery, CdxStats, MatchType, Snapshot
from necropolis.archive.timestamps import format_timestamp, parse_timestamp

__all__ = [
    "ARCHIVE_BASE",
    "ARCHIVE_HOST",
    "BACKOFF_S",
    "SNAPSHOT_MAX_BYTES",
    "TTL",
    "ArchiveCache",
    "ArchiveClient",
    "ArchiveError",
    "ArchiveHostViolation",
    "ArchiveUnavailable",
    "BoundedDecoder",
    "CaptureRow",
    "CdxFormatError",
    "CdxPage",
    "CdxQuery",
    "CdxStats",
    "DecodeError",
    "MatchType",
    "Snapshot",
    "SnapshotUnavailable",
    "cache_key",
    "cdx_target",
    "format_timestamp",
    "parse_page",
    "parse_timestamp",
    "url_sha256",
]
