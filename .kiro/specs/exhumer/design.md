# Design Document: exhumer

## Overview

The exhumer is an async job: **validate → page CDX → normalise → pick scripts → mine JS → aggregate → save**. All
network access goes through `ArchiveClient` (passive). The aggregation step is a pure function, so it is
property-tested without any I/O.

## Architecture

```
ExhumeRequest ─► validate_target ─► CdxPager (ArchiveClient) ─► normalise() ─► CaptureRows
                                                                                │
                         pick_scripts(CaptureRows) ─► SnapshotFetcher (ArchiveClient, id_) ─► js_miner
                                                                                │
                                         aggregate(captures, references, now) ─► EndpointRecords ─► SQLite
progress ──► JobBus (in-process pub/sub) ──► SSE (graveyard-ui spec)
```

- **Passive only.** `ArchiveClient` is built with `base_url="https://web.archive.org"`. A transport-level check
  raises `ArchiveHostViolation` for any other host. The exhumer never imports `netguard` or `prober`.
- `now` is passed in, which keeps `aggregate` pure.

## Components and Interfaces

```python
# necropolis/archive/client.py
class ArchiveClient:
    async def cdx_page(self, q: CdxQuery, resume_key: str | None) -> CdxPage: ...
    async def snapshot(self, timestamp: str, url: str, max_bytes: int) -> bytes: ...

# necropolis/exhumer/
def validate_target(raw: str, *, fixture_mode: bool) -> Target | InvalidTarget
async def cdx_captures(client, target, scope, years) -> AsyncIterator[CaptureRow]   # pages via resumeKey
def pick_scripts(rows: list[CaptureRow], limit: int = 50) -> list[CaptureRow]
def mine_js(text: str, script_url: str, target: Target) -> list[str]                # pure; raw path strings
def aggregate(rows, refs, now) -> list[EndpointRecord]                              # pure
async def run_exhume(job: ExhumeJob) -> ExhumeResult
```

### CDX query

`GET /cdx/search/cdx` with:
- `url=<host>/*` (scope `host`) or `url=<host>` with `matchType=domain` (scope `domain`);
- `output=json`, `fl=timestamp,original,mimetype,statuscode`, `collapse=urlkey`;
- `showResumeKey=true`, `limit=5000`, plus optional `from` and `to` (years).

The JSON output is a header row followed by data rows. When a resume key exists, it comes after an empty row.

`[VERIFY: exact JSON shape with showResumeKey on the live API, then freeze it into a recorded fixture.]`

### JS miner

- Decodes as UTF-8 with replacement and scans with bounded regexes. There are no catastrophic-backtracking
  patterns: each regex is tested against a 2 MiB adversarial string within 1 s.
- Candidate patterns:
  - quoted strings `"/…"`, `'/…'` and template literals `` `/…${x}…` `` up to 300 characters;
  - absolute `https?://` URLs.
- A path is kept if `kind=api` after normalising, or if it has two or more segments and a JSON-ish context
  (`fetch(`, `axios.`, `.get(`, `.post(`, `url:`) within 40 characters before it.

### Dating

- `first_seen` and `last_seen` cover both CDX captures and JS references.
- `last_seen_in_frontend` is the maximum script-capture timestamp among the references.
- The current front end is the set of keys referenced by the scripts that the newest root-page capture loads
  (Requirement 4.7). If there is no root-page capture, it falls back to scripts captured within 30 days of the
  newest script capture. A fixed time window alone failed the demo: v1 and v2 are archived days apart. If the
  domain has no scripts, zombie candidacy is `unknown`, not `true`.

## Data Models

```python
class CaptureRow(BaseModel): timestamp: datetime; original: str; mimetype: str | None; status: int | None
class FrontendRef(BaseModel): key: EndpointKey; script_key: EndpointKey; seen_at: datetime
class EndpointRecord(BaseModel):
    key: EndpointKey
    first_seen: datetime; last_seen: datetime; last_seen_in_frontend: datetime | None
    capture_count: int; archived_statuses: set[int]; mimetypes: set[str]
    sources: set[Literal["cdx", "js"]]; example_path: str | None
    zombie_candidate: bool | None      # None = unknown (no JS history)
class ExhumeResult(BaseModel):
    status: Literal["complete", "partial", "empty", "cancelled"]; failed_phase: str | None
    endpoints: list[EndpointRecord]; rejected: dict[str, int]; capped: bool
```

SQLite tables: `archive_cache(req_hash PK, body, fetched_at)`, `exhume_runs`, `endpoints(run_id, key_json, ...)`,
`frontend_refs`.

## Correctness Properties

### Property 1: Exhumer is passive
*For any* generated CDX data (including original URLs on arbitrary hosts) and JS bodies (including absolute URLs to
arbitrary hosts), every request recorded by the mock transport during `run_exhume` has host `web.archive.org`.
**Validates: Requirements 3.4; safety rule 1**

### Property 2: Paging collects every row exactly once
*For any* list of CDX rows split into any number of pages with resume keys, `cdx_captures` yields each row exactly
once, in order, stopping when no key is returned or the cap is hit.
**Validates: Requirements 2.2, 2.3**

### Property 3: Dating is order-independent and correct
*For any* multiset of captures and references, `aggregate` gives the same records for every permutation of its
input. For each key, `first_seen` is the minimum timestamp, `last_seen` the maximum, and `capture_count` the number
of CDX rows.
**Validates: Requirement 5.1**

### Property 4: More history never shrinks the inventory
*For any* inputs A and B, every key in `aggregate(A)` is in `aggregate(A ∪ B)`, with a `first_seen` no later and a
`last_seen` no earlier.
**Validates: Requirement 5.1**

### Property 5: JS mining stays on the target's site
*For any* JS text containing absolute URLs on random registrable domains, `mine_js` keeps only those whose
registrable domain equals the target's.
**Validates: Requirement 4.5**

### Property 6: Script limits hold
*For any* list of script captures, `pick_scripts` returns at most 50 items, includes the newest and oldest of each
script key while within the limit, and the fetcher never reads more than 2 MiB per snapshot.
**Validates: Requirements 4.1, 4.2**

## Error Handling

| Situation | Behaviour |
|---|---|
| Invalid domain | 422 with a plain message; no job created |
| Archive 429/503 | Back off and retry (Requirement 3.2); progress event "the archive asked us to wait" |
| Archive down after retries | `partial` with `failed_phase` |
| No captures | `empty`; the UI shows the "nothing buried here" state |
| Malformed CDX row | Skipped and counted as `rejected["malformed_row"]` |
| Script fetch fails | Skipped; the run continues; counted |
| Cancel | `cancelled`; partial data kept |

## Testing Strategy

- Recorded fixtures: the CDX pages and three JS snapshots of our own demo domain, captured once by a script
  (`scripts/record_fixtures.py`, run by hand) into `tests/fixtures/archive/`.
- Unit tests: validation table, CDX JSON parsing (with and without a resume key), JS miner examples (fetch, axios,
  template literals, minified bundle), dating examples.
- Property tests: Properties 1 to 6 in `tests/property/test_exhumer_props.py`.
- Regex performance test: every miner regex runs over an adversarial 2 MiB input in under 1 s.
