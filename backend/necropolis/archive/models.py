"""Models at the archive boundary (exhumer design, "Data Models" and "CDX query")."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MatchType = Literal["exact", "prefix", "host", "domain"]

CDX_FIELDS = ("timestamp", "original", "mimetype", "statuscode")
CDX_PAGE_ROWS = 5000


class CaptureRow(BaseModel):
    """One CDX row.

    Listings are collapsed by URL key, so a row stands for every capture of one URL: its own first capture, plus
    the captures the archive skipped, which it reports as `skipcount` and `endtimestamp` when asked (`counters`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime  # the row's own capture: the first one of this URL
    last_timestamp: datetime  # the last capture it stands for; equal to `timestamp` without counters
    captures: int = Field(ge=1)  # 1 + skipcount
    original: str  # user info, query values and fragment removed (safety.md rule 5)
    original_sha256: str  # of the URL exactly as archived: names its snapshot in the cache
    query_stripped: bool  # redaction changed the query, so `original` alone cannot address the snapshot
    mimetype: str | None
    status: int | None
    # The URL as archived, kept in memory only so a script with a query string can still be fetched. Never
    # serialised, printed or stored; None when the row came from the cache.
    raw_original: str | None = Field(default=None, exclude=True, repr=False)

    def address(self) -> str | None:
        """The URL to request this row's snapshot with, or None when only the redacted form is left."""
        return self.raw_original if self.query_stripped else self.original


class Snapshot(BaseModel):
    """One archived file, as the archive served it (`id_`, raw), decoded and capped."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime  # the capture that was served: the archive serves the one closest to the request
    url: str  # redacted URL of that capture
    content_type: str | None
    body: bytes = Field(repr=False)
    truncated: bool  # the decoded file was longer than the cap, and was cut there


@dataclass(frozen=True, slots=True)
class CdxPage:
    rows: tuple[CaptureRow, ...]
    malformed: int
    # Opaque, and built from the next row's URL key, so it can hold an archived query value: never logged or stored.
    resume_key: str | None = field(repr=False)
    counters: bool  # the header named both `skipcount` and `endtimestamp`


@dataclass
class CdxStats:
    """What a listing cost and found. Filled in while it is read; the exhumer reports it as progress."""

    pages: int = 0
    rows: int = 0
    malformed: int = 0
    capped: bool = False
    counters: bool | None = None  # every page carried counters (None until a page with a header arrives)
    from_cache: bool = False


@dataclass(frozen=True, slots=True)
class CdxQuery:
    """One CDX query (tech.md "External services"). Use `listing()` or `newest_root()`."""

    url: str
    match_type: MatchType = "exact"
    collapse_urlkey: bool = False
    counters: bool = False
    filters: tuple[str, ...] = ()
    limit: int = CDX_PAGE_ROWS
    from_year: int | None = None
    to_year: int | None = None

    @classmethod
    def listing(cls, host: str, *, match_type: MatchType, years: tuple[int, int] | None = None) -> CdxQuery:
        """Req exhumer:2.1: every URL on the host (or under the domain), one row per URL, with counters."""
        return cls(
            url=host,
            match_type=match_type,
            collapse_urlkey=True,
            counters=True,
            from_year=years[0] if years else None,
            to_year=years[1] if years else None,
        )

    @classmethod
    def newest_root(cls, host: str) -> CdxQuery:
        """Req exhumer:4.7: the newest successful HTML captures of the host's root page, newest last.

        A negative limit returns the last results (CDX server README). It is not -1, which implies `fastLatest`,
        whose interaction with filters is not documented.
        """
        return cls(url=f"{host}/", match_type="exact", filters=("statuscode:200", "mimetype:text/html"), limit=-3)

    def params(self) -> list[tuple[str, str]]:
        """The query's parameters. A resume key is appended by the client, verbatim (see `cdx_target`)."""
        params = [
            ("url", self.url),
            ("matchType", self.match_type),
            ("output", "json"),
            ("fl", ",".join(CDX_FIELDS)),
        ]
        if self.collapse_urlkey:
            params.append(("collapse", "urlkey"))
        if self.counters:
            params += [("showSkipCount", "true"), ("lastSkipTimestamp", "true")]
        params += [("filter", item) for item in self.filters]
        if self.from_year is not None:
            params.append(("from", str(self.from_year)))
        if self.to_year is not None:
            params.append(("to", str(self.to_year)))
        params.append(("limit", str(self.limit)))
        if self.limit > 0:
            params.append(("showResumeKey", "true"))
        return params
