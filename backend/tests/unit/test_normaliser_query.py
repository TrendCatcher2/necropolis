"""Req endpoint-normaliser:3.1 to 3.4: query parameter names only, never values."""

from __future__ import annotations

import pytest

from necropolis.normaliser import Normalised, normalise


def names(query: str) -> tuple[str, ...]:
    result = normalise(f"https://example.com/search?{query}")
    assert isinstance(result, Normalised), result
    return result.param_names


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("b=2&a=1&a=3", ("a", "b")),  # 3.1 de-duplicated and sorted
        ("ref=mail&utm_source=news", ("ref", "utm_source")),
        ("debug", ("debug",)),  # a name without a value
        ("x[]=1&x[]=2", ("x[]",)),
        ("user%5Bid%5D=7", ("user[id]",)),  # names are decoded before the checks
        ("&&=v&", ()),
        ("n" * 64 + "=1", ("n" * 64,)),  # ("a" * 64 would be a 64-character hex value)
        ("n" * 65 + "=1", ()),  # 3.3 longer than 64
        ("na+me=1&na%20me=2&naïve=3&a/b=4", ()),  # 3.3 characters outside [A-Za-z0-9_.-[]]
        ("1234", ()),  # 3.4 names that look like values
        ("d41d8cd98f00b204e9800998ecf8427e", ()),
        ("Xk9Pq2LmZ7Rt4WvB8NcJ&page=2", ("page",)),
        ("v2=1", ("v2",)),  # a version is not a value
    ],
)
def test_param_names(query: str, expected: tuple[str, ...]) -> None:
    assert names(query) == expected


def test_values_never_reach_the_output() -> None:
    """3.2, including the example value."""
    result = normalise("https://example.com/reset?token=SECRET-reset-0042&email=victim%40example.org#x")
    assert isinstance(result, Normalised)
    dumped = result.model_dump_json()
    assert "SECRET-reset-0042" not in dumped
    assert "victim" not in dumped
    assert result.example_path == "/reset"
