# Implementation Plan

- [ ] 1. Body signals
- [ ] 1.1 Implement `body_signals` with the bounded detectors, the JSON key walk (prefix-tolerant, depth 5) and the
  fixed vocabulary
  - _Requirements: 1.1, 1.2, 1.3, 1.4_
- [ ] 1.2 Add the fake error-page and JSON fixtures (no real data) with their expected signals
  - _Requirements: 1.1, 1.2_
- [ ] 1.3 Write the property test for `body_signals`
  - **Property 5: body_signals is total, bounded and leak-free**
  - **Validates: Requirements 1.1, 1.3, 1.4**

- [ ] 2. Siblings and signals
- [ ] 2.1 Implement `resource_path` and `sibling_index`
  - _Requirements: 2.1_
- [ ] 2.2 Implement `signals_for` (context vs risk)
  - _Requirements: 2.1, 2.2_
- [ ] 2.3 Write the property test for the auth-asymmetry direction
  - **Property 6: Auth asymmetry points one way**
  - **Validates: Requirement 2.1**

- [ ] 3. Severity and score
- [ ] 3.1 Implement `severity` and `score` from the tables
  - _Requirements: 3.1–3.6_
- [ ] 3.2 Write the property tests for severity
  - **Property 1: More risk never means less severity**
  - **Property 2: The buried stay buried**
  - **Property 3: Unprobed means unexamined**
  - **Validates: Requirements 3.1, 3.2, 3.4, 3.5**

- [ ] 4. Cause of death and `examine`
- [ ] 4.1 Implement the sentence templates and `cause_of_death`
  - _Requirements: 4.1, 4.2, 4.3_
- [ ] 4.2 Implement `examine`, and wire it to run after probe runs and re-probes
  - _Requirements: 5.1, 5.2_
- [ ] 4.3 Write the property tests for the explanation and order independence
  - **Property 4: The explanation matches the evidence**
  - **Property 7: Order independence**
  - **Validates: Requirements 4.1, 4.2, 5.2**
- [ ] 4.4 Write the demo-scenario unit test (v1 users zombie → `RAMPAGING` with the expected signals and text)
  - _Requirements: 2.1, 3.5, 4.1_

- [ ] 5. Checkpoint: all tests pass; `[VERIFY]` marker strings checked; `KIRO_LOG.md` entry
