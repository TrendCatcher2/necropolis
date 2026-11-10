# Implementation Plan

- [x] 1. Set up the backend package and test harness
  - Create the `backend/` uv project, `necropolis` package, ruff and mypy config, pytest, Hypothesis profiles, and
    the no-network autouse fixture (`testing.md`)
  - Create `tests/property/strategies.py` with host, segment and URL strategies
  - _Requirements: 5.1_

- [x] 2. Parse and canonicalise
- [x] 2.1 Implement `parse.py`: scheme and host handling, IDNA, default ports, offline public-suffix check, and
  rejection reasons
  - _Requirements: 1.1, 1.2, 1.6_
- [x] 2.2 Implement path canonicalisation: decode unreserved characters, then remove dot segments, merge slashes,
  and handle the trailing slash
  - _Requirements: 1.3, 1.4, 1.5_
- [x] 2.3 Write the property test for total rejection
  - **Property 6: Rejection is total and never throws**
  - **Validates: Requirement 1.6**

- [x] 3. Template segments
- [x] 3.1 Implement the ordered segment classifiers and the placeholder fixed points
  - _Requirements: 2.1, 2.2_
- [x] 3.2 Implement the conservative token heuristic with its built-in word list
  - _Requirements: 2.1_
- [x] 3.3 Write the property test for ID collapse
  - **Property 2: ID values collapse to one template**
  - **Validates: Requirements 2.3, 2.1**
- [x] 3.4 Write the property tests for literal survival and version segments
  - **Property 3: Literal segments survive**
  - **Property 5: Version segments are never templated**
  - **Validates: Requirements 1.4, 2.1, 2.2, 4.1**

- [x] 4. Query names, crypt and kind
- [x] 4.1 Implement `query.py`: names only, validated, sorted and unique
  - _Requirements: 3.1, 3.2, 3.3_
- [x] 4.2 Implement `crypt_of` and `kind.py`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] 4.3 Write the property test for query values
  - **Property 4: No query value ever appears in output**
  - **Validates: Requirements 3.1, 3.2**

- [x] 5. Public API, `render` and purity
- [x] 5.1 Implement `normalise()` and `render()` and the models `EndpointKey`, `Normalised` and `Rejected`
  - _Requirements: 2.4, 5.3_
- [x] 5.2 Write the property tests for idempotence and purity
  - **Property 1: Normalisation is idempotent**
  - **Property 7: Purity**
  - **Validates: Requirements 5.1, 5.2, 5.3, 1.3**
- [x] 5.3 Add the regression corpus test (`normaliser_corpus.jsonl`)
  - _Requirements: 1.1–4.5_

- [x] 6. Checkpoint: the whole suite passes with `HYPOTHESIS_PROFILE=ci`; mypy is strict-clean on `normaliser`; add
  a `KIRO_LOG.md` entry for anything the property tests caught
