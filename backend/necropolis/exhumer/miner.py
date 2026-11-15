"""Endpoints named in archived JavaScript (Req exhumer:4.3 to 4.5). Pure: the text is scanned, never run.

Hostile files stay cheap (safety.md rule 7):
- Every pattern is bounded: no nested quantifiers, every repeat capped, and the alternatives inside a repeat start
  with different characters. A literal must start with "/", "\\/" or "http(s):" right after its quote, and holds no
  unescaped quote of its own kind. So a failed attempt never runs past the next quote of that kind, failed attempts
  never overlap, and the scan is linear. A test runs each pattern over 2 MiB of adversarial input in under a second.
- At most `MAX_CANDIDATES` distinct literals are normalised per script: each call costs tens of microseconds, and a
  hostile file can hold hundreds of thousands of literals.
"""

from __future__ import annotations

import re

from necropolis.exhumer.models import Target
from necropolis.normaliser import Normalised, Rejected, normalise, registrable_domain

MAX_LITERAL = 300  # characters (an escape such as "\/" counts as one) between the quotes
CONTEXT_WINDOW = 40
MAX_CANDIDATES = 5000  # distinct literals normalised per script
MAX_FOUND_PER_SCRIPT = 5000

_START = r"(?=/|\\/|\\u002[fF]|https?:)"
_ESCAPE = r"\\(?:/|u002[fF])"  # "\/api\/v1" in JSON-escaped bundles; no other escape is a path
# String and template literals that start like a path or an absolute URL.
LITERAL = re.compile(
    rf'"({_START}(?:[^"\\\r\n]|{_ESCAPE}){{1,{MAX_LITERAL}}})"'
    rf"|'({_START}(?:[^'\\\r\n]|{_ESCAPE}){{1,{MAX_LITERAL}}})'"
    rf"|`({_START}(?:[^`\\]|{_ESCAPE}){{1,{MAX_LITERAL}}})`"
)
INTERPOLATION = re.compile(r"\$\{[^{}`]{0,200}\}")  # Req 4.4
ESCAPED_SLASH = re.compile(_ESCAPE)
CONTEXT = re.compile(r"fetch\(|axios\.|\.get\(|\.post\(|url\s*:")  # exhumer design, "JS miner"
PATTERNS = (LITERAL, INTERPOLATION, ESCAPED_SLASH, CONTEXT)


def mine_js(text: str, script_url: str, target: Target, *, base_host: str | None = None) -> list[Normalised]:
    """Endpoints in one script: unique, in order of first appearance.

    A literal is a candidate if it starts with `/` (resolved against `base_host`, default the script's own host) or
    is an absolute http(s) URL (Req 4.3). It is kept only on the target's site (Req 4.5), and only if it is an `api`
    endpoint, or has two or more segments with a request call just before it (`fetch(`, `axios.`, ...).
    """
    base = base_host if base_host is not None else _host_of(script_url)
    found: dict[Normalised, None] = {}
    seen: dict[str, Normalised | None] = {}  # candidate -> its on-site endpoint, or None
    for match in LITERAL.finditer(text):
        candidate = _candidate(match.group(1) or match.group(2) or match.group(3) or "")
        if candidate is None:
            continue
        if candidate in seen:
            endpoint = seen[candidate]
        elif len(seen) >= MAX_CANDIDATES:
            continue  # out of budget: only literals already normalised can still be kept
        else:
            endpoint = seen[candidate] = _on_site(candidate, base, target)
        if endpoint is None or endpoint in found:
            continue
        if endpoint.kind != "api" and not (
            _segment_count(endpoint.key.path_template) >= 2
            and CONTEXT.search(text, max(0, match.start() - CONTEXT_WINDOW), match.start())
        ):
            continue
        found[endpoint] = None
        if len(found) >= MAX_FOUND_PER_SCRIPT:
            break
    return list(found)


def _candidate(literal: str) -> str | None:
    text = ESCAPED_SLASH.sub("/", literal) if "\\" in literal else literal
    if "${" in text:
        text = INTERPOLATION.sub("{id}", text)
    if "${" in text or "\\" in text:
        return None
    if text.startswith(("/", "https://", "http://")):
        return text
    return None


def _on_site(candidate: str, base: str | None, target: Target) -> Normalised | None:
    if candidate.startswith("/") and not candidate.startswith("//") and base is None:
        return None  # a relative path with no host to resolve it against
    result = normalise(candidate, base_host=base)
    if isinstance(result, Rejected) or registrable_domain(result.key.host) != target.registrable_domain:
        return None
    return result


def _host_of(url: str) -> str | None:
    result = normalise(url)
    if isinstance(result, Rejected):
        return None
    key = result.key
    return key.host if key.port is None else f"{key.host}:{key.port}"


def _segment_count(path_template: str) -> int:
    return sum(1 for segment in path_template.split("/") if segment)
