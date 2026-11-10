# Implementation Plan

- [ ] 1. ArchiveClient (passive transport)
- [ ] 1.1 Implement `ArchiveClient` with the fixed base URL, a host check in the transport, `User-Agent`, rate
  limit, and retry/backoff with `Retry-After`
  - _Requirements: 3.1, 3.2, 3.4_
- [ ] 1.2 Implement the SQLite cache (`archive_cache`, 7-day TTL) and the migrations scaffold
  - _Requirements: 3.3_
- [ ] 1.3 Write the recording script `scripts/record_fixtures.py`, run it on the demo domain by hand, and commit
  the fixtures
  - _Requirements: 2.1_

- [ ] 2. Target validation and CDX paging
- [ ] 2.1 Implement `validate_target` (public suffix, rejections, scope)
  - _Requirements: 1.1, 1.2, 1.3_
- [ ] 2.2 Implement `cdx_captures`: query building, JSON parsing, resume keys, the cap, and malformed-row counting
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
- [ ] 2.3 Write the property test for paging
  - **Property 2: Paging collects every row exactly once**
  - **Validates: Requirements 2.2, 2.3**

- [ ] 3. JS mining
- [ ] 3.1 Implement `pick_scripts`
  - _Requirements: 4.1_
- [ ] 3.2 Implement `mine_js` with bounded regexes, `${}` → `{id}`, and the same-site filter
  - _Requirements: 4.3, 4.4, 4.5, 4.6_
- [ ] 3.3 Implement snapshot fetching (`id_`, 2 MiB cap)
  - _Requirements: 4.2_
- [ ] 3.4 Write the property tests for the same-site rule and the script limits, plus the regex performance test
  - **Property 5: JS mining stays on the target's site**
  - **Property 6: Script limits hold**
  - **Validates: Requirements 4.1, 4.2, 4.5**

- [ ] 4. Aggregation and dating
- [ ] 4.1 Implement pure `aggregate(rows, refs, now)`: dating, example paths, the current front end, and zombie
  candidates (including `unknown`)
  - _Requirements: 5.1, 5.2, 5.3_
- [ ] 4.2 Write the property tests for dating
  - **Property 3: Dating is order-independent and correct**
  - **Property 4: More history never shrinks the inventory**
  - **Validates: Requirement 5.1**

- [ ] 5. Job runner
- [ ] 5.1 Implement `run_exhume`: phases, the JobBus progress events, partial/empty/cancelled statuses, and saving
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
- [ ] 5.2 Write the property test that the exhumer is passive (recording mock transport, generated hostile data)
  - **Property 1: Exhumer is passive**
  - **Validates: Requirement 3.4; safety rule 1**
- [ ] 5.3 Write an integration test: a full run on the recorded demo-domain fixtures, with the expected zombie
  candidates asserted
  - _Requirements: 2.1–6.3_

- [ ] 6. Checkpoint: all tests pass; one live run on the demo domain (by hand) matches the recorded fixtures; log
  in `KIRO_LOG.md`
