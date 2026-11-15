"""Target validation (Req exhumer:1.1 to 1.3): the examples of the acceptance criteria."""

from __future__ import annotations

from typing import get_args

import pytest

from necropolis.exhumer import InvalidTarget, Target, validate_target
from necropolis.exhumer.models import InvalidCode
from necropolis.exhumer.target import _MESSAGES


@pytest.mark.parametrize(
    ("raw", "host", "site"),
    [
        ("shop.example.com", "shop.example.com", "example.com"),
        ("example.com", "example.com", "example.com"),
        ("  Shop.Example.COM  ", "shop.example.com", "example.com"),
        ("https://shop.example.com/account?tab=1#top", "shop.example.com", "example.com"),
        ("HTTP://shop.example.com", "shop.example.com", "example.com"),
        ("//shop.example.com/x", "shop.example.com", "example.com"),
        ("example.com.", "example.com", "example.com"),
        ("shop.example.co.uk", "shop.example.co.uk", "example.co.uk"),
        ("bücher.com", "xn--bcher-kva.com", "xn--bcher-kva.com"),
        ("lantern-lane.onrender.com", "lantern-lane.onrender.com", "lantern-lane.onrender.com"),  # a private suffix
    ],
)
def test_accepted_domains(raw: str, host: str, site: str) -> None:
    assert validate_target(raw) == Target(host=host, registrable_domain=site, scope="host")


def test_scope_defaults_to_host_and_can_be_domain() -> None:
    assert validate_target("example.com").scope == "host"  # type: ignore[union-attr]
    assert validate_target("example.com", scope="domain") == Target(
        host="example.com", registrable_domain="example.com", scope="domain"
    )


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("", "empty"),
        ("   ", "empty"),
        ("a" * 3000, "too_long"),
        ("ftp://example.com", "not_a_domain"),
        ("http://", "not_a_domain"),
        ("exa mple.com", "not_a_domain"),
        ("*.example.com", "not_a_domain"),
        ("shop..example.com", "not_a_domain"),
        ("-shop.example.com", "not_a_domain"),
        ("shop-.example.com", "not_a_domain"),
        ("shop_1.example.com", "not_a_domain"),
        ("https://user:pw@example.com", "has_credentials"),
        ("example.com:8080", "has_port"),
        ("127.0.0.1", "ip_address"),
        ("10.0.0.1", "ip_address"),
        ("127.1", "ip_address"),
        ("[::1]", "ip_address"),
        ("fe80::1", "ip_address"),
        ("localhost", "localhost"),
        ("LOCALHOST.", "localhost"),
        ("app.localhost", "localhost"),
        ("intranet", "single_label"),
        ("com", "single_label"),
        ("shop.test", "reserved_name"),  # not accepted, even in tests: no capture under .test could be normalised
        ("printer.local", "reserved_name"),
        ("db.internal", "reserved_name"),
        ("x.invalid", "reserved_name"),
        ("co.uk", "public_suffix"),
        ("github.io", "public_suffix"),
        ("example.notatld", "unknown_suffix"),
    ],
)
def test_rejected_inputs(raw: str, code: str) -> None:
    result = validate_target(raw)
    assert isinstance(result, InvalidTarget)
    assert result.code == code
    assert result.message == _MESSAGES[result.code]


def test_every_code_has_a_plain_message() -> None:
    for code in get_args(InvalidCode):
        message = _MESSAGES[code]
        assert message.endswith(".")
        assert "Error" not in message
        assert "{" not in message
