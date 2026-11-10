"""Normaliser output models (design.md "Data Models").

The key is the endpoint's identity only. Captures of one endpoint differ in scheme (old http, new https), query
string and MIME type, so those ride beside the key on `Normalised` and are aggregated by the exhumer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Scheme = Literal["http", "https"]
Kind = Literal["api", "script", "static", "page"]
Reason = Literal["unparseable", "scheme", "ip_literal", "localhost", "no_public_suffix", "too_long"]


class EndpointKey(BaseModel, frozen=True, extra="forbid"):
    """Identity of one endpoint. Req endpoint-normaliser:2.3: URLs that differ only in templated values share it."""

    host: str  # IDNA (punycode), lowercase, no trailing dot
    port: int | None  # None for 80 and 443: the key has no scheme, so both count as default
    path_template: str  # "/api/v1/users/{id}"
    crypt: str  # first version segment, lowercased ("v1", "v2.1"), or "unversioned"


class Normalised(BaseModel, frozen=True, extra="forbid"):
    """One normalised capture: the key plus what this capture said about it."""

    key: EndpointKey
    scheme: Scheme  # as captured; scheme-relative and bare paths count as https
    kind: Kind
    param_names: tuple[str, ...]  # Req 3.1: names only, sorted and unique; values never kept
    example_path: str | None  # Req 2.4: concrete path without query; None when the input held placeholders


class Rejected(BaseModel, frozen=True, extra="forbid"):
    """Req endpoint-normaliser:1.6: a raw value that is not an endpoint, and why."""

    reason: Reason
