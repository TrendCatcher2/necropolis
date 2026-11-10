# Design Document: endpoint-normaliser

## Overview

`necropolis.normaliser` is a pure library. It takes a raw URL plus context and returns either an `EndpointKey` or a
`Rejected(reason)`. It is used by the exhumer (on CDX rows and JS-mined paths), by `wayback-mcp`, and by the prober
(to group re-probe results). It does no I/O (safety: passive, no network).

## Architecture

```
raw str ──► parse ──► canonicalise ──► split path ──► classify segments ──► template ──► EndpointKey
                │                                                                       ▲
                └── Rejected(reason) ◄── host/scheme checks (public suffix, IP, localhost)
                                         query ──► names only (values dropped here) ────┘
```

Order matters for idempotence. Percent-decoding of unreserved characters happens **before** dot-segment removal, so
that `%2E%2E` is treated like `..`. Placeholders (`{id}` and the others) are recognised as fixed points before
segment classification, so rendering and then normalising again is stable.

## Components and Interfaces

```python
# necropolis/normaliser/__init__.py
def normalise(raw: str, *, base_host: str | None = None, mimetype: str | None = None) -> EndpointKey | Rejected: ...
def render(key: EndpointKey) -> str            # "https://host/path/{id}?a&b"
def classify_segment(seg: str) -> Placeholder | None
def crypt_of(segments: list[str]) -> str
```

- `parse.py`: scheme, host and port handling, IDNA, public-suffix check (tldextract, offline), and rejection reasons.
- `segments.py`: ordered segment classifiers (Requirement 2.1) and the placeholder set.
- `query.py`: parameter-name extraction and validation (Requirement 3).
- `kind.py`: static/script/api/page classification and the extension lists.

## Data Models

```python
class Placeholder(StrEnum): UUID="{uuid}"; EMAIL="{email}"; DATE="{date}"; ID="{id}"; HASH="{hash}"; TOKEN="{token}"

class EndpointKey(BaseModel, frozen=True):
    scheme: Literal["http", "https"]
    host: str                     # IDNA, lowercase, no trailing dot
    port: int | None              # None = default port
    path_template: str            # "/api/v1/users/{id}"
    crypt: str                    # "v1" | "v2.1" | "unversioned"
    kind: Literal["api", "script", "static", "page"]
    param_names: tuple[str, ...]  # sorted, unique

class Normalised(BaseModel, frozen=True):
    key: EndpointKey
    example_path: str             # concrete path, no query or fragment

class Rejected(BaseModel, frozen=True):
    reason: Literal["unparseable", "scheme", "ip_literal", "localhost", "no_public_suffix", "too_long"]
```

`normalise` returns `Normalised | Rejected`. The exhumer keeps the latest `example_path` per key (Requirement 2.4)
by comparing capture timestamps. Comparing timestamps is the exhumer's job, because the normaliser has no notion of
time.

### Token heuristic (Requirement 2.1, item 6)

A segment counts as `{token}` when **all** of these hold:
- it is at least 20 characters long and uses only the URL-safe alphabet;
- it contains at least one digit and at least one letter;
- it has no run of 4 or more lowercase letters that forms a word in a small built-in word list, so that
  `user-preferences-settings` stays literal;
- it is not a version segment.

Keep the heuristic conservative. A missed token only costs an extra tombstone. A false positive merges two real
endpoints, which hides a zombie.

## Correctness Properties

### Property 1: Normalisation is idempotent
*For any* raw URL `u` that normalises to `n`, `normalise(render(n.key))` returns a result whose key equals `n.key`.
**Validates: Requirements 5.3, 1.3**

### Property 2: ID values collapse to one template
*For any* path template made of literal segments and placeholders, and *any* two fillings of its placeholders with
values of the matching class, the two filled URLs normalise to equal keys.
**Validates: Requirements 2.3, 2.1**

### Property 3: Literal segments survive
*For any* path whose segments match no placeholder class, the `path_template` equals the canonicalised path, with
case preserved.
**Validates: Requirements 1.4, 2.1**

### Property 4: No query value ever appears in output
*For any* URL with query parameters whose values are random strings of length 8 or more, none of those value strings
appears in the serialised `Normalised` output, unless the same string also appears in the path or host.
**Validates: Requirements 3.1, 3.2**

### Property 5: Version segments are never templated
*For any* path containing a `v<n>` or `v<n>.<m>` segment, that segment appears literally in `path_template`, and
`crypt` equals the first one.
**Validates: Requirements 2.2, 4.1**

### Property 6: Rejection is total and never throws
*For any* string, including random bytes decoded as text, `normalise` returns either a key or a `Rejected` and never
raises.
**Validates: Requirement 1.6**

### Property 7: Purity
*For any* input, two calls return equal output. The test also patches `time`, `random` and `socket` to raise, to show
they are never touched.
**Validates: Requirements 5.1, 5.2**

## Error Handling

- Never raise for bad input. Return `Rejected(reason)`, and let the exhumer count rejections by reason for the
  "skipped captures" line in the UI.
- Inputs longer than 4,096 characters are rejected as `too_long` before parsing, which bounds the cost of the regexes.

## Testing Strategy

- Unit tests: one example table per acceptance criterion, in `tests/unit/test_normaliser_*.py`.
- Property tests: `tests/property/test_normaliser_props.py`, Properties 1 to 7. The strategies generate hosts under
  `example.com` and `*.test` plus real-looking ID values of each class.
- Regression corpus: `tests/fixtures/normaliser_corpus.jsonl`, raw-to-expected pairs from our demo domain's recorded
  CDX data. It grows whenever a bug is found.
