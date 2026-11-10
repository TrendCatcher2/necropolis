# Design Document: autopsy

## Overview

The autopsy runs in two places:

1. `body_signals` runs inside the probe runner. The bytes are dropped right after.
2. `examine(records, probe_results, now)` runs after a probe run (and after every re-probe). It returns an `Autopsy`
   for each endpoint.

Both are pure (no I/O, no network: passive by construction).

## Architecture

```
probe bytes ─► body_signals ─► frozenset[str] ─(stored as names in ProbeResult)
EndpointRecords + ProbeResults ─► build sibling index ─► signals ─► severity + score ─► cause_of_death ─► [Autopsy]
```

## Components and Interfaces

```python
def body_signals(data: bytes, content_type: str | None) -> frozenset[str]
def resource_path(template: str) -> str
def sibling_index(records: list[EndpointRecord]) -> Mapping[EndpointKey, tuple[EndpointKey, ...]]
def signals_for(rec, result, siblings, results_by_key) -> tuple[frozenset[str], frozenset[str]]  # (context, risk)
def severity(outcome: Outcome | None, risk: frozenset[str]) -> Severity | None
def score(context: frozenset[str], risk: frozenset[str]) -> int
def cause_of_death(rec, result, signals, siblings) -> str
def examine(records, results, now) -> list[Autopsy]
```

### Body-signal detectors (bounded, regex and JSON)

| Signal | Detector (on the first 64 KiB, decoded with replacement) |
|---|---|
| `stack_trace` | `Traceback (most recent call last)`, `\n\s+at [\w$.]+\(.*:\d+\)`, `Exception in thread`, `System.\w+Exception` |
| `debug_mode` | Werkzeug or Django debug page markers, `Whitelabel Error Page`, `DEBUG = True`, `X-Debug-Token` (header passed in) |
| `sql_error` | `SQLSTATE[`, `syntax error at or near`, `ORA-\d{5}`, `You have an error in your SQL syntax` |
| `json_pii_keys` | JSON parse, or a streaming prefix parse when the body is truncated; key walk to depth 5 |
| `json_record_list` | A top-level array (or `data`/`items`/`results`) of 2 or more objects sharing 3 or more keys |
| `login_form` | `<form` containing `type="password"` |
| `directory_listing` | `<title>Index of /` |

`[VERIFY: marker strings against current Django, Flask/Werkzeug, Spring Boot and Express default error pages
before freezing the fixtures.]`

### Score weights

| Signal | Weight |
|---|---|
| `data_exposed` | 40 |
| `auth_asymmetry` | 35 |
| `verbose_error` | 20 |
| `docs_exposed` | 15 |
| `sensitive_path` | 10 |
| `version_behind` (context) | 5 |
| `removed_from_frontend` (context) | 5 |

The score orders tombstones within a severity only. It never changes the severity.

### Cause-of-death templates (examples)

- Base: "Born {first_seen:%b %Y}. The front end last called it in {last_fe:%b %Y}." If there is no front-end
  reference: "The front end never referenced it in the archive."
- `version_behind`: "It was replaced by {sibling} in {crypt}."
- `auth_asymmetry`: "It still answers {status} without authentication, while {sibling} asks for it."
- `data_exposed`: "Its response looks like personal or record data."
- `verbose_error`: "It returns a detailed error that reveals internals."
- `BURIED`: "It no longer answers ({status_or_reason}). Rest in peace."

## Data Models

```python
class Severity(IntEnum): BURIED=0; STIRRING=1; RISEN=2; RAMPAGING=3
class Autopsy(BaseModel, frozen=True):
    key: EndpointKey; severity: Severity | None; score: int
    context_signals: frozenset[str]; risk_signals: frozenset[str]
    siblings: tuple[EndpointKey, ...]; cause_of_death: str; examined_at: datetime
```

## Correctness Properties

### Property 1: More risk never means less severity
*For any* outcome and risk-signal sets `A ⊆ B`, `severity(outcome, A) <= severity(outcome, B)`. This holds whenever
both are not `None`.
**Validates: Requirements 3.4, 3.5**

### Property 2: The buried stay buried
*For any* risk signals, `severity(GONE, s) == severity(UNREACHABLE, s) == BURIED`.
**Validates: Requirement 3.2**

### Property 3: Unprobed means unexamined
*For any* signals, outcomes `None`, `REFUSED` and `NOT_PROBEABLE` give severity `None`.
**Validates: Requirement 3.1**

### Property 4: The explanation matches the evidence
*For any* autopsy:
- every present signal has its sentence in `cause_of_death`, and absent signals have none;
- every number (year or status) in the text appears in the input record or probe result.
**Validates: Requirements 4.1, 4.2**

### Property 5: body_signals is total, bounded and leak-free
*For any* byte string up to 1 MiB:
- `body_signals` returns a subset of the fixed vocabulary and never raises;
- its result does not depend on bytes after 64 KiB;
- a random 32-character marker in the body never appears in the result's string form.
**Validates: Requirements 1.1, 1.3, 1.4**

### Property 6: Auth asymmetry points one way
*For any* pair of siblings where one is `open` and the other `guarded`, only the `open` one gets `auth_asymmetry`.
**Validates: Requirement 2.1**

### Property 7: Order independence
*For any* permutation of the records and results lists, `examine` returns the same set of autopsies.
**Validates: Requirement 5.2**

## Error Handling

- A missing probe result gives severity `None` and the base sentence only.
- Malformed JSON gives no JSON signals. It is not an error.
- Unknown outcome values cannot happen: the type is an enum, and validation fails at the boundary.

## Testing Strategy

- Unit tests: a fixtures folder of tiny fake error pages and JSON bodies, each with its expected signals; the
  severity table; the demo-site scenario (v1 users open + v2 guarded → `RAMPAGING`, with `auth_asymmetry`,
  `data_exposed`, `version_behind` and `removed_from_frontend`).
- Property tests: Properties 1 to 7 in `tests/property/test_autopsy_props.py`.
