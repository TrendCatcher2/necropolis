---
inclusion: always
---

# Testing

## Rules

- **No test touches the network.**
  - Python: an autouse fixture in `backend/tests/conftest.py` makes `socket.socket.connect` and
    `socket.getaddrinfo` raise.
  - HTTP goes through httpx `MockTransport`.
  - DNS goes through a fake resolver injected into `netguard` and `ownership`.
- Fixtures are recorded from **our own demo domain** or written by hand for `example.com`, `example.org` and
  `*.test`. Never record a third-party domain.
- Every spec requirement that carries a correctness property in its `design.md` has a property-based test that
  names it:

  ```python
  # Feature: endpoint-normaliser, Property 1: normalisation is idempotent
  # Validates: Req endpoint-normaliser:2.1
  @given(urls())
  def test_normalise_idempotent(u): ...
  ```

- Unit tests cover the examples in the acceptance criteria. Property tests cover the "for any" rules. Both are needed.
- When a property test finds a bug, keep the shrunk example as a `@example(...)` and add a line to `KIRO_LOG.md`
  (what it caught that the unit tests missed). This is write-up material.

## Hypothesis settings

- Profiles in `conftest.py`: `dev` (50 examples), `ci` (300 examples, `deadline=None`). `HYPOTHESIS_PROFILE`
  selects one; the default is `dev`.
- Shared strategies live in `backend/tests/property/strategies.py`: hosts, path segments, id-like segments, URLs,
  CDX rows, probe outcomes, verification states. Reuse them; don't redefine them per test.

## Front end

- Vitest + Testing Library for components. fast-check for pure UI logic: timeline filtering, layout of crypts,
  severity-to-style mapping.
- One Playwright test runs the demo flow against the backend in fixture mode (`NECROPOLIS_FIXTURE_MODE=1`, which
  serves recorded archive data and a fake prober).

## Commands

If uv is missing, install it with `pipx install uv` (done on 10 Nov 2026: uv 0.13.7).

```bash
cd backend && uv run pytest -q                       # all Python tests
cd backend && HYPOTHESIS_PROFILE=ci uv run pytest -q tests/property
cd backend && uv run ruff check . && uv run ruff format --check .
cd backend && uv run mypy --strict necropolis/normaliser     # also netguard, prober, ownership once they exist
cd web && npm test                                   # vitest
cd web && npx playwright test                        # end-to-end demo flow
```

## Definition of done for a task

1. Tests for the task pass, and the whole suite still passes.
2. Any property named in the task exists and references its requirement.
3. ruff and mypy are clean for the touched modules.
4. Nothing in the diff breaks `safety.md`. In particular: no new network call outside `ArchiveClient` or
   `GuardedClient`, and no stored response body.
