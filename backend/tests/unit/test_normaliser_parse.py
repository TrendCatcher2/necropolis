"""Req endpoint-normaliser:1.1, 1.2, 1.5, 1.6: scheme, host, port, bare paths and rejections."""

from __future__ import annotations

import socket

import pytest
import tldextract

from necropolis.normaliser import MAX_LENGTH, Normalised, Rejected, normalise
from tests.conftest import NetworkBlockedError

DEMO = "lantern-lane.onrender.com"


def accepted(raw: str, **kwargs: str) -> Normalised:
    result = normalise(raw, **kwargs)
    assert isinstance(result, Normalised), result
    return result


@pytest.mark.parametrize(
    ("raw", "scheme", "host"),
    [
        ("HTTPS://EXAMPLE.COM/x", "https", "example.com"),  # 1.1 lowercase scheme and host
        ("http://Www.Example.Org/x", "http", "www.example.org"),
        ("https://example.com./x", "https", "example.com"),  # 1.1 trailing dot
        ("https://Bücher.example.com/x", "https", "xn--bcher-kva.example.com"),  # 1.1 IDNA
        ("https://faß.example.com/x", "https", "xn--fa-hia.example.com"),  # UTS #46 non-transitional, like browsers
        ("https://\uff25\uff38\uff21\uff2d\uff30\uff2c\uff25.com/x", "https", "example.com"),  # full-width letters
        ("https://example\u3002com/x", "https", "example.com"),  # ideographic full stop
        ("https://lantern-lane.onrender.com/", "https", DEMO),  # private PSL suffix: one site per Render app
        ("https://user:s3cr3t-pw@example.com/x", "https", "example.com"),  # user info dropped
        ("  https://example.com/x\n", "https", "example.com"),  # trimmed like browsers do
        ("https://exa\tmple.com/x", "https", "example.com"),  # tabs and newlines removed anywhere
        ("//cdn.example.com/x", "https", "cdn.example.com"),  # scheme-relative counts as https
    ],
)
def test_scheme_and_host(raw: str, scheme: str, host: str) -> None:
    result = accepted(raw)
    assert (result.scheme, result.key.host) == (scheme, host)


def test_user_info_never_reaches_the_output() -> None:
    assert "s3cr3t-pw" not in accepted("https://admin:s3cr3t-pw@example.com/x").model_dump_json()


@pytest.mark.parametrize(
    ("raw", "port"),
    [
        ("http://example.com:80/x", None),  # 1.2
        ("https://example.com:443/x", None),  # 1.2
        ("http://example.com:443/x", None),  # the key has no scheme, so 80 and 443 both count as default
        ("https://example.com:80/x", None),
        ("https://example.com:0443/x", None),
        ("https://example.com:/x", None),  # empty port means the default
        ("https://example.com:8443/x", 8443),
        ("http://example.com:8080/x", 8080),
    ],
)
def test_default_ports_are_removed(raw: str, port: int | None) -> None:
    assert accepted(raw).key.port == port


def test_bare_path_resolves_against_the_mined_host() -> None:
    """1.5: a JS-mined path takes the host of the script it came from."""
    result = accepted("/api/v1/users/7", base_host=DEMO)
    assert (result.key.host, result.key.path_template, result.scheme) == (DEMO, "/api/v1/users/{id}", "https")
    assert accepted("/x", base_host="Example.COM:8080").key.port == 8080
    assert accepted("https://example.org/x", base_host=DEMO).key.host == "example.org"  # absolute URLs keep theirs


@pytest.mark.parametrize(
    ("raw", "base_host", "reason"),
    [
        ("/api/v1/x", None, "unparseable"),  # a bare path needs the host it was mined from
        ("/api/v1/x", "a@example.com", "unparseable"),
        ("/api/v1/x", "localhost", "localhost"),
        ("/api/v1/x", "10.0.0.1", "ip_literal"),
        ("/api/v1/x", "foo.test", "no_public_suffix"),
    ],
)
def test_bare_path_with_a_bad_base_host(raw: str, base_host: str | None, reason: str) -> None:
    assert normalise(raw, base_host=base_host) == Rejected(reason=reason)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "unparseable"),
        ("not a url", "unparseable"),
        ("example.com/api", "unparseable"),  # no scheme and not a path
        ("\ud800", "unparseable"),  # lone surrogate
        ("http://[::1", "unparseable"),
        ("https://exa mple.com/", "unparseable"),
        ("https://exa%6Dple.com/", "unparseable"),
        ("https://evil.example\\@example.com/", "unparseable"),  # browsers and urllib disagree on this host
        ("https://example.com:99999/", "unparseable"),
        ("https://example.com:8o80/", "unparseable"),
        ("https:///x", "unparseable"),
        ("https://" + "a" * 64 + ".example.com/", "unparseable"),  # label over 63 characters
        ("ftp://example.com/x", "scheme"),
        ("javascript:alert(1)", "scheme"),
        ("mailto:someone@example.com", "scheme"),
        ("data:text/plain,hi", "scheme"),
        ("http://127.0.0.1/", "ip_literal"),
        ("http://[::1]/", "ip_literal"),
        ("http://[2001:db8::1]:8080/x", "ip_literal"),
        ("http://0x7f.1/", "ip_literal"),  # browsers read these as IPv4
        ("http://2130706433/", "ip_literal"),
        ("http://192.168.0.1.:8080/", "ip_literal"),
        ("http://localhost:8080/", "localhost"),
        ("http://api.localhost/", "localhost"),
        ("https://foo.test/", "no_public_suffix"),  # .test is reserved, not on the Public Suffix List
        ("https://intranet/", "no_public_suffix"),
        ("https://onrender.com/", "no_public_suffix"),  # a public suffix itself: no site under it
        ("https://co.uk/", "no_public_suffix"),
        ("https://example.com/" + "a" * MAX_LENGTH, "too_long"),
    ],
)
def test_rejections(raw: str, reason: str) -> None:
    """1.6: rejected with a reason code, never an exception."""
    assert normalise(raw) == Rejected(reason=reason)  # type: ignore[arg-type]


def test_tests_cannot_reach_the_network() -> None:
    """testing.md: the autouse fixture blocks connections and name resolution."""
    with pytest.raises(NetworkBlockedError):
        socket.create_connection(("example.com", 80))
    with pytest.raises(NetworkBlockedError):
        socket.getaddrinfo("example.com", 443)


def test_public_suffix_list_works_offline() -> None:
    """tech.md: the bundled snapshot loads with the network blocked, and includes private suffixes."""
    extract = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True)
    assert extract(DEMO).suffix == "onrender.com"
    assert extract("foo.test").suffix == ""
