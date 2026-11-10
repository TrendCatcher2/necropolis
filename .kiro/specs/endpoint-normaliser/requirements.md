# Requirements Document

## Introduction

The endpoint normaliser turns raw archived URLs, and paths mined from archived JavaScript, into stable **endpoint
keys**. Thousands of captures like `/api/v1/users/123?ref=mail` and `/api/v1/users/9876` must become one tombstone,
`/api/v1/users/{id}`. Every other module depends on this being correct and stable, so it is pure, needs no network
access, and is the most heavily property-tested part of Necropolis.

## Glossary

- **Normaliser**: the `necropolis.normaliser` module.
- **Raw URL**: a URL string as found in a CDX row or in archived JS. It can be absolute, scheme-relative or a bare
  path.
- **EndpointKey**: the normalised identity of an endpoint: `host`, `path_template`, `crypt`, `param_names`.
- **Path template**: the path with variable segments replaced by placeholders: `{id}`, `{uuid}`, `{hash}`, `{token}`,
  `{date}`, `{email}`.
- **Crypt**: the API version that an endpoint belongs to (`v1`, `v2.1`, or `unversioned`).
- **Example value**: the most recent concrete path seen for a key, kept so the prober has a real path to request.

## Requirements

### Requirement 1: Parse and canonicalise

**User Story:** As an AppSec engineer, I want messy archived URLs reduced to one canonical form, so that the same
endpoint is not counted many times.

#### Acceptance Criteria

1. WHEN the Normaliser receives a raw URL THE Normaliser SHALL lowercase the scheme and host, convert the host to its
   IDNA (punycode) form, and remove a trailing dot from the host.
2. WHEN the URL carries the default port for its scheme (80 for http, 443 for https) THE Normaliser SHALL remove the
   port.
3. THE Normaliser SHALL remove the fragment, merge repeated slashes, resolve `.` and `..` segments, and remove a
   trailing slash except on the root path `/`.
4. THE Normaliser SHALL percent-decode only unreserved characters (RFC 3986 section 2.3) and SHALL keep path case
   unchanged.
5. WHEN the raw value is a bare path (from JS) THE Normaliser SHALL resolve it against the host it was mined from.
6. IF the raw value cannot be parsed, uses a scheme other than http or https, or has a host that is an IP literal,
   `localhost` or not under a public suffix THEN THE Normaliser SHALL reject it with a reason code and SHALL NOT
   raise an exception.

### Requirement 2: Template variable segments

**User Story:** As a user looking at the graveyard, I want endpoints that differ only by IDs grouped into one
tombstone, so that the map shows the API's shape and not its data.

#### Acceptance Criteria

1. THE Normaliser SHALL replace a path segment with a placeholder when it matches exactly one class, checked in this
   order:
   1. UUID → `{uuid}`
   2. Email address → `{email}`
   3. ISO date `YYYY-MM-DD` → `{date}`
   4. Integer of 1 to 19 digits → `{id}`
   5. Hex string of 16 or more characters → `{hash}`
   6. Opaque token of 20 or more URL-safe characters mixing letters and digits, with no dictionary-word structure →
      `{token}`
2. THE Normaliser SHALL keep version segments matching `v<digits>` or `v<digits>.<digits>` (case-insensitive) as
   literal segments.
3. WHEN two raw URLs differ only in the values of segments that rule 2.1 templates THE Normaliser SHALL return equal
   EndpointKeys.
4. THE Normaliser SHALL keep, for each EndpointKey, the most recent concrete path as its example value, with query
   string and fragment removed.

### Requirement 3: Query strings never leak values

**User Story:** As a security tool owner, I want query values dropped at the boundary, so that archived secrets such
as reset tokens or API keys never reach storage, the UI or a generated spec.

#### Acceptance Criteria

1. THE Normaliser SHALL keep only the query parameter **names**, de-duplicated and sorted, in `param_names`.
2. THE Normaliser SHALL NOT include any query parameter value in any field of its output, including the example
   value.
3. WHEN a parameter name is longer than 64 characters or contains characters outside `[A-Za-z0-9_.\-\[\]]` THE
   Normaliser SHALL drop that name.

### Requirement 4: Classify crypt and kind

**User Story:** As a user, I want endpoints grouped by API version and told apart from static files, so that the
graveyard shows API crypts and not images.

#### Acceptance Criteria

1. THE Normaliser SHALL set `crypt` to the first version segment in the path, or `unversioned` if there is none.
2. WHEN the path ends in a static asset extension (images, fonts, CSS, media, source maps) THE Normaliser SHALL mark
   the key `kind=static`.
3. WHEN the path ends in `.js` or `.mjs` THE Normaliser SHALL mark the key `kind=script`, so the exhumer can mine it.
4. THE Normaliser SHALL mark the key `kind=api` WHEN any of these hold:
   - the path contains a segment equal to `api`, `rest`, `graphql`, `rpc`, `ajax`, `json` or `ws`;
   - the path contains a version segment;
   - the capture MIME type is JSON or XML;
   - the path ends in `.json`, `.xml`, `.php`, `.asp`, `.aspx`, `.jsp` or `.do`.
5. OTHERWISE THE Normaliser SHALL mark the key `kind=page`.

### Requirement 5: Deterministic and pure

**User Story:** As a developer, I want the normaliser to be a pure function, so that results are reproducible across
runs, machines and the MCP server.

#### Acceptance Criteria

1. THE Normaliser SHALL perform no I/O and SHALL NOT read the clock, the environment or random sources.
2. WHEN called twice with the same input THE Normaliser SHALL return equal output.
3. THE Normaliser SHALL expose `render(key) -> str`. Normalising the rendered form SHALL return the same key.
