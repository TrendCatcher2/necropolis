"""Path segment classes: placeholders, version segments, crypts (Req endpoint-normaliser:2.1, 2.2, 4.1)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum

from necropolis.normaliser.kind import FILE_EXTENSIONS


class Placeholder(StrEnum):
    """What a variable segment becomes. Each value is a fixed point: classify_segment("{id}") is ID."""

    UUID = "{uuid}"
    EMAIL = "{email}"
    DATE = "{date}"
    ID = "{id}"
    HASH = "{hash}"
    TOKEN = "{token}"  # noqa: S105 - a placeholder name, not a credential


PLACEHOLDERS: frozenset[str] = frozenset(p.value for p in Placeholder)
UNVERSIONED = "unversioned"

# Common words of URL paths, 4+ letters. A token candidate whose letter runs contain one of them stays literal
# (design.md "Token heuristic"). Kept small: every word is also a chance to miss a real token.
_STOP_WORDS_TEXT = """
        about access account action active activity admin agent alert album alias analytics answer apply approve
        archive article asset assign attach audit auth author avatar backup badge balance banner basket batch
        billing block blog board book booking branch brand browse bucket build bulk bundle button cache calendar
        callback campaign cancel card cart catalog category change channel chart chat check checkout child chunk
        city claim class client close cloud code collection color comment commit company compare config confirm
        connect contact content context contract control cookie copy count country coupon course create credit
        cron currency custom customer dashboard data date debug default delete delivery demo deploy design detail
        device dialog diff digest direct discount display document domain download draft driver dump edit email
        embed employee enable endpoint entry error event example exchange export extension external feature feed
        field file filter find flag folder follow font form forum forward frame friend gallery game gateway
        general generate global grant graph group guest guide hash header health help hidden history home hook
        host image import inbox index info input insert install internal invite invoice issue item join journal
        json keyword label language last latest layout lead legacy level library license like limit link list
        live load local locale location lock login logo logout lookup mail main manage manifest manual market
        match media member menu merge message meta method metric migrate mobile model module monitor move name
        native network news next node note notify object offer office online open option order owner package page
        panel partner password payment people permission person phone photo picture ping place plan player plugin
        point policy poll popup portal post preview price print private process product profile program project
        promo proxy public publish purchase push query queue quote rate read recent record redirect refresh
        refund region register release remote remove render reply report request reset resource response rest
        result return review role room root route rule sale sample save schedule schema scope score script search
        secret section secure select send server service session setting setup share shop show sign signup site
        size skip slide slot snapshot social sort source space staff stage start state static stats status step
        stock storage store stream style subject submit subscribe summary support survey sync system table task
        team template tenant test text theme thread ticket time title today token tool topic total track trade
        transfer trash tree trial type update upgrade upload user valid value vendor verify version video view
        visit vote wallet watch webhook widget wiki work write year zone
"""
TOKEN_STOP_WORDS: tuple[str, ...] = tuple(sorted(_STOP_WORDS_TEXT.split()))

_VERSION = re.compile(r"[vV][0-9]+(?:\.[0-9]+)?")
_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")
# local part, "@" (raw or %40), up to 8 dot-ended labels, then a letters-only top-level label
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{1,64}(?:@|%40)(?:[A-Za-z0-9-]{1,63}\.){1,8}([A-Za-z]{2,24})")
_DATE = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])")
_INTEGER = re.compile(r"[0-9]{1,19}")
_HEX = re.compile(r"[0-9A-Fa-f]{16,}")
_URL_SAFE = re.compile(r"[A-Za-z0-9_-]{20,}")
_LETTER_RUN = re.compile(r"[a-z]{4,}")
_STOP_WORD = re.compile("|".join(TOKEN_STOP_WORDS))
_SEPARATOR = re.compile(r"[-_]")


def is_version(segment: str) -> bool:
    """Req 2.2: `v<digits>` or `v<digits>.<digits>`, case-insensitive."""
    return _VERSION.fullmatch(segment) is not None


def crypt_of(segments: Sequence[str]) -> str:
    """Req 4.1: the first version segment, lowercased so /API/V2 and /api/v2 share a crypt; else "unversioned"."""
    for segment in segments:
        if is_version(segment):
            return segment.lower()
    return UNVERSIONED


def classify_segment(segment: str) -> Placeholder | None:
    """Req 2.1: the placeholder for one canonical path segment, or None to keep it literal. First match wins."""
    if segment in PLACEHOLDERS:
        return Placeholder(segment)
    if is_version(segment):
        return None
    if _UUID.fullmatch(segment):
        return Placeholder.UUID
    if _is_email(segment):
        return Placeholder.EMAIL
    if _DATE.fullmatch(segment):
        return Placeholder.DATE
    if _INTEGER.fullmatch(segment):
        return Placeholder.ID
    if _HEX.fullmatch(segment):
        return Placeholder.HASH
    if _is_token(segment):
        return Placeholder.TOKEN
    return None


def _is_email(segment: str) -> bool:
    match = _EMAIL.fullmatch(segment)
    # "logo@2x.png" is a retina image, not an address: a file extension never counts as a top-level domain
    return match is not None and match.group(1).lower() not in FILE_EXTENSIONS


def _is_token(segment: str) -> bool:
    """Design "Token heuristic": conservative, because a false positive merges two real endpoints."""
    if not _URL_SAFE.fullmatch(segment):
        return False
    if not any(c.isdigit() for c in segment) or not any(c.isalpha() for c in segment):
        return False
    if _is_lowercase_slug(segment):
        return False
    return not any(_STOP_WORD.search(run) for run in _LETTER_RUN.findall(segment.lower()))


def _is_lowercase_slug(segment: str) -> bool:
    """`galaxy-s24-ultra-512gb`: no capitals, and a `-` or `_` separated part made only of letters."""
    if any(c.isupper() for c in segment):
        return False
    parts = _SEPARATOR.split(segment)
    return len(parts) > 1 and any(part.isalpha() for part in parts)
