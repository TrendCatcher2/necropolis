"""Shared Hypothesis strategies (testing.md: reuse these, don't redefine them per test).

Hosts are subdomains of example.com and example.org, or the demo host. `*.test` hosts are not on the Public Suffix
List, so the normaliser rejects them; `reserved_test_hosts()` is for the rejection properties.
"""

from __future__ import annotations

from urllib.parse import quote

from hypothesis import strategies as st

from necropolis.normaliser import Placeholder, classify_segment

DEMO_HOST = "lantern-lane.onrender.com"

_LOWER_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
# Path characters that need no encoding (unreserved, sub-delims except ";", ":" and "@"): already canonical.
LITERAL_CHARS = _LETTERS + "0123456789-._~!$&'()*+,=:@"
# No vowels, so no stop word can form in a generated token.
_VOWEL_FREE_CHARS = "bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ0123456789-_"
# TLDs for generated emails: none of them is a file extension.
_EMAIL_TLDS = ("com", "org", "net", "io", "dev", "co", "uk", "example")

labels = st.text(_LOWER_ALNUM + "-", min_size=1, max_size=12).filter(lambda s: s[0] != "-" and s[-1] != "-")


@st.composite
def hosts(draw: st.DrawFn) -> str:
    """Canonical hosts the normaliser accepts."""
    base = draw(st.sampled_from(["example.com", "example.org", DEMO_HOST]))
    return ".".join([*draw(st.lists(labels, max_size=3)), base])


@st.composite
def reserved_test_hosts(draw: st.DrawFn) -> str:
    """`*.test` hosts: valid names, but under no public suffix."""
    return ".".join([*draw(st.lists(labels, min_size=1, max_size=3)), "test"])


@st.composite
def host_spellings(draw: st.DrawFn, host: str) -> str:
    """The same host with random letter case and maybe a trailing dot."""
    flips = draw(st.lists(st.booleans(), min_size=len(host), max_size=len(host)))
    spelled = "".join(c.upper() if flip else c for c, flip in zip(host, flips, strict=True))
    return spelled + draw(st.sampled_from(["", "."]))


literal_segments = st.text(LITERAL_CHARS, min_size=1, max_size=24).filter(
    lambda s: s not in (".", "..") and classify_segment(s) is None
)

version_segments = st.builds(
    lambda v, major, minor: f"{v}{major}" + ("" if minor is None else f".{minor}"),
    st.sampled_from("vV"),
    st.integers(0, 999),
    st.none() | st.integers(0, 99),
)


def _random_case(text: str) -> st.SearchStrategy[str]:
    return st.sampled_from([text, text.upper(), text.lower()])


VALUES: dict[Placeholder, st.SearchStrategy[str]] = {
    Placeholder.UUID: st.uuids().map(str).flatmap(_random_case),
    Placeholder.EMAIL: st.builds(
        lambda local, domain, tld: f"{local}@{domain}.{tld}",
        st.text(_LOWER_ALNUM + "._+-", min_size=1, max_size=16),
        st.lists(st.text(_LOWER_ALNUM, min_size=1, max_size=10), min_size=1, max_size=3).map(".".join),
        st.sampled_from(_EMAIL_TLDS),
    ),
    Placeholder.DATE: st.dates().map(lambda d: d.isoformat()),
    Placeholder.ID: st.integers(0, 10**19 - 1).map(str) | st.text("0123456789", min_size=1, max_size=19),
    Placeholder.HASH: st.text("0123456789abcdef", min_size=16, max_size=64).flatmap(_random_case),
    Placeholder.TOKEN: st.text(_VOWEL_FREE_CHARS, min_size=20, max_size=48),
}
# Every generated value must really be of its class: a 16-digit "hash" is an {id}, for example.
VALUES = {cls: values.filter(lambda v, cls=cls: classify_segment(v) is cls) for cls, values in VALUES.items()}

placeholders = st.sampled_from(list(Placeholder))

any_value_segments = st.one_of(*VALUES.values())


@st.composite
def templates(draw: st.DrawFn) -> list[str]:
    """A path template: literal segments, version segments and placeholders, in any order."""
    return draw(st.lists(st.one_of(literal_segments, version_segments, placeholders), max_size=6))


def fill(draw: st.DrawFn, template: list[str]) -> list[str]:
    """Replace each placeholder of a template with a value of its class."""
    return [draw(VALUES[seg]) if isinstance(seg, Placeholder) else seg for seg in template]


query_names = st.builds(
    lambda head, tail, brackets: head + tail + brackets,
    st.sampled_from(_LETTERS + "_"),
    st.text(_LETTERS + "0123456789_.-", max_size=15),
    st.sampled_from(["", "", "[]"]),
).filter(lambda n: classify_segment(n) is None)

query_values = st.text(min_size=8, max_size=40)


def encode_query(params: list[tuple[str, str]]) -> str:
    return "&".join(f"{quote(name, safe='')}={quote(value, safe='')}" for name, value in params)


@st.composite
def messy_urls(draw: st.DrawFn) -> str:
    """Valid absolute URLs spelled messily: scheme and host case, default ports, dot segments, repeated and
    trailing slashes, percent-encoded unreserved characters, a query and a fragment. All are accepted."""
    scheme = draw(st.sampled_from(["http", "https", "HTTP", "Https"]))
    host = draw(host_spellings(draw(hosts())))
    port = draw(st.sampled_from(["", "", ":80", ":443", ":8080", ":0443"]))
    segments: list[str] = []
    for seg in draw(st.lists(st.one_of(literal_segments, version_segments, any_value_segments), max_size=6)):
        if draw(st.booleans()) and seg[0] in _LETTERS:  # spell the first letter as a percent-encoding
            seg = f"%{ord(seg[0]):02x}{seg[1:]}"
        segments.append(seg)
        segments.extend(
            draw(st.sampled_from([[], [], [""], ["."], ["%2E"], ["x", ".."], ["x", "%2e%2E"], ["x", ".%2e"]]))
        )
    path = "/" + "/".join(segments) + draw(st.sampled_from(["", "/"]))
    query = draw(st.lists(st.tuples(query_names, query_values), max_size=3).map(encode_query))
    fragment = draw(st.sampled_from(["", "#top", "#/route?x=1"]))
    return f"{scheme}://{host}{port}{path}" + (f"?{query}" if query else "") + fragment


_UNRESERVED = frozenset(_LETTERS + "0123456789-._~")


@st.composite
def percent_spellings(draw: st.DrawFn, segment: str) -> str:
    """The same segment with some unreserved characters written as %XX, in either hex case."""
    out = []
    for char in segment:
        if char in _UNRESERVED and draw(st.booleans()):
            hex_digits = f"{ord(char):02X}"
            out.append("%" + draw(st.sampled_from([hex_digits, hex_digits.lower()])))
        else:
            out.append(char)
    return "".join(out)


any_text = st.one_of(
    st.text(),
    st.binary().map(lambda b: b.decode("utf-8", "replace")),
    st.from_regex(r"\A[a-zA-Z][a-zA-Z0-9+.-]{0,8}://[^/?#]{0,30}(/[^?#]{0,40})?(\?[^#]{0,30})?(#.{0,10})?\Z"),
    messy_urls(),
)
