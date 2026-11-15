"""Validate the domain a user typed (Req exhumer:1.1 to 1.3)."""

from __future__ import annotations

import re

from necropolis.exhumer.models import InvalidCode, InvalidTarget, Scope, Target
from necropolis.normaliser import Rejected, is_public_suffix, normalise, registrable_domain

MAX_INPUT = 2048
RESERVED_SUFFIXES = frozenset({"test", "local", "internal", "invalid", "localhost"})  # Req 1.2
_END_OF_HOST = re.compile(r"[/?#]")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")  # a hostname label, after IDNA: letters, digits, hyphens

_MESSAGES: dict[InvalidCode, str] = {
    "empty": "Enter a domain, like example.com.",
    "too_long": "That is too long to be a domain name.",
    "not_a_domain": "That does not look like a domain name. Enter one like example.com.",
    "has_credentials": "Enter just the domain, without a user name or password.",
    "has_port": "Enter the domain without a port number.",
    "ip_address": "That is an IP address. The archive is searched by domain name, like example.com.",
    "localhost": "localhost is a name for your own computer, not a public site.",
    "single_label": "Enter a full domain name, like example.com, not a single word.",
    "reserved_name": "That name ends in a reserved suffix that is never used on the public internet.",
    "public_suffix": "That is a public suffix that many sites share. Enter your own domain under it.",
    "unknown_suffix": "That does not end in a known public suffix, like .com or .org.",
}


def validate_target(raw: str, *, scope: Scope = "host") -> Target | InvalidTarget:
    """Req 1.1: accept a hostname under a public suffix, after trimming whitespace, a scheme and a path.

    Req 1.2: refuse IP addresses, localhost, single labels and reserved suffixes, with a plain message. `.test` is
    refused too: it is not on the Public Suffix List, so no capture under it could be normalised.
    """
    text = raw.strip()
    if not text:
        return _invalid("empty")
    if len(text) > MAX_INPUT:
        return _invalid("too_long")
    scheme, separator, rest = text.partition("://")
    if separator:
        if scheme.lower() not in ("http", "https"):
            return _invalid("not_a_domain")
        text = rest
    elif text.startswith("//"):
        text = text[2:]
    host = _END_OF_HOST.split(text, maxsplit=1)[0]
    if not host:
        return _invalid("not_a_domain")
    if "@" in host:
        return _invalid("has_credentials")
    if host.startswith("[") or host.count(":") > 1:
        return _invalid("ip_address")
    host, colon, port = host.partition(":")
    if colon and port:
        return _invalid("has_port")

    result = normalise(f"https://{host}/")
    if isinstance(result, Rejected):
        return _invalid(_code_for(result, host))
    if not all(_LABEL.fullmatch(label) for label in result.key.host.split(".")):
        return _invalid("not_a_domain")  # "-shop.example.com" or "shop_1.example.com": not a hostname (Req 1.1)
    site = registrable_domain(result.key.host)
    if site is None:  # normalise() already checked this
        return _invalid("unknown_suffix")
    return Target(host=result.key.host, registrable_domain=site, scope=scope)


def _code_for(rejected: Rejected, host: str) -> InvalidCode:
    if rejected.reason == "ip_literal":
        return "ip_address"
    if rejected.reason == "localhost":
        return "localhost"
    if rejected.reason == "too_long":
        return "too_long"
    if rejected.reason != "no_public_suffix":
        return "not_a_domain"
    lowered = host.lower().rstrip(".")
    if "." not in lowered:
        return "single_label"
    if lowered.rpartition(".")[2] in RESERVED_SUFFIXES:
        return "reserved_name"
    if is_public_suffix(lowered):
        return "public_suffix"
    return "unknown_suffix"


def _invalid(code: InvalidCode) -> InvalidTarget:
    return InvalidTarget(code=code, message=_MESSAGES[code])
