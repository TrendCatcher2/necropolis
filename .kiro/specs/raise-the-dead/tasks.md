# Implementation Plan

- [ ] 1. Demo site (do this first: the archive needs time to hold history)
- [ ] 1.1 Build `demo-site/`: v2 front end + v2 API, v1 API with the fake-data zombie, a debug endpoint with a fake
  stack trace, and a v1 endpoint returning 410
  - _Requirements: 8.1, 8.2_
- [ ] 1.2 Deploy it on our own domain with a v1 front end first; archive the pages and the JS with Save Page Now
  (by hand); then switch the front end to v2 only and keep v1 running
  - _Requirements: 8.3_

- [ ] 2. Network guard
- [ ] 2.1 Implement `is_blocked_ip` (all ranges, IPv4-mapped, 6to4, CGNAT)
  - _Requirements: 4.1_
- [ ] 2.2 Implement `GuardedClient`: injected resolver, pinned transport with SNI and Host, no auto-redirects,
  timeout, and the byte cap
  - _Requirements: 4.2, 4.3, 4.4_
- [ ] 2.3 Write the property test for blocked addresses
  - **Property 3: Blocked addresses are never contacted**
  - **Validates: Requirement 4.1**

- [ ] 3. Ownership
- [ ] 3.1 Implement challenges (128-bit tokens, `SecretStr`, constant-time compare, 72 h expiry), the SQLite tables, and the never-log rule
  - _Requirements: 1.1, 1.2, 1.3_
- [ ] 3.2 Implement `verify_dns`, `verify_file` (sealed `WellKnownTarget`), the failure messages, freshness,
  re-verification and revoke
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
- [ ] 3.3 Write the property test for scope matching
  - **Property 2: Scope matching is label-exact**
  - **Validates: Requirements 2.1, 2.2, 3.2**

- [ ] 4. Probe gate
- [ ] 4.1 Implement `ProbeGate.authorize`, the sealed `AuthorizedTarget`, `Refusal` reasons and the kill switch
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [ ] 4.2 Write the property test: no request ever reaches an unverified host
  - **Property 1: No request ever reaches an unverified host**
  - **Validates: Requirements 3.1, 3.2, 3.3, 2.4; safety rule 2**

- [ ] 5. Runner and classification
- [ ] 5.1 Implement `classify` with the outcome table
  - _Requirements: 6.1_
- [ ] 5.2 Implement `plan_probes` (example paths only, zombie candidates first, cap 500, `not_probeable`)
  - _Requirements: 5.1_
- [ ] 5.3 Implement `run_probes`:
  - HEAD, then GET on 405/501
  - per-host token bucket, at most 2 in flight
  - redirects re-gated, at most 3 hops
  - 429 pause and single retry
  - 64 KiB read → `autopsy.body_signals` → discard
  - minimal `ProbeResult`, run limiter and cancel
  - _Requirements: 5.2–5.7, 6.2, 6.3, 6.4_
- [ ] 5.4 Write the property tests for safe requests, limits, bodies, classification and redirects
  - **Property 4: Only safe requests are sent**
  - **Property 5: Limits hold**
  - **Property 6: Bodies are never kept**
  - **Property 7: Classification is total and deterministic**
  - **Property 8: Redirects are re-gated**
  - **Validates: Requirements 5.1–5.5, 6.1–6.4**

- [ ] 6. Re-probe
- [ ] 6.1 Implement re-probe for one endpoint or a burial plan's endpoints, with the `laid_to_rest` comparison
  - _Requirements: 7.1, 7.2_

- [ ] 7. Checkpoint: all tests pass (`HYPOTHESIS_PROFILE=ci`); mypy strict on `netguard`, `ownership` and
  `prober`; manual run on the real demo domain recorded in `KIRO_LOG.md`
