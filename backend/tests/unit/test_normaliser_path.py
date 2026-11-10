"""Req endpoint-normaliser:1.3, 1.4, 3.5: path canonicalisation."""

from __future__ import annotations

import pytest

from necropolis.normaliser import Normalised, normalise
from necropolis.normaliser.path import canonical_segment


def path_of(raw_path: str) -> str:
    result = normalise("https://example.com" + raw_path)
    assert isinstance(result, Normalised), result
    return result.key.path_template


@pytest.mark.parametrize(
    ("raw_path", "path"),
    [
        ("", "/"),
        ("/", "/"),
        ("/a#frag", "/a"),  # 1.3 fragment removed
        ("/a#/b/c?x=1", "/a"),
        ("//a///b", "/a/b"),  # 1.3 repeated slashes merged
        ("/a/", "/a"),  # 1.3 trailing slash removed, except on the root
        ("/a/./b/../c", "/a/c"),  # 1.3 dot segments
        ("/../../a", "/a"),
        ("/a/b/%2E%2E/c", "/a/c"),  # decoded before dot removal: %2E%2E acts like ..
        ("/a/%2e/b", "/a/b"),
        ("/.well-known/x", "/.well-known/x"),  # not a dot segment
    ],
)
def test_canonical_path(raw_path: str, path: str) -> None:
    assert path_of(raw_path) == path


@pytest.mark.parametrize(
    ("segment", "canonical"),
    [
        ("%41%62%63%2D%5f%7E", "Abc-_~"),  # 1.4 unreserved characters decoded
        ("Users", "Users"),  # 1.4 case kept
        ("a%2Fb", "a%2Fb"),  # reserved characters stay encoded
        ("a%2fb", "a%2Fb"),  # with uppercase hex digits (RFC 3986 section 6.2.2.1)
        ("a b", "a%20b"),  # bytes a path may not hold are encoded
        ("café", "caf%C3%A9"),
        ("caf%c3%a9", "caf%C3%A9"),
        ("100%", "100%25"),  # a lone % made well-formed
        ("%zz", "%25zz"),
        ("{x}", "%7Bx%7D"),
        ("a:b@c!$&'()*+,=", "a:b@c!$&'()*+,="),  # sub-delims, ":" and "@" are fine in a path
    ],
)
def test_canonical_segment(segment: str, canonical: str) -> None:
    assert canonical_segment(segment) == canonical
    assert canonical_segment(canonical) == canonical


@pytest.mark.parametrize(
    ("raw_path", "path"),
    [
        ("/shop/cart.do;jsessionid=8A7F6E5D4C3B2A10", "/shop/cart.do"),  # 3.5 path parameters dropped
        ("/products;color=red;size=xl/list", "/products/list"),
        ("/a/..;/b", "/b"),
        ("/a%3Bb", "/a%3Bb"),  # an encoded semicolon is data, not a parameter
    ],
)
def test_path_parameters_are_dropped(raw_path: str, path: str) -> None:
    assert path_of(raw_path) == path
