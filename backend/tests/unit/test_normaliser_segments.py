"""Req endpoint-normaliser:2.1 and 2.2: ordered segment classes, the token heuristic and version segments."""

from __future__ import annotations

import pytest

from necropolis.normaliser import Placeholder, classify_segment, is_version
from necropolis.normaliser.segments import TOKEN_STOP_WORDS

P = Placeholder


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        ("123e4567-e89b-12d3-a456-426614174000", P.UUID),
        ("123E4567-E89B-12D3-A456-426614174000", P.UUID),
        ("alice@example.com", P.EMAIL),
        ("alice%40example.com", P.EMAIL),
        ("bob+tag@mail.example.org", P.EMAIL),
        ("2024-02-29", P.DATE),
        ("0", P.ID),
        ("42", P.ID),
        ("9999999999999999999", P.ID),  # 19 digits
        ("1234567890123456", P.ID),  # 16 digits: {id} comes before {hash}
        ("12345678901234567890", P.HASH),  # 20 digits
        ("d41d8cd98f00b204e9800998ecf8427e", P.HASH),
        ("DA39A3EE5E6B4B0D3255BFEF95601890AFD80709", P.HASH),
        ("abcdef0123456789", P.HASH),  # 16 hex
        ("Xk9Pq2LmZ7Rt4WvB8NcJ", P.TOKEN),  # 20 URL-safe characters
        ("V1StGXR8_Z5jdHi6B-myT", P.TOKEN),  # nanoid
    ],
)
def test_classes(segment: str, expected: Placeholder) -> None:
    assert classify_segment(segment) is expected


@pytest.mark.parametrize(
    "segment",
    [
        "users",
        "logo@2x.png",  # a retina image, not an address
        "react@18.2.0",
        "@babel",
        "2024-13-01",  # no month 13
        "2024-02-30x",
        "-1",
        "abcdef012345678",  # 15 hex characters
        "Xk9Pq2LmZ7Rt4WvB8Nc",  # 19 characters: too short for a token
        "user-preferences-settings",  # no digit
        "user-settings-2fa-backup-codes",  # stop words
        "getUserPreferences2024Export",  # camelCase words are found too
        "galaxy-s24-ultra-512gb",  # a lowercase slug
        "main.3f9a8b7c6d5e4f3a9b8c",  # "." is not in the token alphabet, so bundle names stay literal
        "v12345678901234567890",  # a version segment, never a token
        "Xk9Pq2LmZ7Rt4WvB8NcJ!",
    ],
)
def test_literals(segment: str) -> None:
    assert classify_segment(segment) is None


@pytest.mark.parametrize("placeholder", list(Placeholder))
def test_placeholders_are_fixed_points(placeholder: Placeholder) -> None:
    assert classify_segment(placeholder.value) is placeholder


@pytest.mark.parametrize(("segment", "version"), [("v1", True), ("V2", True), ("v2.1", True), ("v10", True),
                                                   ("v1.2.3", False), ("v", False), ("version1", False),
                                                   ("v1beta", False), ("1", False)])  # fmt: skip
def test_version_segments(segment: str, version: bool) -> None:
    """2.2: kept literal, case-insensitive."""
    assert is_version(segment) is version
    if version:
        assert classify_segment(segment) is None


def test_stop_words_are_plain_lowercase_words() -> None:
    assert list(TOKEN_STOP_WORDS) == sorted(set(TOKEN_STOP_WORDS))
    assert all(word.isascii() and word.isalpha() and word.islower() and len(word) >= 4 for word in TOKEN_STOP_WORDS)
