# Design Document: graveyard-ui

## Overview

FastAPI serves the JSON API, the SSE job streams and the built React app from one origin. The UI is one page with
four views:

1. **Landing**
2. **Graveyard**: map plus timeline, with a detail drawer
3. **Ownership**: the proof wizard
4. **Burial**: the plan builder

The table view is a toggle inside Graveyard. Layout and timeline logic are pure TypeScript modules, property-tested
with fast-check. The SVG components only draw what those modules compute.

## Architecture

```
web/src/
  api/client.ts          typed fetch wrapper (adds X-Necropolis header, JSON), SSE helper with reconnect
  graveyard/layout.ts    pure: endpoints → crypt plots → tombstone positions (deterministic, no overlap)
  graveyard/timeline.ts  pure: (endpoints, year) → visible + abandoned sets
  graveyard/style.ts     pure: severity → {label, icon, className}
  components/            Tombstone, Crypt, Legend, TimelineSlider, DetailDrawer, ProofWizard, BurialBuilder, TableView
  pages/                 Landing, Graveyard, Ownership, Burial
  styles/                tokens.css (palette, motion), fonts
```

### Visual language

- A night palette: deep blue-black, moss green, bone white, lantern amber, ghost green for the glow.
  Severity colours are checked for AA contrast against the background.
- Each crypt is an arched plot with its version name on the lintel.
- Tombstones are SVG shapes; the engraving is SVG text.
- Motion, CSS only:
  - glow: an opacity pulse of 3 s;
  - twitch: a 2-degree rotate every 4 s;
  - rising: translate-y on result;
  - lay to rest: sink and fade.
  All of it is disabled under `prefers-reduced-motion`.
- Fonts: one display font for headings and engravings (OFL), and the system UI font for everything else.

## Components and Interfaces

### API routes

| Method + path | Body / query | Returns |
|---|---|---|
| `POST /api/exhumes` | `{domain, scope, year_from?, year_to?}` | `{job_id}` |
| `GET /api/jobs/{id}` | | Job state + result summary |
| `GET /api/jobs/{id}/events` | | SSE: `progress`, `endpoint`, `probe_result`, `done`, `error` |
| `DELETE /api/jobs/{id}` | | Cancel |
| `GET /api/domains/{domain}/graveyard` | `run=latest` | Endpoints + autopsies + proofs coverage |
| `POST /api/ownership/challenges` | `{domain}` | Challenge with DNS and file instructions |
| `POST /api/ownership/challenges/{id}/verify` | `{method: "dns" \| "file", origin?}` | Proof or failure reason |
| `GET /api/ownership/proofs` | | Workspace proofs |
| `DELETE /api/ownership/proofs/{id}` | | Revoke |
| `POST /api/probes` | `{domain}` | `{job_id}` |
| `POST /api/probes/reprobe` | `{keys: [...]}` | `{job_id}` |
| `POST /api/burial-plans` | `{domain, keys, rites?, include_lifecycle_steering}` | `{slug, files}` or refusal |
| `POST /api/burial-plans/zip` | Same | `application/zip` |
| `GET /api/report` | `domain, format=md\|json` | Report |
| `GET /api/demo` | | Recorded demo run (fixture mode or bundled) |
| `GET /api/health` | | `{ok, probes_enabled}` |

### Middleware

- Workspace cookie: created on first request.
- CSRF guard: for POST and DELETE, require JSON content type and `X-Necropolis: 1`; otherwise 403
  `csrf_header_missing`.
- Security headers on every response:
  - a strict CSP (`default-src 'self'`, no inline scripts, `img-src 'self' data:`);
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - `frame-ancestors 'none'`.

### Pure UI modules

```ts
layout(endpoints: TombstoneData[], viewport: Size): Placement[]        // deterministic; sorted by crypt then template
visibleAt(endpoints: TombstoneData[], year: number): { visible: Set<string>; abandoned: Set<string> }
severityStyle(s: Severity | null): { label: string; icon: IconName; className: string }
```

## Data Models

`TombstoneData` (from `/graveyard`):
- `key`, `template`, `crypt`;
- `first_seen`, `last_seen`, `last_seen_in_frontend`;
- `capture_count`, `sources`, `example_path_present`, `zombie_candidate`;
- `outcome`, `status`, `severity`, `score`, `signals`, `cause_of_death`, `covered_by_proof`.

## Correctness Properties

### Property 1: The timeline shows what existed
*For any* endpoints and year `y`:
- `visibleAt(e, y).visible` is exactly the set with `first_seen.year <= y`;
- `abandoned` is exactly the visible set with `last_seen_in_frontend.year < y`;
- `visible` only grows as `y` increases.
**Validates: Requirement 4.2**

### Property 2: Every tombstone has exactly one plot
*For any* endpoints and viewport:
- `layout` places each endpoint exactly once, inside its crypt's plot;
- no two tombstones' boxes overlap;
- the result is identical for any input order.
**Validates: Requirements 3.1, 3.4**

### Property 3: Severity is never colour alone
*For any* severity, including `null`, `severityStyle` returns a non-empty label and an icon, and distinct severities
get distinct labels and icons.
**Validates: Requirements 3.2, 9.3**

### Property 4: Archive strings render as text
*For any* template and cause-of-death string (arbitrary Unicode, including HTML), rendering `Tombstone` and
`DetailDrawer` gives text content containing the string, and adds no elements beyond the component's fixed
structure.
**Validates: Requirement 9.4**

### Property 5: Cross-site requests are refused
*For any* state-changing route and any request lacking the JSON content type or the `X-Necropolis` header, the API
answers 403 and changes no state (Hypothesis over routes and header combinations).
**Validates: Requirement 10.3**

### Property 6: Workspaces are isolated
*For any* two workspaces and any sequence of challenge, verify, probe and plan calls, no response to workspace B
contains or acts on A's challenges, proofs, runs or plans.
**Validates: Requirement 10.4**

## Error Handling

| State | UI |
|---|---|
| Invalid domain | Inline message under the input |
| Archive slow (429) | Progress line: "The archive asked us to wait, retrying in N s" |
| `partial` | Amber banner naming the failed phase, with a "Retry" button; the map shows what we have |
| `empty` | Full-screen empty state: "Nothing buried here", with a tip (try "include subdomains") |
| Probe refused | Drawer explains the reason, with a link to the ownership wizard or the next allowed time |
| SSE lost | Silent reconnect; after 3 failures, a banner with "Reload results" |
| API down | Error page with a retry button; the demo graveyard still works (bundled) |

## Testing Strategy

- fast-check: Properties 1 to 4 in `web/src/**/*.test.ts(x)`.
- Hypothesis plus the FastAPI TestClient: Properties 5 and 6 in `backend/tests/property/test_api_props.py`.
- Component tests for each state in the error table.
- Playwright, against fixture mode:
  1. landing;
  2. demo graveyard;
  3. timeline replay;
  4. open the Rampaging tombstone;
  5. ownership (fake verify);
  6. raise;
  7. burial plan zip;
  8. re-probe shows laid to rest.
- Accessibility: an axe-core check in Playwright on every view, plus one keyboard-only run of the main flow.
