---
inclusion: always
---

# Tech stack and conventions

Use the latest stable release of each library at project start and pin it in the lockfiles (`uv.lock`,
`package-lock.json`). Do not add a dependency without a reason in the design doc of the spec that needs it.

## Backend: Python

- **Python 3.12+**, managed with **uv**. Package name: `necropolis` (folder `backend/necropolis/`).
- **FastAPI** for the HTTP API. **Server-Sent Events** stream exhume and probe progress to the UI.
- **httpx** (async) for every outbound request, always through one of two clients:
  - `ArchiveClient` (`necropolis.archive`) talks to `web.archive.org` only. Its base URL is fixed, and it refuses
    any other host.
  - `GuardedClient` (`necropolis.netguard`) is used only by ownership and the prober. It applies `safety.md` rule 3:
    resolve, check, pin, no auto-redirects.
  - Never call `httpx.get`, `requests`, `urllib` or `socket` anywhere else. The safety hook flags this.
- **dnspython** for TXT lookups and resolution in the network guard.
- **Pydantic v2** models for everything that crosses a module boundary or goes over the API.
- **SQLite** (stdlib `sqlite3`, WAL mode) for the archive cache, exhume results, proofs and probe history. One file:
  `data/necropolis.db`. Migrations are numbered SQL files under `backend/necropolis/db/migrations/`.
- Public suffix handling: **tldextract** with its bundled snapshot, and live list fetching **disabled**
  (`suffix_list_urls=()`), so it makes no network calls at runtime.
- Quality: **ruff** (lint and format), **mypy --strict** on `netguard`, `prober`, `ownership` and `normaliser`;
  plain mypy elsewhere.
- Tests: **pytest**, **Hypothesis** (property-based), **pytest-asyncio**, and httpx `MockTransport`. See
  `testing.md`.

## MCP server

- `mcp/wayback_mcp/`: a Python MCP server (official `mcp` SDK, FastMCP style, stdio transport).
- It imports `necropolis.archive` and `necropolis.normaliser`, so it shares the same cache, rate limit and
  `User-Agent`. It never imports the prober, ownership or netguard.
- Registered for Kiro in `.kiro/settings/mcp.json` once it runs.

## Front end

- **React + TypeScript + Vite** in `web/`. State: React state plus one small store. No Redux.
- The graveyard is **SVG** up to 500 tombstones. Above that, crypts collapse into clusters. No canvas, no WebGL, no
  game engine.
- Styling: CSS modules plus CSS custom properties for the palette. One spooky display font for headings only
  (self-hosted, with an OFL or similarly permissive licence, credited in `docs/CREDITS.md`). Body text uses the
  system UI font for readability.
- Animation: CSS only, and switched off when `prefers-reduced-motion` is set.
- Tests: **Vitest**, **fast-check** (property-based), Testing Library. **Playwright** for one end-to-end run of the
  demo flow.
- Lint: eslint, `tsc --noEmit`.

## API conventions

- JSON only, under `/api/`. Errors use `{ "error": { "code": "snake_case", "message": "plain words" } }` with the
  right HTTP status.
- Long jobs (exhume, probe run): `POST` starts a job and returns `{job_id}`, `GET /api/jobs/{id}/events` streams SSE,
  and `GET /api/jobs/{id}` returns the final state.
- Times are UTC ISO 8601. Wayback timestamps (`YYYYMMDDhhmmss`) are converted at the archive boundary and never leak
  further.

## Config

- All settings come from environment variables with safe defaults, read in one place (`necropolis.settings`,
  pydantic-settings):
  - `NECROPOLIS_PROBES_DISABLED`
  - `NECROPOLIS_DB_PATH`
  - `NECROPOLIS_PUBLIC_URL`
  - `NECROPOLIS_ARCHIVE_RPS`
  - `NECROPOLIS_PROBE_RPS`
- No secrets are needed for the core app. If one is ever added, it comes from the environment, never from code, and
  `.env` stays gitignored.

## Deploy

- One Docker image: FastAPI serves the built `web/` assets. A volume holds `data/`.
- Host: decided at deploy time. It needs an HTTPS URL and outbound DNS and HTTP(S).
- The public demo deployment sets the probe limits low and can set `NECROPOLIS_PROBES_DISABLED=1`, falling back to
  the recorded demo.

## External services

| Service | Use | Notes |
|---|---|---|
| Wayback CDX API `https://web.archive.org/cdx/search/cdx` | List archived URLs for a domain | Params used: `url`, `matchType`, `output=json`, `fl=timestamp,original,mimetype,statuscode`, `collapse=urlkey`, `from`, `to`, `limit`, `showResumeKey`, `resumeKey`. Paginate with `resumeKey`. |
| Wayback raw snapshot `https://web.archive.org/web/{timestamp}id_/{url}` | Fetch archived JS as originally served | The `id_` flag returns the original bytes without Wayback's rewriting |
| Save Page Now `https://web.archive.org/save/` | Demo prep only, done by hand in a browser | Not called by the app |

`[VERIFY: CDX parameter behaviour (matchType=domain, collapse, resumeKey) against the live API docs on day 1; record
any differences here.]`
`[VERIFY: Internet Archive rate-limit guidance and terms (link + date).]`
