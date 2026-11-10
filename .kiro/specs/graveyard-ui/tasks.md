# Implementation Plan

- [ ] 1. API foundation
- [ ] 1.1 Set up the FastAPI app: settings, error format, workspace cookie, CSRF guard, security headers, static
  serving, `/api/health`
  - _Requirements: 10.1, 10.2, 10.3_
- [ ] 1.2 Implement the JobBus → SSE endpoint, job state and cancel
  - _Requirements: 2.1, 2.2, 2.3_
- [ ] 1.3 Implement the exhume, graveyard, ownership, probe, re-probe, burial-plan, report and demo routes, all
  workspace-scoped
  - _Requirements: 10.1, 10.4, 1.3, 8.1, 8.2_
- [ ] 1.4 Write the property tests for cross-site refusal and workspace isolation
  - **Property 5: Cross-site requests are refused**
  - **Property 6: Workspaces are isolated**
  - **Validates: Requirements 10.3, 10.4**

- [ ] 2. Front-end foundation
- [ ] 2.1 Scaffold `web/` (Vite, React, TS, eslint, Vitest, fast-check, Playwright); add `tokens.css`, the palette
  with AA checks, and the font with its credit
  - _Requirements: 9.3_
- [ ] 2.2 Implement `api/client.ts` (headers, typed responses, SSE with reconnect)
  - _Requirements: 2.2, 10.3_

- [ ] 3. Pure graveyard logic
- [ ] 3.1 Implement `layout.ts`, `timeline.ts` and `style.ts`
  - _Requirements: 3.1, 3.2, 3.4, 4.2_
- [ ] 3.2 Write the property tests for the timeline, layout and severity style
  - **Property 1: The timeline shows what existed**
  - **Property 2: Every tombstone has exactly one plot**
  - **Property 3: Severity is never colour alone**
  - **Validates: Requirements 3.1, 3.2, 3.4, 4.2, 9.3**

- [ ] 4. Views
- [ ] 4.1 Landing (pitch, input, scope, safety sentence, demo button, inline errors)
  - _Requirements: 1.1, 1.2, 1.3_
- [ ] 4.2 Graveyard map: crypts, tombstones, legend, clustering, filters, search, live fill from SSE, and the
  empty/partial/cancelled states
  - _Requirements: 2.1, 2.3, 3.1–3.5_
- [ ] 4.3 Timeline slider and "Replay the years", with reduced motion
  - _Requirements: 4.1, 4.2, 4.3_
- [ ] 4.4 Detail drawer: facts, archive links, signals, cause of death, state-dependent actions
  - _Requirements: 5.1, 5.2, 5.3_
- [ ] 4.5 Write the property test that archive strings render as text
  - **Property 4: Archive strings render as text**
  - **Validates: Requirement 9.4**
- [ ] 4.6 Ownership wizard and the proofs list
  - _Requirements: 6.1, 6.2, 6.3_
- [ ] 4.7 Raise the dead and re-probe: the rising and lay-to-rest transitions, refusal explanations
  - _Requirements: 7.1, 7.2, 7.3_
- [ ] 4.8 Burial builder (select, rites, preview, zip, copy) and report export
  - _Requirements: 8.1, 8.2_
- [ ] 4.9 Table view, keyboard operation, accessible names
  - _Requirements: 9.1, 9.2_

- [ ] 5. End to end
- [ ] 5.1 Playwright demo-flow test in fixture mode, plus the axe checks on every view
  - _Requirements: 1.3, 2.1–9.4_
- [ ] 5.2 Dockerfile (build `web/`, serve from FastAPI) and a deploy with conservative probe limits (`safety.md` rule 4)
  - _Requirements: 10.1_

- [ ] 6. Checkpoint: feature freeze (Wed 2 Dec). A clean-browser run of the live URL works; record screenshots for
  `docs/screenshots/`; add a `KIRO_LOG.md` entry
