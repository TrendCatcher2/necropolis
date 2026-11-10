"""Scheme, host and port of a raw URL, and the reasons to reject it (Req endpoint-normaliser:1.1, 1.2, 1.5, 1.6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import idna
import tldextract

from necropolis.normaliser.models import Reason, Scheme

MAX_LENGTH = 4096  # design "Error handling": longer inputs are rejected before parsing

_C0_CONTROL_OR_SPACE = "".join(map(chr, range(0x21)))
_LABEL = re.compile(r"[a-z0-9_-]{1,63}")
_ENDS_IN_NUMBER = re.compile(r"[0-9]+|0[xX][0-9A-Fa-f]*")  # WHATWG: such a host is parsed as IPv4
_DEFAULT_PORTS = frozenset({80, 443})
_MAX_HOST = 253

# Bundled Public Suffix List snapshot only: no live fetch (suffix_list_urls=()), no disk cache, and private
# suffixes such as onrender.com included (tech.md). Built at import, see _load_tables().
_PSL = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True)


@dataclass(frozen=True, slots=True)
class ParsedURL:
    scheme: Scheme
    host: str  # canonical
    port: int | None  # None for 80 and 443
    path: str  # raw: path.py canonicalises it
    query: str  # raw: query.py keeps the names and drops the values


def parse_url(raw: str, *, base_host: str | None = None) -> ParsedURL | Reason:
    """Accept absolute http(s) URLs, scheme-relative URLs and bare paths (resolved against `base_host`)."""
    if len(raw) > MAX_LENGTH:
        return "too_long"
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:  # lone surrogates, as a JSON "\ud800" escape can produce
        return "unparseable"
    # Like browsers: trim C0 controls and spaces, remove tabs and newlines anywhere.
    text = raw.strip(_C0_CONTROL_OR_SPACE).replace("\t", "").replace("\n", "").replace("\r", "")
    if not text or "\\" in text:
        # Browsers read "\" as "/" and urllib does not, so the two can disagree on the host. Never guess.
        return "unparseable"
    try:
        parts = urlsplit(text)
    except ValueError:  # bad brackets, netloc characters that change under NFKC
        return "unparseable"

    scheme: Scheme
    if parts.scheme == "http":
        scheme, authority = "http", parts.netloc
    elif parts.scheme == "https":
        scheme, authority = "https", parts.netloc
    elif parts.scheme:
        return "scheme"
    elif text.startswith("//"):
        scheme, authority = "https", parts.netloc
    elif text.startswith("/"):
        if base_host is None or "@" in base_host:
            return "unparseable"
        scheme, authority = "https", base_host
    else:
        return "unparseable"

    host_port = _host_and_port(authority.rpartition("@")[2])  # user info is dropped, never stored
    if isinstance(host_port, str):
        return host_port
    host, port = host_port
    return ParsedURL(scheme=scheme, host=host, port=port, path=parts.path, query=parts.query)


def canonical_host(host: str) -> str | None:
    """Req 1.1: IDNA (UTS #46 non-transitional, as browsers do), lowercase, no trailing dot. None if invalid."""
    if host.isascii():
        labels = host.lower().split(".")
    else:
        try:
            mapped = idna.uts46_remap(host, std3_rules=False, transitional=False)
            labels = [part if part.isascii() else idna.alabel(part).decode("ascii") for part in mapped.split(".")]
        except ValueError:  # idna.IDNAError and UnicodeError are ValueErrors
            return None
    if len(labels) > 1 and not labels[-1]:
        labels.pop()
    if not all(_LABEL.fullmatch(label) for label in labels):
        return None
    result = ".".join(labels)
    return result if len(result) <= _MAX_HOST else None


def check_host(host: str) -> Reason | None:
    """Req 1.6: an IP literal, localhost, or not under a public suffix (or itself a suffix, like onrender.com)."""
    if _ENDS_IN_NUMBER.fullmatch(host.rpartition(".")[2]):
        return "ip_literal"
    if host == "localhost" or host.endswith(".localhost"):
        return "localhost"
    parts = _PSL(host)
    if not parts.suffix or not parts.domain:
        return "no_public_suffix"
    return None


def _host_and_port(host_port: str) -> tuple[str, int | None] | Reason:
    if host_port.startswith("["):  # brackets only ever hold an IP literal
        _, bracket, rest = host_port.partition("]")
        return "ip_literal" if bracket and (not rest or rest.startswith(":")) else "unparseable"
    host_text, colon, port_text = host_port.partition(":")
    port: int | None = None
    if colon and port_text:
        if not (port_text.isascii() and port_text.isdigit()):
            return "unparseable"
        digits = port_text.lstrip("0") or "0"
        if len(digits) > 5 or int(digits) > 65535:
            return "unparseable"
        port = None if int(digits) in _DEFAULT_PORTS else int(digits)
    host = canonical_host(host_text)
    if host is None:
        return "unparseable"
    reason = check_host(host)
    return (host, port) if reason is None else reason


def _load_tables() -> None:
    """Load the PSL snapshot and the IDNA and punycode tables now, at import.

    Each is loaded on first use, and loading reads files. Doing it here keeps normalise() itself free of I/O
    (Req 5.1). The host has an IDN top-level label so that the suffix lookup decodes punycode too.
    """
    host = canonical_host("bücher.рф")
    if host is not None:
        check_host(host)


_load_tables()
