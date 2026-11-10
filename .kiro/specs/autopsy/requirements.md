# Requirements Document

## Introduction

The autopsy explains each probed endpoint. It turns exhume history and probe results into named **risk signals**, a
**severity** ("how far it has risen") and a plain-language **cause of death**. It is pure and deterministic. It uses
no LLM, so every word on a tombstone can be traced to a fact. It also provides `body_signals`, the in-memory check
that the prober runs on the first 64 KiB of a response before the bytes are discarded.

## Glossary

- **Autopsy**: the `necropolis.autopsy` module.
- **Resource path**: a path template with its version segment removed. `/api/v1/users/{id}` and `/api/v2/users/{id}`
  share the resource path `/api/users/{id}`.
- **Sibling**: another endpoint on the same host with the same resource path (any crypt), or with the same parent
  template in the same crypt.
- **Alive outcomes**: `open`, `redirected`, `erroring`, `guarded`, `other` and `rate_limited`.
- **Severity**: `BURIED` < `STIRRING` < `RISEN` < `RAMPAGING`. If the endpoint was not probed, the severity is
  `None`, shown as "Unexamined".

## Requirements

### Requirement 1: Body signals (in memory only)

**User Story:** As a privacy-minded user, I want risky response content recognised without being stored, so that I
learn that an endpoint leaks data without Necropolis keeping that data.

#### Acceptance Criteria

1. THE Autopsy SHALL expose `body_signals(data: bytes, content_type: str | None) -> frozenset[str]`. It SHALL read at
   most the first 64 KiB, and SHALL return names only from this fixed vocabulary:
   - `stack_trace`, `debug_mode`, `sql_error`
   - `json_pii_keys`, `json_record_list`
   - `login_form`, `directory_listing`
2. THE Autopsy SHALL detect `json_pii_keys` WHEN the body parses as JSON (or as a JSON prefix) and contains at least
   one key, at any depth up to 5, from this list: `email`, `phone`, `password`, `passwd`, `token`, `secret`, `ssn`,
   `dob`, `address`, `api_key`.
3. THE Autopsy SHALL NOT return, log or embed any part of the body in its result.
4. FOR ANY input bytes THE Autopsy SHALL return a result and SHALL NOT raise.

### Requirement 2: Risk signals

**User Story:** As an AppSec engineer, I want named, explainable reasons why a zombie matters, so that I can fix the
worst ones first and trust the ranking.

#### Acceptance Criteria

1. THE Autopsy SHALL assign these signals from the endpoint record, its probe result and its siblings:
   - `removed_from_frontend`: a zombie candidate with an alive outcome.
   - `version_behind`: a sibling with the same resource path in a higher crypt appears in the current front end.
   - `auth_asymmetry`: outcome `open`, and at least one sibling's outcome is `guarded`.
   - `verbose_error`: the body signals include `stack_trace`, `debug_mode` or `sql_error`.
   - `sensitive_path`: a path segment matches the sensitive list:
     - `admin`, `debug`, `internal`, `actuator`, `console`, `phpinfo`;
     - `swagger`, `api-docs`, `openapi`, `graphql`;
     - `metrics`, `env`, `config`, `backup`, `test`, `staging`, `dev`.
   - `docs_exposed`: outcome `open` and the path is an API-description path (`swagger`, `openapi`, `api-docs`).
   - `data_exposed`: outcome `open` and the body signals include `json_pii_keys` or `json_record_list`.
2. THE Autopsy SHALL classify `removed_from_frontend` and `version_behind` as **context** signals, and all the
   others as **risk** signals.

### Requirement 3: Severity

**User Story:** As a user scanning the graveyard, I want one clear level per tombstone, so that the glow on the map
means something consistent.

#### Acceptance Criteria

1. IF the endpoint was not probed, or its outcome is `refused` or `not_probeable` THEN THE Autopsy SHALL set
   severity to `None`.
2. WHEN the outcome is `gone` or `unreachable` THE Autopsy SHALL set severity `BURIED`, whatever the signals.
3. WHEN the outcome is `guarded`, `redirected`, `other` or `rate_limited` THE Autopsy SHALL set severity `STIRRING`.
4. WHEN the outcome is `open` or `erroring` with no risk signal THE Autopsy SHALL set severity `RISEN`.
5. WHEN the outcome is `open` or `erroring` with at least one risk signal THE Autopsy SHALL set severity `RAMPAGING`.
6. THE Autopsy SHALL compute a numeric `score` to order endpoints within a severity, as a documented weighted sum of
   signals.

### Requirement 4: Cause of death

**User Story:** As a non-specialist reading a tombstone, I want two or three plain sentences explaining what
happened, so that I understand the risk without reading HTTP codes.

#### Acceptance Criteria

1. THE Autopsy SHALL produce a cause-of-death text from fixed sentence templates, filled only with facts from the
   input:
   - dates (month and year);
   - crypt names, status code and outcome;
   - sibling templates;
   - signal names.
2. THE Autopsy SHALL include one sentence for each signal present, and none for absent signals.
3. THE Autopsy SHALL produce plain text only. Escaping is the job of the renderer (UI or burial plan).

### Requirement 5: Pure and deterministic

**User Story:** As a developer, I want the autopsy to be a pure function, so that results are reproducible and can
be property-tested.

#### Acceptance Criteria

1. THE Autopsy SHALL perform no I/O and SHALL take `now` as a parameter.
2. WHEN given equal inputs THE Autopsy SHALL return equal outputs, whatever the order of the sibling lists.
