# Design Document: endpoint-normaliser

## Overview

`necropolis.normaliser` is a pure library. It takes a raw URL plus context and returns either a `Normalised` (an
`EndpointKey` plus what this capture said about it) or a `Rejected(reason)`. It is used by the exhumer (on CDX rows
and JS-mined paths), by `wayback-mcp`, and by the prober (to group re-probe results). It does no I/O (safety:
passive, no network).

## Architecture

```
raw str ──► parse ──► canonicalise ──► split path ──► classify segments ──► template ──► Normalised(key, ...)
                │                                                                          ▲
                └── Rejected(reason) ◄── host/scheme checks (public suffix, IP, localhost)
                                         query ──► names only (values dropped here) ───────┘
```

Order matters for idempotence. Path parameters (`;jsessionid=…`) are cut off when the path is split. Percent-decoding
of unreserved characters happens **before** dot-segment removal, so that `%2E%2E` is treated like `..`. Placeholders
(`{id}` and the others) are recognised as fixed points before segment classification, so rendering and then
normalising again is stable.

## Components and Interfaces

```python
# necropolis/normaliser/__init__.py
def normalise(raw: str, *, base_host: str | None = None, mimetype: str | None = None) -> Normalised | Rejected: ...
def render(key: EndpointKey, *, scheme: Literal["http", "https"] = "https", param_names: Sequence[str] = ()) -> str
    # "https://host/api/v1/users/{id}"; with a capture's scheme and names: "http://host/api/v1/users/{id}?a&b"
def classify_segment(seg: str) -> Placeholder | None
def crypt_of(segments: Sequence[str]) -> str
```

- `parse.py`: scheme, host and port handling, IDNA, public-suffix check (tldextract, offline), and rejection reasons.
  `base_host` may carry a `:port`; bare and scheme-relative paths count as `https`.
- `path.py`: path canonicalisation (Requirements 1.3, 1.4, 3.5) and templating.
- `segments.py`: ordered segment classifiers (Requirement 2.1), the placeholder set, version segments and crypts.
- `query.py`: parameter-name extraction and validation (Requirement 3).
- `kind.py`: static/script/api/page classification and the extension lists.
- `models.py`: the models below.

Dependencies (tech.md asks for a reason):
- `tldextract`: the offline public-suffix check (tech.md).
- `idna`: UTS #46 host mapping, as browsers do. The standard library codec is IDNA 2003, which turns `faß` into
  `fass` where browsers request `xn--fa-hia`. It is already a dependency of tldextract.
- `pydantic`: the models.

## Data Models

```python
class Placeholder(StrEnum): UUID="{uuid}"; EMAIL="{email}"; DATE="{date}"; ID="{id}"; HASH="{hash}"; TOKEN="{token}"

class EndpointKey(BaseModel, frozen=True):    # the identity of an endpoint
    host: str                     # IDNA, lowercase, no trailing dot
    port: int | None              # None for 80 and 443: the key has no scheme, so both count as default
    path_template: str            # "/api/v1/users/{id}"
    crypt: str                    # first version segment, lowercased: "v1" | "v2.1" | "unversioned"

class Normalised(BaseModel, frozen=True):     # one capture
    key: EndpointKey
    scheme: Literal["http", "https"]
    kind: Literal["api", "script", "static", "page"]
    param_names: tuple[str, ...]  # sorted, unique, names only
    example_path: str | None      # concrete path, no query or fragment; None when the input held placeholders

class Rejected(BaseModel, frozen=True):
    reason: Literal["unparseable", "scheme", "ip_literal", "localhost", "no_public_suffix", "too_long"]
```

### Why the key has no scheme or query

The key must be the same for every capture of one endpoint, or one endpoint becomes several tombstones:
- the CDX index collapses rows by URL key, which ignores the scheme, so one endpoint's row may be its old `http`
  capture while the JS that calls it is read as `https`;
- `/api/v1/users/123?ref=mail` and `/api/v1/users/9876` must be one tombstone (requirements, introduction);
- captures of one URL can have different MIME types (a JSON answer, an HTML error page), and `kind` depends on it.

So `scheme`, `kind`, `param_names` and `example_path` describe the capture and sit beside the key. The exhumer
aggregates them per key (exhumer design, `EndpointRecord`): the latest `example_path` and `scheme` by capture
timestamp (Requirement 2.4), the union of `param_names`, and `kind=api` if any capture says so. Comparing
timestamps is the exhumer's job, because the normaliser has no notion of time.

### Token heuristic (Requirement 2.1, item 6)

A segment counts as `{token}` when **all** of these hold:
- it is at least 20 characters long and uses only the URL-safe alphabet `[A-Za-z0-9_-]`. A `.` is not in it, so
  bundle names like `main.3f9a8b7c6d5e4f3a9b8c.js` stay literal and are still mined as scripts;
- it contains at least one digit and at least one letter;
- it is not a lowercase slug: no capital letters, and a `-` or `_` separated part made only of letters, as in
  `galaxy-s24-ultra-512gb`;
- no run of 4 or more letters, compared case-folded, contains a word from a small built-in list
  (`segments.TOKEN_STOP_WORDS`), so that `user-settings-2fa-backup-codes` and `getUserPreferences2024Export` stay
  literal;
- it is not a version segment.

Keep the heuristic conservative. A missed token only costs an extra tombstone. A false positive merges two real
endpoints, which hides a zombie. The cost, measured on 200,000 random base64url tokens (10 Nov 2026): 3.0% of
21-character tokens stay literal, most of them because they contain no digit, and 0.7% of 32-character ones.

Emails (item 2) skip addresses whose last label is a file extension, so the retina image `logo@2x.png` stays literal
and is still `static`.

## Correctness Properties

### Property 1: Normalisation is idempotent
*For any* raw URL `u` that normalises to `n`, `normalise(render(n.key))` returns a result whose key equals `n.key`,
and `normalise(render(n.key, scheme=n.scheme, param_names=n.param_names))` also returns `n`'s scheme, parameter names
and kind. This holds for JS-mined bare paths too.
**Validates: Requirements 5.3, 1.3**

### Property 2: ID values collapse to one template
*For any* path template made of literal segments and placeholders, and *any* two fillings of its placeholders with
values of the matching class, the two filled URLs normalise to equal keys.
**Validates: Requirements 2.3, 2.1**

### Property 3: Literal segments survive
*For any* path whose segments match no placeholder class, the `path_template` equals the canonicalised path, with
case preserved, also when some unreserved characters are written as `%XX`.
**Validates: Requirements 1.4, 2.1**

### Property 4: No query value ever appears in output
*For any* URL with query parameters whose values are random strings of length 8 or more, none of those value strings
appears in the `Normalised` output, raw or percent-encoded, unless the same string also appears in the output for the
URL without its query, or inside a kept parameter name.
**Validates: Requirements 3.1, 3.2**

### Property 5: Version segments are never templated
*For any* path containing a `v<n>` or `v<n>.<m>` segment, that segment appears literally in `path_template`, and
`crypt` equals the first one, lowercased.
**Validates: Requirements 2.2, 4.1**

### Property 6: Rejection is total and never throws
*For any* string, including random bytes decoded as text, `normalise` returns either a `Normalised` or a `Rejected`
and never raises. Hosts under `*.test` (not on the Public Suffix List) are always `no_public_suffix`.
**Validates: Requirement 1.6**

### Property 7: Purity
*For any* input, two calls return equal output. The test also patches the clock, `random`, `os.urandom`, the
environment, `socket` and file opening to raise, and checks that no module is imported during the calls.
**Validates: Requirements 5.1, 5.2**

## Error Handling

- Never raise for bad input. Return `Rejected(reason)`, and let the exhumer count rejections by reason for the
  "skipped captures" line in the UI.
- Inputs longer than 4,096 characters are rejected as `too_long` before parsing, which bounds the cost of the regexes.
- A backslash anywhere is `unparseable`. Browsers read `\` as `/` and urllib does not, so the two would disagree on
  the host of `https://evil.example\@example.com/`. Lone surrogates (from JSON `\ud800` escapes) are `unparseable`
  too.
- User info (`user:pass@`) is dropped and never stored.

## Purity

tldextract loads its bundled snapshot, and idna its tables, on first use, which reads files. `parse.py` triggers both
at import (`_load_tables`), so `normalise()` itself does no I/O. Property 7 catches a lazy import that slips in.
A unit test also checks by construction that the package imports no `os`, `io`, `time`, `random` or `socket` and
calls no `open` or `print`.

## Testing Strategy

- Unit tests: one example table per acceptance criterion, in `tests/unit/test_normaliser_*.py`.
- Property tests: `tests/property/test_normaliser_props.py`, Properties 1 to 7. The strategies generate hosts under
  `example.com`, `example.org` and the demo host, plus real-looking values of each class. `*.test` hosts are not on
  the Public Suffix List, so they drive the rejection property instead.
- Regression corpus: `tests/fixtures/normaliser_corpus.jsonl`, raw-to-expected pairs: the demo site's saved URLs and
  its JS paths, plus hand-written `example.com` cases. Recorded CDX rows join it at exhumer task 1.3. It grows
  whenever a bug is found.
