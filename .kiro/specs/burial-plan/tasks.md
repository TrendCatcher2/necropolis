# Implementation Plan

- [ ] 1. Safe Markdown helpers
- [ ] 1.1 Implement `md_code`, `md_text` and `slugify`
  - _Requirements: 3.1, 3.4_
- [ ] 1.2 Write the property tests for injection safety and safe names
  - **Property 2: Archived strings cannot inject Markdown**
  - **Property 4: Safe names and paths**
  - **Validates: Requirements 3.1, 3.2, 3.4**

- [ ] 2. Rites and validation
- [ ] 2.1 Implement `Rite`, `default_rites`, user overrides, and the eligibility check with refusal reasons
  - _Requirements: 1.1, 1.2, 1.3_
- [ ] 2.2 Write the property test for eligibility
  - **Property 5: Only examined zombies are buried**
  - **Validates: Requirement 1.3**

- [ ] 3. Templates and generator
- [ ] 3.1 Write the Jinja2 templates for `requirements.md`, `design.md` (with the evidence section) and `tasks.md`,
  plus the optional `api-lifecycle.md` steering file
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.2, 4.2_
- [ ] 3.2 Implement `generate` (sorted, dates from input, no forbidden fields)
  - _Requirements: 2.1, 3.3, 4.3_
- [ ] 3.3 Write the property tests for structure and determinism
  - **Property 1: The plan is a well-formed Kiro spec**
  - **Property 3: Determinism**
  - **Validates: Requirements 2.1, 2.2, 2.3, 4.3**
- [ ] 3.4 Add the golden-file test for the demo-site scenario
  - _Requirements: 2.1–2.4_

- [ ] 4. Delivery
- [ ] 4.1 Implement `to_zip` (fixed timestamps, relative paths) and the API endpoint
  - _Requirements: 4.1, 4.3_

- [ ] 5. Dogfood: run the generated demo plan in Kiro against `demo-site/`, re-probe, and confirm `laid_to_rest`;
  log it in `KIRO_LOG.md`
  - _Requirements: 2.3_
