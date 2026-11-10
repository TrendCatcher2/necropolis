# Design Document: wayback-mcp

## Overview

A small Python MCP server using the official `mcp` SDK (FastMCP style, stdio transport). Each tool is a thin
adapter: validate the arguments, call `necropolis.archive` or `necropolis.normaliser`, or run a read-only SQL query,
then wrap the result in the untrusted envelope. Passive only.

## Architecture

```
Kiro / kiro-cli agent ──stdio──► wayback_mcp.server (FastMCP)
                                   ├─ cdx_search / list_snapshots / snapshot_text ─► ArchiveClient ─► web.archive.org
                                   ├─ normalise_url ─► normaliser (pure)
                                   └─ endpoint_history ─► sqlite (mode=ro)
                                   all results ─► envelope(data, truncated) ─► caps (64 KiB / 500 rows)
```

## Components and Interfaces

```python
# mcp/wayback_mcp/server.py
mcp = FastMCP("wayback-mcp")

@mcp.tool()
async def cdx_search(domain: str, scope: Literal["host","domain"]="host", year_from: int | None=None,
                     year_to: int | None=None, status: int | None=None, mimetype: str | None=None,
                     limit: int = 100) -> dict: ...
@mcp.tool()
async def list_snapshots(url: str, limit: int = 50) -> dict: ...
@mcp.tool()
async def snapshot_text(url: str, timestamp: str, max_kb: int = 32) -> dict: ...
@mcp.tool()
def normalise_url(url: str) -> dict: ...
@mcp.tool()
def endpoint_history(domain: str, template: str | None = None, limit: int = 100) -> dict: ...

def envelope(data: object, truncated: bool) -> dict   # {"untrusted_archived_content": True, "note": ..., "truncated": ..., "data": ...}
```

### `.kiro/settings/mcp.json` (written in task 4 once the server runs)

```json
{
  "mcpServers": {
    "wayback-mcp": {
      "command": "uv",
      "args": ["run", "--project", "backend", "python", "-m", "wayback_mcp"],
      "env": { "NECROPOLIS_DB_PATH": "data/necropolis.db" },
      "disabled": false,
      "autoApprove": ["normalise_url", "endpoint_history"]
    }
  }
}
```

`[VERIFY: Kiro mcp.json fields (autoApprove, disabled) and the path resolution for --project against current Kiro
docs.]` Only the two local, read-only tools are auto-approved. Archive-fetching tools ask each time.

### Gravedigger agent (`.kiro/agents/gravedigger.json`)

- Tools: `wayback-mcp` and file read. File write is allowed only under `reports/`.
- The prompt summarises `safety.md` rules 1, 6 and 7, and gives the weekly-sweep procedure:
  1. `endpoint_history` (previous run);
  2. `cdx_search` (fresh), and `normalise_url` for each row;
  3. diff the two;
  4. write the report.

`[VERIFY: kiro-cli custom agent file format and field names against current Kiro CLI docs before writing the file.]`

## Data Models

The envelope is shown above. `cdx_search` rows look like this, with no query values:

```json
{ "timestamp": "2019-03-04T10:22:01Z", "url": "https://demo.example/api/v1/users/{id}?page", "mimetype": "application/json", "status": 200 }
```

## Correctness Properties

### Property 1: The server is passive
*For any* sequence of tool calls with arbitrary arguments (including URLs on arbitrary hosts), every HTTP request
recorded by the mock transport targets `web.archive.org`.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: No query values leave the server
*For any* CDX rows whose URLs carry random query values, none of those values appears in the output of
`cdx_search` or `list_snapshots`.
**Validates: Requirement 1.2**

### Property 3: Every result is enveloped and bounded
*For any* tool and arguments, the result has `untrusted_archived_content: true`, its serialised size is at most
64 KiB, and it holds at most 500 rows, with `truncated` set correctly.
**Validates: Requirements 3.1, 3.2**

### Property 4: The database is never modified
*For any* sequence of `endpoint_history` calls, the SHA-256 of the database file is the same before and after.
**Validates: Requirement 4.1**

## Error Handling

- Invalid arguments: an MCP tool error with a plain message (for example "limit must be 1–500").
- Archive unavailable: a tool error saying the archive asked us to wait. No retry loop beyond `ArchiveClient`'s own.
- Database missing: `endpoint_history` returns an empty list and a note saying "run an exhume in the app first".

## Testing Strategy

- Unit tests call the tool functions directly with a mocked `ArchiveClient` transport and a temporary SQLite file.
- One stdio smoke test starts the server as a subprocess and lists the tools. It uses no network, because the
  transport is in fixture mode.
- Property tests: Properties 1 to 4 in `tests/property/test_mcp_props.py`.
- In use: record in `KIRO_LOG.md` the concrete moments when Kiro used the server while building, for example
  checking real CDX rows while fixing a normaliser edge case. This is write-up item 6.
