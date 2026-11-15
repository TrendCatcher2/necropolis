"""Exhumer models (exhumer design, "Data Models")."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from necropolis.normaliser import EndpointKey, Kind, Normalised, Scheme

Scope = Literal["host", "domain"]
Status = Literal["complete", "partial", "empty", "cancelled"]
Phase = Literal["cdx", "frontend", "scripts", "save"]
Dating = Literal["full", "first_capture_only"]
Source = Literal["cdx", "js"]
InvalidCode = Literal[
    "empty",
    "too_long",
    "not_a_domain",
    "has_credentials",
    "has_port",
    "ip_address",
    "localhost",
    "single_label",
    "reserved_name",
    "public_suffix",
    "unknown_suffix",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Target(_Frozen):
    """A validated domain (Req 1.1, 1.3)."""

    host: str  # canonical, as in EndpointKey.host
    registrable_domain: str  # the site: what JS-mined URLs must belong to (Req 4.5)
    scope: Scope = "host"


class InvalidTarget(_Frozen):
    """Req 1.2: why the input was refused, in plain words. The API answers 422 with it."""

    code: InvalidCode
    message: str


class Capture(_Frozen):
    """A CDX row after normalising (Req 2.4): every capture of one URL."""

    endpoint: Normalised
    first_seen: datetime
    last_seen: datetime
    count: int = Field(ge=1)
    status: int | None  # of the row's own (first) capture
    mimetype: str | None


class FrontendRef(_Frozen):
    """Req 4.6: an endpoint named in an archived script, dated by that script's capture."""

    endpoint: Normalised
    script_key: EndpointKey
    seen_at: datetime


class ScriptCapture(_Frozen):
    """A script capture that was fetched and mined."""

    key: EndpointKey
    seen_at: datetime  # the capture the archive served
    current: bool  # loaded by the newest root-page capture of its host (Req 4.7)


class EndpointRecord(_Frozen):
    """Req 5.1. Tuples are sorted and unique."""

    key: EndpointKey
    first_seen: datetime
    last_seen: datetime
    last_seen_in_frontend: datetime | None
    capture_count: int
    archived_statuses: tuple[int, ...]  # of the first capture of each URL: rows are collapsed by URL
    mimetypes: tuple[str, ...]  # likewise
    sources: tuple[Source, ...]
    example_path: str | None
    scheme: Scheme  # of the newest capture or reference, like example_path
    kind: Kind  # "api" if any capture or reference says so
    param_names: tuple[str, ...]  # union over captures and references, names only
    zombie_candidate: bool | None  # None: unknown, because no script was mined


class ScriptStats(_Frozen):
    picked: int = 0
    mined: int = 0
    failed: int = 0


class ExhumeResult(_Frozen):
    status: Status
    failed_phase: Phase | None
    endpoints: list[EndpointRecord]
    rejected: dict[str, int]
    capped: bool
    # "full" when the archive reported how many captures each collapsed row stands for, and the last of them.
    # Otherwise last_seen and capture_count only count each URL's first capture, and the UI says so.
    dating: Dating
    scripts: ScriptStats
