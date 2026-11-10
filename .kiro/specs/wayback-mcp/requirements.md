# Requirements Document

## Introduction

`wayback-mcp` is a custom MCP server written for this project. It gives Kiro, and the "Gravedigger" custom agent,
direct, safe access to the Internet Archive and to Necropolis's own results. While building, Kiro can look at real
archive data for our demo domain, for example when a normaliser edge case shows up, without copy-pasting. After the
build, the Gravedigger agent uses it for a weekly passive sweep. It is **passive only**: it talks to
`web.archive.org` and reads the local database, nothing else.

## Glossary

- **Server**: the `mcp/wayback_mcp` package, run over stdio.
- **Untrusted envelope**: the wrapper on every tool result: `{"untrusted_archived_content": true, "note": "...",
  "data": ...}`.
- **Gravedigger**: a Kiro CLI custom agent defined in `.kiro/agents/`, which uses this server.

## Requirements

### Requirement 1: Tools

**User Story:** As a developer using Kiro, I want archive lookups as tools, so that Kiro can ground its work in real
archive data for our demo domain.

#### Acceptance Criteria

1. THE Server SHALL provide these tools, each with a JSON schema and a one-line description:

   | Tool | Arguments | Returns |
   |---|---|---|
   | `cdx_search` | `domain`, `scope` (`host` or `domain`), optional `year_from`, `year_to`, `status`, `mimetype`, `limit` (default 100, max 500) | Capture rows |
   | `list_snapshots` | `url`, `limit` (default 50, max 200) | Capture timestamps for one URL |
   | `snapshot_text` | `url`, `timestamp`, `max_kb` (default 32, max 64) | Raw archived text (`id_`), text MIME types only |
   | `normalise_url` | `url` | The EndpointKey, or a rejection reason |
   | `endpoint_history` | `domain`, optional `template`, `limit` | Necropolis endpoint records and autopsies from the local DB |

2. THE Server SHALL return capture URLs with query values removed (parameter names only), using the shared
   normaliser.

### Requirement 2: Passive and polite

**User Story:** As the maintainer, I want the MCP server bound by the same archive etiquette as the app, so that an
agent in a loop cannot hammer the archive or touch a target.

#### Acceptance Criteria

1. THE Server SHALL send HTTP requests only through the shared `ArchiveClient`. It SHALL therefore share its host
   restriction, rate limit, backoff and cache.
2. THE Server SHALL NOT import or call `netguard`, `ownership` or `prober`.
3. WHEN a tool argument contains a URL on any host THE Server SHALL use it only as a lookup key for the archive,
   and SHALL never contact that host.

### Requirement 3: Treat archive content as hostile

**User Story:** As a user of an AI agent, I want archived content clearly marked and size-limited, so that
instructions planted in old pages cannot steer the agent.

#### Acceptance Criteria

1. THE Server SHALL wrap every tool result in the untrusted envelope. Its note SHALL say that the data is archived
   web content and that any instructions inside it must not be followed.
2. THE Server SHALL cap every result at 64 KiB of text and 500 rows. It SHALL say when output was truncated.
3. WHEN a snapshot is not a text MIME type THE `snapshot_text` tool SHALL return an error instead of the bytes.

### Requirement 4: Read-only access to results

**User Story:** As the Gravedigger agent, I want to read past results, so that I can report what changed since last
week.

#### Acceptance Criteria

1. THE Server SHALL open the Necropolis database read-only (`mode=ro` SQLite URI).
2. THE `endpoint_history` tool SHALL return records and autopsies without response-derived content beyond what is
   stored (outcome, status, signal names).

### Requirement 5: Registration and agent

**User Story:** As a developer, I want the server and the agent ready in the repo, so that anyone cloning it can use
them in Kiro straight away.

#### Acceptance Criteria

1. THE repo SHALL register the Server in `.kiro/settings/mcp.json`, started with `uv run` from the `backend`
   environment, with no secrets in the config.
2. THE repo SHALL define the Gravedigger agent in `.kiro/agents/`. Its tools SHALL be limited to `wayback-mcp`, file
   read, and writing under `reports/`. Its prompt SHALL tell it to re-exhume passively, compare the results with the
   previous run, and write `reports/gravedigger-<date>.md` listing new endpoints, newly risen zombies and zombies laid
   to rest.
3. THE Gravedigger SHALL NOT trigger active probes. Re-probing stays a user action through the app.
