"""Path canonicalisation (Req endpoint-normaliser:1.3, 1.4) and templating (2.1, 2.4, 3.5)."""

from __future__ import annotations

from dataclasses import dataclass

from necropolis.normaliser.segments import PLACEHOLDERS, classify_segment

_UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
# RFC 3986 pchar minus pct-encoded: unreserved, sub-delims, ":" and "@". Every other byte is percent-encoded.
_PATH_SAFE = _UNRESERVED | frozenset(b"!$&'()*+,;=:@")
_HEX_DIGITS = frozenset(b"0123456789ABCDEFabcdef")


@dataclass(frozen=True, slots=True)
class Template:
    segments: tuple[str, ...]  # canonical literals and placeholders, in order
    example_path: str | None  # the concrete canonical path, or None when the input already held placeholders

    @property
    def path(self) -> str:
        return "/" + "/".join(self.segments)


def canonical_segment(segment: str) -> str:
    """Req 1.4: decode unreserved characters only, and keep the case of everything else.

    The rest is made well-formed so that rendering and normalising again is stable: percent-encodings get
    uppercase hex digits (RFC 3986 section 6.2.2.1), a lone "%" becomes "%25", and bytes a path may not hold
    (space, quotes, braces, non-ASCII as UTF-8, ...) are percent-encoded.
    """
    data = segment.encode("utf-8")
    out: list[str] = []
    i = 0
    while i < len(data):
        byte = data[i]
        if byte == 0x25:  # "%"
            pair = data[i + 1 : i + 3]
            if len(pair) == 2 and pair[0] in _HEX_DIGITS and pair[1] in _HEX_DIGITS:
                value = int(pair, 16)
                out.append(chr(value) if value in _UNRESERVED else "%" + pair.decode("ascii").upper())
                i += 3
                continue
            out.append("%25")
        elif byte in _PATH_SAFE:
            out.append(chr(byte))
        else:
            out.append(f"%{byte:02X}")
        i += 1
    return "".join(out)


def template_path(raw_path: str) -> Template:
    """Split, canonicalise, resolve dot segments, then template each segment (Req 1.3, 1.4, 2.1).

    Decoding comes before dot-segment removal, so `%2E%2E` acts like `..`. A segment that is already a placeholder
    (rendered keys, JS paths where the exhumer put `{id}` for `${...}`) is kept as it is: it is a fixed point.
    """
    items: list[tuple[str, bool]] = []  # (canonical text, arrived as a placeholder)
    for raw in raw_path.split("/"):
        raw = raw.partition(";")[0]  # Req 3.5: drop path parameters such as ;jsessionid=...
        if not raw:
            continue  # merges repeated slashes and drops the trailing slash
        if raw in PLACEHOLDERS:
            items.append((raw, True))
            continue
        text = canonical_segment(raw)
        if text == ".":
            continue
        if text == "..":
            if items:
                items.pop()
            continue
        items.append((text, False))

    template: list[str] = []
    concrete: list[str] = []
    for text, is_placeholder in items:
        if is_placeholder:
            template.append(text)
            continue
        placeholder = classify_segment(text)
        template.append(text if placeholder is None else placeholder.value)
        concrete.append(text)

    has_placeholder_input = any(p in raw_path for p in PLACEHOLDERS)  # also `user-{id}`, which stays literal
    example = None if has_placeholder_input else "/" + "/".join(concrete)
    return Template(segments=tuple(template), example_path=example)
