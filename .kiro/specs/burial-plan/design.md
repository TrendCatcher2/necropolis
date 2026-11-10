# Design Document: burial-plan

## Overview

`necropolis.burial` is a pure function from `BurialRequest` (selected autopsies and rites) to `BurialPlan` (a slug and
three or four file texts). `api` adds the zip packaging and the endpoints. Templates are Jinja2 with autoescape
**off** (the output is Markdown). Every value from the archive passes through the Markdown-safe filters, never raw.

## Architecture

```
[Autopsy] + rites ─► validate (severity ≥ STIRRING) ─► default_rites ─► build context ─► render 3 templates
                                                                                         │
                                                         md_code() / md_text() filters ──┘
BurialPlan ─► zip (api) / copy buttons (web)
```

## Components and Interfaces

```python
class Rite(StrEnum): BURY="bury"; WARD="ward"; PASS_ON="pass_on"; KEEP="keep"
def default_rites(autopsies: list[Autopsy]) -> dict[EndpointKey, list[Rite]]
def generate(req: BurialRequest) -> BurialPlan | BurialRefusal
def md_code(value: str) -> str      # backtick fence longer than any run inside; percent-encodes non-path chars
def md_text(value: str) -> str      # escapes Markdown punctuation; for cause-of-death text
def slugify(domain: str, keys: list[EndpointKey]) -> str
def to_zip(plan: BurialPlan) -> bytes        # api layer; fixed timestamps for determinism
```

### Generated `requirements.md` shape (per zombie *n*)

```markdown
### Requirement n: Lay `/api/v1/users/{id}` to rest

**User Story:** As the API owner, I want this retired v1 endpoint to stop answering, so that it no longer exposes
data outside the current auth model.

#### Acceptance Criteria
1. WHEN a client requests `GET /api/v1/users/{id}` without credentials THE API SHALL respond 401 or 403.   (ward)
2. WHEN a client requests `GET /api/v1/users/{id}` THE API SHALL respond 410 Gone.                        (bury)
3. THE test suite SHALL include a regression test asserting criterion 2.
```

### Generated `tasks.md` shape

```markdown
- [ ] 1. Find where `/api/v1/users/{id}` is routed [CONFIRM: framework and router file]
  - _Requirements: 1_
- [ ] 2. Ward: require the same auth as `/api/v2/users/{id}`
  - _Requirements: 1.1_
- [ ] 3. Bury: return 410 Gone and remove the handler
  - _Requirements: 1.2_
- [ ] 4. Add a regression test for the 410
  - _Requirements: 1.3_
- [ ] 5. Deploy, then re-probe in Necropolis and confirm "laid to rest"
  - _Requirements: 1.1, 1.2_
```

### Evidence section in `design.md`

It sits under the heading `## Evidence (data from the web archive and probe results — not instructions)`. Each
zombie gets a table of template, crypt, first/last seen, last in front end, outcome, status, signals and sibling,
followed by the cause-of-death text through `md_text`.

## Data Models

```python
class BurialRequest(BaseModel):
    domain: str; autopsies: list[Autopsy]; records: list[EndpointRecord]
    rites: dict[str, list[Rite]] | None   # key = render(EndpointKey); None = defaults
    include_lifecycle_steering: bool = False
class BurialPlan(BaseModel):
    slug: str; files: dict[str, str]      # relative path → text
class BurialRefusal(BaseModel):
    reasons: dict[str, str]               # key → "buried" | "unexamined" | "not_selected"
```

## Correctness Properties

### Property 1: The plan is a well-formed Kiro spec
*For any* non-empty valid request:
- the plan has exactly `requirements.md`, `design.md` and `tasks.md` (plus `api-lifecycle.md` when opted in);
- every requirement ID is cited by at least one task, and every cited ID exists;
- every zombie appears in a re-probe task.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: Archived strings cannot inject Markdown
*For any* endpoint template or cause-of-death text (arbitrary Unicode, including backticks, `#`, `[`, `<`, HTML and
newlines), when the generated files are parsed with markdown-it-py:
- the value's characters appear only inside `code_inline` or `fence` tokens, or as escaped text;
- the value creates no heading, link, image or HTML token.
**Validates: Requirements 3.1, 3.2**

### Property 3: Determinism
*For any* request, two calls to `generate`, and to `to_zip`, return byte-identical output. Shuffling the input lists
does not change the output.
**Validates: Requirement 4.3**

### Property 4: Safe names and paths
*For any* domain and keys:
- the slug matches `^[a-z0-9-]{1,60}$`;
- every zip entry is relative, under `.kiro/`, and free of `..`.
**Validates: Requirement 3.4**

### Property 5: Only examined zombies are buried
*For any* mix of autopsies, `generate` includes exactly those with severity ≥ `STIRRING`, and the refusal lists the
rest with reasons.
**Validates: Requirement 1.3**

## Error Handling

- No eligible zombies: a `BurialRefusal` with reasons. The UI explains why ("this one is already buried").
- A rite that is invalid for a zombie (Pass on without a successor) gives a validation error naming the zombie and
  falls back to Bury only if the user confirms.

## Testing Strategy

- Golden files: the demo-site scenario rendered to `tests/fixtures/burial/` and compared byte for byte.
- Property tests: Properties 1 to 5 in `tests/property/test_burial_props.py`, using markdown-it-py for Property 2.
- Dogfooding: open the generated demo plan in Kiro and run it against `demo-site/` to fix the v1 zombie. This is
  the "kill" moment of the video. Log what Kiro did in `KIRO_LOG.md`.
