"""Dating endpoints, and zombie candidates (Req exhumer:5.1 to 5.3). Pure: no I/O and no clock.

`aggregate` needs no `now`: the fallback window is anchored on the newest script capture, not on today.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from necropolis.exhumer.models import Capture, EndpointRecord, FrontendRef, ScriptCapture, Source
from necropolis.normaliser import EndpointKey, Kind, Normalised

FALLBACK_WINDOW = timedelta(days=30)
_NOT_A_MIMETYPE = frozenset({"warc/revisit", "unk"})  # CDX placeholders, not types the site sent


def current_frontend(refs: Sequence[FrontendRef], scripts: Sequence[ScriptCapture]) -> frozenset[EndpointKey] | None:
    """The keys the current front end references (exhumer glossary, Req 4.7).

    Those are the scripts the newest root page loads. If none of those was mined, it is the scripts captured within
    30 days of the newest mined script. None if no script was mined at all: candidacy is then unknown.
    """
    if not scripts:
        return None
    current = {(script.key, script.seen_at) for script in scripts if script.current}
    if not current:
        newest = max(script.seen_at for script in scripts)
        current = {(s.key, s.seen_at) for s in scripts if newest - s.seen_at <= FALLBACK_WINDOW}
    return frozenset(ref.endpoint.key for ref in refs if (ref.script_key, ref.seen_at) in current)


def aggregate(
    captures: Sequence[Capture], refs: Sequence[FrontendRef], scripts: Sequence[ScriptCapture] = ()
) -> list[EndpointRecord]:
    """One record per endpoint key, sorted by key. The same records for any order of the inputs (Property 3)."""
    by_key_captures: defaultdict[EndpointKey, list[Capture]] = defaultdict(list)
    by_key_refs: defaultdict[EndpointKey, list[FrontendRef]] = defaultdict(list)
    for capture in captures:
        by_key_captures[capture.endpoint.key].append(capture)
    for ref in refs:
        by_key_refs[ref.endpoint.key].append(ref)
    current = current_frontend(refs, scripts)
    keys = sorted(by_key_captures.keys() | by_key_refs.keys(), key=key_order)
    return [_record(key, by_key_captures[key], by_key_refs[key], current) for key in keys]


def key_order(key: EndpointKey) -> tuple[str, int, str, str]:
    return key.host, key.port or 0, key.path_template, key.crypt


def _record(
    key: EndpointKey,
    captures: list[Capture],
    refs: list[FrontendRef],
    current: frozenset[EndpointKey] | None,
) -> EndpointRecord:
    # Each observation is (when, what this capture or reference said). Ties break on the content, so the result
    # never depends on input order.
    observations: list[tuple[datetime, Normalised]] = [(c.last_seen, c.endpoint) for c in captures]
    observations += [(r.seen_at, r.endpoint) for r in refs]
    times = [c.first_seen for c in captures] + [c.last_seen for c in captures] + [r.seen_at for r in refs]

    newest = max(observations, key=_observation_order)[1]
    concrete = [(when, e.example_path) for when, e in observations if e.example_path is not None]
    kind: Kind = "api" if any(e.kind == "api" for _, e in observations) else newest.kind
    if kind != "api":
        zombie: bool | None = False
    elif current is None:
        zombie = None
    else:
        zombie = key not in current
    sources: list[Source] = []
    if captures:
        sources.append("cdx")
    if refs:
        sources.append("js")
    return EndpointRecord(
        key=key,
        first_seen=min(times),
        last_seen=max(times),
        last_seen_in_frontend=max((r.seen_at for r in refs), default=None),
        capture_count=sum(c.count for c in captures),
        archived_statuses=tuple(sorted({c.status for c in captures if c.status is not None})),
        mimetypes=tuple(sorted({c.mimetype for c in captures if c.mimetype and c.mimetype not in _NOT_A_MIMETYPE})),
        sources=tuple(sources),
        example_path=max(concrete)[1] if concrete else None,  # Req 5.3: none for JS-only templates
        scheme=newest.scheme,
        kind=kind,
        param_names=tuple(sorted({name for _, e in observations for name in e.param_names})),
        zombie_candidate=zombie,
    )


def _observation_order(observation: tuple[datetime, Normalised]) -> tuple[datetime, str, str, str]:
    when, endpoint = observation
    return when, endpoint.scheme, endpoint.kind, endpoint.example_path or ""
