"""Correctness properties 1 to 7 of .kiro/specs/endpoint-normaliser/design.md."""

from __future__ import annotations

import builtins
import io
import os
import random
import socket
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st

from necropolis.normaliser import (
    MAX_LENGTH,
    Normalised,
    Placeholder,
    Rejected,
    is_version,
    normalise,
    render,
)
from tests.property.strategies import (
    any_text,
    any_value_segments,
    encode_query,
    fill,
    host_spellings,
    hosts,
    literal_segments,
    messy_urls,
    percent_spellings,
    query_names,
    query_values,
    reserved_test_hosts,
    templates,
    version_segments,
)


def _accepted(raw: str, **kwargs: str | None) -> Normalised:
    result = normalise(raw, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, Normalised), f"{raw!r} was rejected: {result!r}"
    return result


# Feature: endpoint-normaliser, Property 1: normalisation is idempotent
# Validates: Req endpoint-normaliser:5.3, 1.3
@given(messy_urls())
@example("HTTP://WWW.Example.COM.:80/API/V1/Users/42/?sessionid=abc#x")
@example("http://example.com:443/a")  # 443 on http: the key has no scheme, so 80 and 443 both count as default
@example("https://example.com/a%20b/%7Bid%7D/user-{id}/caf%c3%a9")
def test_normalise_idempotent(raw: str) -> None:
    first = _accepted(raw)
    assert _accepted(render(first.key)).key == first.key
    again = _accepted(render(first.key, scheme=first.scheme, param_names=first.param_names))
    assert (again.key, again.scheme, again.param_names, again.kind) == (
        first.key,
        first.scheme,
        first.param_names,
        first.kind,
    )


# Feature: endpoint-normaliser, Property 1: normalisation is idempotent (JS-mined bare paths)
# Validates: Req endpoint-normaliser:5.3, 1.5
@given(hosts(), messy_urls())
def test_bare_path_round_trip(base_host: str, url: str) -> None:
    path = "/" + url.split("://", 1)[1].partition("/")[2].lstrip("/")  # "//x" would be scheme-relative
    first = _accepted(path, base_host=base_host)
    assert first.key.host == base_host
    assert _accepted(render(first.key)).key == first.key


# Feature: endpoint-normaliser, Property 2: ID values collapse to one template
# Validates: Req endpoint-normaliser:2.3, 2.1
@given(hosts(), templates(), st.data())
def test_id_values_collapse(host: str, template: list[str], data: st.DataObject) -> None:
    one = _accepted(f"https://{host}/" + "/".join(fill(data.draw, template)))
    two = _accepted(f"https://{host}/" + "/".join(fill(data.draw, template)))
    assert one.key == two.key
    assert one.key.path_template == "/" + "/".join(template)


# Feature: endpoint-normaliser, Property 3: literal segments survive
# Validates: Req endpoint-normaliser:1.4, 2.1
@given(hosts(), st.lists(literal_segments, max_size=8), st.booleans(), st.data())
def test_literal_segments_survive(host: str, segments: list[str], trailing_slash: bool, data: st.DataObject) -> None:
    spelled = [data.draw(percent_spellings(segment)) for segment in segments]  # %41 is "A" (Req 1.4)
    path = "/" + "/".join(spelled) + ("/" if trailing_slash else "")
    result = _accepted(f"https://{host}{path}")
    assert result.key.path_template == "/" + "/".join(segments)
    assert result.example_path == "/" + "/".join(segments)


# Feature: endpoint-normaliser, Property 4: no query value ever appears in output
# Validates: Req endpoint-normaliser:3.1, 3.2
@given(
    hosts(),
    st.lists(st.one_of(literal_segments, version_segments, any_value_segments), max_size=4),
    st.lists(st.tuples(query_names, query_values), min_size=1, max_size=5),
)
@example("example.com", ["reset"], [("token", "SECRET-reset-0042"), ("email", "victim@example.org")])
def test_no_query_value_in_output(host: str, segments: list[str], params: list[tuple[str, str]]) -> None:
    url = f"https://{host}/" + "/".join(segments)
    result = _accepted(f"{url}?{encode_query(params)}")
    baseline = _accepted(url)  # anything also produced without the query did not come from a value
    fields = _strings(result)
    for _, value in params:
        if any(value in s for s in _strings(baseline)) or any(value in name for name in result.param_names):
            continue
        for spelling in {value, encode_query([("n", value)])[2:]}:
            assert not any(spelling in s for s in fields), f"query value {spelling!r} leaked"
    assert result.param_names == tuple(sorted({name for name, _ in params}))


def _strings(result: Normalised) -> list[str]:
    dumped = result.model_dump()
    key = dumped.pop("key")
    values = [*key.values(), *dumped.values()]
    flat = [v for v in values if isinstance(v, str)] + [n for v in values if isinstance(v, tuple) for n in v]
    return [*flat, result.model_dump_json()]


# Feature: endpoint-normaliser, Property 5: version segments are never templated
# Validates: Req endpoint-normaliser:2.2, 4.1
@given(
    hosts(),
    st.lists(st.one_of(literal_segments, any_value_segments, version_segments), max_size=4),
    version_segments,
    st.lists(st.one_of(literal_segments, any_value_segments, version_segments), max_size=4),
)
def test_version_segments_never_templated(host: str, before: list[str], version: str, after: list[str]) -> None:
    segments = [*before, version, *after]
    result = _accepted(f"https://{host}/" + "/".join(segments))
    template = result.key.path_template.split("/")[1:]
    assert len(template) == len(segments)
    for raw, templated in zip(segments, template, strict=True):
        if is_version(raw):
            assert templated == raw
    assert result.key.crypt == next(s for s in segments if is_version(s)).lower()


# Feature: endpoint-normaliser, Property 6: rejection is total and never throws
# Validates: Req endpoint-normaliser:1.6
@given(any_text, st.none() | st.text(max_size=40) | hosts(), st.none() | st.text(max_size=300))
@example("x" * (MAX_LENGTH + 1), None, None)
@example("\ud800", None, None)
@example("http://[::1", None, None)
@example("https://example.com:99999/", None, None)
@example("/api/v1/x", "\ud800", None)
@example("/api/v1/x", "[::1]", "application/json")
@example("https://exa\u3002mple\uff0ecom/", None, None)
@example("http://\u0661\u0662\u0667.0.0.1/", None, None)
def test_rejection_is_total(raw: str, base_host: str | None, mimetype: str | None) -> None:
    assert isinstance(normalise(raw, base_host=base_host, mimetype=mimetype), Normalised | Rejected)


# Feature: endpoint-normaliser, Property 6: rejection is total and never throws (hosts under no public suffix)
# Validates: Req endpoint-normaliser:1.6
@given(reserved_test_hosts().flatmap(host_spellings), st.lists(literal_segments, max_size=3))
def test_hosts_under_no_public_suffix_are_rejected(host: str, segments: list[str]) -> None:
    assert normalise(f"https://{host}/" + "/".join(segments)) == Rejected(reason="no_public_suffix")


class _ForbiddenError(Exception):
    pass


class _NoEnviron(Mapping[str, str]):
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def _refuse(self) -> _ForbiddenError:
        self._calls.append("os.environ")
        return _ForbiddenError("os.environ")

    def __getitem__(self, key: str) -> str:
        raise self._refuse()

    def __iter__(self) -> Iterator[str]:
        raise self._refuse()

    def __len__(self) -> int:
        raise self._refuse()


_IMPURE = [
    (time, ["time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "process_time",
            "localtime", "gmtime", "ctime", "strftime"]),
    (random, ["random", "randint", "randrange", "choice", "choices", "shuffle", "sample", "getrandbits", "uniform"]),
    (random.Random, ["random", "getrandbits"]),
    (os, ["urandom", "getenv", "open", "stat", "listdir", "scandir"]),
    (socket, ["socket", "create_connection", "getaddrinfo", "gethostbyname"]),
    (builtins, ["open", "print", "input"]),
    (io, ["open", "open_code"]),
]  # fmt: skip


@contextmanager
def _forbid_impurity() -> Iterator[list[str]]:
    """Make clock, randomness, environment, sockets and file access raise, and record any attempt."""
    calls: list[str] = []

    def refuse(name: str) -> mock.MagicMock:
        def side_effect(*args: object, **kwargs: object) -> None:
            calls.append(name)
            raise _ForbiddenError(name)

        return mock.MagicMock(side_effect=side_effect)

    with ExitStack() as stack:
        for owner, names in _IMPURE:
            for name in names:
                label = f"{getattr(owner, '__name__', owner)}.{name}"
                stack.enter_context(mock.patch.object(owner, name, refuse(label)))
        stack.enter_context(mock.patch.object(os, "environ", _NoEnviron(calls)))
        yield calls


# Feature: endpoint-normaliser, Property 7: purity
# Validates: Req endpoint-normaliser:5.1, 5.2
@given(any_text, st.none() | hosts(), st.none() | st.sampled_from(["application/json", "text/html", "warc/revisit"]))
@example("https://bücher.example.com/api/v2/users/42?x=1", None, "application/json")
@example("/api/v1/users/{id}", "xn--bcher-kva.example.com", None)
def test_purity(raw: str, base_host: str | None, mimetype: str | None) -> None:
    with _forbid_impurity() as calls:
        modules = set(sys.modules)
        first = normalise(raw, base_host=base_host, mimetype=mimetype)
        second = normalise(raw, base_host=base_host, mimetype=mimetype)
        imported = set(sys.modules) - modules  # a first-time import inside normalise() reads files
    assert calls == []
    assert imported == set()
    assert first == second


def test_placeholder_values_are_their_own_class() -> None:
    """The strategies' fixed points: a rendered placeholder normalises to itself."""
    for placeholder in Placeholder:
        assert _accepted(f"https://example.com/a/{placeholder}").key.path_template == f"/a/{placeholder}"
