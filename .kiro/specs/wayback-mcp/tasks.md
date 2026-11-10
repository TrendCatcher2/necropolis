# Implementation Plan

- [ ] 1. Server skeleton
- [ ] 1.1 Create `mcp/wayback_mcp` (FastMCP, stdio, `python -m wayback_mcp`) with `envelope()` and the caps
  - _Requirements: 3.1, 3.2_
- [ ] 1.2 Write the property test for the envelope and the caps
  - **Property 3: Every result is enveloped and bounded**
  - **Validates: Requirements 3.1, 3.2**

- [ ] 2. Archive tools
- [ ] 2.1 Implement `cdx_search`, `list_snapshots` and `snapshot_text` on the shared `ArchiveClient`, with query
  values stripped through the normaliser and the text-only check
  - _Requirements: 1.1, 1.2, 2.1, 2.3, 3.3_
- [ ] 2.2 Implement `normalise_url`
  - _Requirements: 1.1_
- [ ] 2.3 Write the property tests: the server is passive, and no query values leave it
  - **Property 1: The server is passive**
  - **Property 2: No query values leave the server**
  - **Validates: Requirements 1.2, 2.1, 2.2, 2.3**

- [ ] 3. Results tool
- [ ] 3.1 Implement `endpoint_history` on a read-only SQLite connection
  - _Requirements: 4.1, 4.2_
- [ ] 3.2 Write the property test for read-only access
  - **Property 4: The database is never modified**
  - **Validates: Requirement 4.1**

- [ ] 4. Register with Kiro
- [ ] 4.1 Verify the current `mcp.json` format, write `.kiro/settings/mcp.json`, and confirm that Kiro lists the
  five tools
  - _Requirements: 5.1_
- [ ] 4.2 Add a stdio smoke test
  - _Requirements: 5.1_

- [ ] 5. Gravedigger agent
- [ ] 5.1 Verify the kiro-cli agent format, then write `.kiro/agents/gravedigger.json` (limited tools, sweep prompt,
  no active probes)
  - _Requirements: 5.2, 5.3_
- [ ] 5.2 Do one sweep on the demo domain and commit the report under `reports/` as an example
  - _Requirements: 5.2_

- [ ] 6. Checkpoint: all tests pass; `KIRO_LOG.md` notes how Kiro used the server while building
