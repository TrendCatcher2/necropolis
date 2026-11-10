"""Raw archived URL -> endpoint key (spec: .kiro/specs/endpoint-normaliser).

Pure (Req endpoint-normaliser:5.1): no I/O, no clock, no environment, no randomness. Never raises for bad input;
it returns `Rejected(reason)` instead (Req 1.6).
"""

from __future__ import annotations

from collections.abc import Sequence

from necropolis.normaliser.kind import kind_of
from necropolis.normaliser.models import EndpointKey, Kind, Normalised, Reason, Rejected, Scheme
from necropolis.normaliser.parse import MAX_LENGTH, parse_url
from necropolis.normaliser.path import template_path
from necropolis.normaliser.query import query_names
from necropolis.normaliser.segments import UNVERSIONED, Placeholder, classify_segment, crypt_of, is_version

__all__ = [
    "MAX_LENGTH",
    "UNVERSIONED",
    "EndpointKey",
    "Kind",
    "Normalised",
    "Placeholder",
    "Reason",
    "Rejected",
    "Scheme",
    "classify_segment",
    "crypt_of",
    "is_version",
    "normalise",
    "render",
]


def normalise(raw: str, *, base_host: str | None = None, mimetype: str | None = None) -> Normalised | Rejected:
    """Normalise one CDX `original` or JS-mined path.

    `base_host` is the host a bare path was mined from (Req 1.5), optionally with `:port`. `mimetype` is the
    capture's MIME type, used only for `kind` (Req 4.4).
    """
    parsed = parse_url(raw, base_host=base_host)
    if isinstance(parsed, str):
        return Rejected(reason=parsed)
    template = template_path(parsed.path)
    crypt = crypt_of(template.segments)
    return Normalised(
        key=EndpointKey(host=parsed.host, port=parsed.port, path_template=template.path, crypt=crypt),
        scheme=parsed.scheme,
        kind=kind_of(template.segments, has_version=crypt != UNVERSIONED, mimetype=mimetype),
        param_names=query_names(parsed.query),
        example_path=template.example_path,
    )


def render(key: EndpointKey, *, scheme: Scheme = "https", param_names: Sequence[str] = ()) -> str:
    """Req 5.3: the key as a URL, e.g. `https://host/api/v1/users/{id}?a&b`. Normalising it gives the same key.

    Pass a capture's `scheme` and `param_names` to show them; values are never part of it.
    """
    port = "" if key.port is None else f":{key.port}"
    query = "?" + "&".join(param_names) if param_names else ""
    return f"{scheme}://{key.host}{port}{key.path_template}{query}"
