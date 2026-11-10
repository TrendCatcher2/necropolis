# Requirements Document

## Introduction

The exhumer builds the history of a domain's endpoints from the Internet Archive alone. It pages through the
Wayback Machine CDX API, mines archived JavaScript bundles for API paths, normalises everything with the
`endpoint-normaliser`, and dates each endpoint. It is **passive**: it never sends a request to the target domain
(see `safety.md` rule 1), so it may run on any domain.

## Glossary

- **Exhumer**: the `necropolis.exhumer` module, plus the `necropolis.archive` client it uses.
- **ArchiveClient**: the only HTTP client the Exhumer uses. Its base URL is fixed to `https://web.archive.org`.
- **Capture**: one CDX row: timestamp, original URL, MIME type, status code.
- **Exhume run**: one job for one domain, with its options and its results.
- **Front-end reference**: an endpoint path found inside an archived JS file, with that file's capture timestamp.
- **Current front end**: the set of endpoints referenced by the scripts that the newest archived capture of a host's
  root page (`/`) loads, through same-site `<script src>`. Fallback, if no root-page capture exists: scripts captured
  within 30 days of the newest script capture.
- **Zombie candidate**: an `api` endpoint that is not in the current front end.

## Requirements

### Requirement 1: Validate the target

**User Story:** As a user, I want to type a domain and get a clear answer straight away if it is not valid, so that
I don't wait for a job that cannot work.

#### Acceptance Criteria

1. WHEN a user submits a domain THE Exhumer SHALL accept it only if it is a hostname under a public suffix, after
   trimming whitespace, a scheme and a path.
2. IF the input is an IP address, `localhost`, a single label, or a reserved test suffix (`.test`, `.local`,
   `.internal`, `.invalid`, `.localhost`) THEN THE Exhumer SHALL reject it with a plain-language message.
   Exception: fixture mode, which accepts `.test` for tests.
3. THE Exhumer SHALL offer scope `host` (only that hostname) or `domain` (the hostname and all its subdomains), with
   `host` as the default.

### Requirement 2: Enumerate captures from the CDX API

**User Story:** As an AppSec engineer, I want every archived URL for my domain, so that the inventory is complete.

#### Acceptance Criteria

1. WHEN an exhume run starts THE Exhumer SHALL query the CDX API with the fields timestamp, original, MIME type and
   status code, collapsed by URL key, for the chosen scope and an optional year range.
2. WHILE the CDX API returns a resume key THE Exhumer SHALL request the next page until no key is returned or the
   cap is reached.
3. THE Exhumer SHALL stop at 200,000 captures per run. It SHALL report that the cap was reached, and suggest
   narrowing the year range.
4. THE Exhumer SHALL normalise each capture and count rejected captures by reason, without failing the run.

### Requirement 3: Be a polite archive client

**User Story:** As the maintainer, I want Necropolis to respect the Internet Archive, so that the tool does not get
blocked and does not harm a public service.

#### Acceptance Criteria

1. THE ArchiveClient SHALL send at most one request at a time, at no more than `NECROPOLIS_ARCHIVE_RPS` requests per
   second (default 1).
2. WHEN the archive answers 429 or 503 THE ArchiveClient SHALL honour `Retry-After` when present, otherwise back off
   exponentially (2 s, 4 s, 8 s, 16 s, 32 s), and give up after 5 retries.
3. THE ArchiveClient SHALL cache every CDX page and snapshot in SQLite for 7 days, keyed by the full request, and
   SHALL serve repeated runs from the cache.
4. THE ArchiveClient SHALL refuse to send a request to any host other than `web.archive.org`.

### Requirement 4: Mine archived JavaScript

**User Story:** As a bug hunter turned defender, I want API paths pulled out of old JS bundles, so that endpoints
that were only ever called from code are found too.

#### Acceptance Criteria

1. THE Exhumer SHALL select up to 50 script captures per run: the newest and oldest capture of each distinct script
   key first, then spread evenly over time.
2. THE Exhumer SHALL fetch each selected script in its raw archived form (`id_` snapshot) and read at most 2 MiB of
   it.
3. THE Exhumer SHALL extract candidate paths from string and template literals, and treat them as text only, never
   executing them:
   - strings starting with `/` that contain an API-like segment;
   - absolute `http(s)` URLs.
4. WHEN a template literal contains `${...}` THE Exhumer SHALL replace each interpolation with the `{id}`
   placeholder before normalising.
5. THE Exhumer SHALL keep only absolute URLs whose registrable domain equals the target's, and relative paths
   resolved against the script's host.
6. THE Exhumer SHALL record a front-end reference (endpoint key, script key, script capture timestamp) for each
   kept path.
7. THE Exhumer SHALL fetch the newest raw capture of each in-scope host's root page (at most 2 MiB). It SHALL list
   that page's same-site `<script src>` URLs, and SHALL always include those scripts in the selection of
   criterion 4.1. This is how the current front end is known.

### Requirement 5: Aggregate and date endpoints

**User Story:** As a user, I want each endpoint dated, so that I can see when it was born, when the front end stopped
using it, and whether it is a zombie candidate.

#### Acceptance Criteria

1. THE Exhumer SHALL record for each endpoint key:
   - `first_seen`: the earliest capture or reference timestamp;
   - `last_seen`: the latest;
   - `last_seen_in_frontend`: the latest front-end reference timestamp, or none;
   - the capture count, the set of archived status codes, the MIME types, and the sources (`cdx`, `js`);
   - the example path (the latest concrete one).
2. THE Exhumer SHALL mark an `api` endpoint as a zombie candidate WHEN it is not in the current front end.
3. WHEN an endpoint is known only from JS, with placeholders and no concrete capture, THE Exhumer SHALL store it
   without an example path.

### Requirement 6: Report progress and degrade gracefully

**User Story:** As a user watching the graveyard fill, I want live progress and partial results, so that a slow
archive or a failure does not leave me with nothing.

#### Acceptance Criteria

1. WHILE a run is active THE Exhumer SHALL emit progress events (phase, pages fetched, captures, endpoints, scripts
   mined) at least every 2 seconds.
2. IF the archive fails after the retries THEN THE Exhumer SHALL finish with status `partial`, keep everything
   gathered so far, and state which phase failed.
3. WHEN the archive has no captures for the domain THE Exhumer SHALL finish with status `empty`. This is not an
   error.
4. THE Exhumer SHALL let a user cancel a run. Results gathered before the cancel are kept as `partial`.
