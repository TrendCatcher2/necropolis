# Kiro log: Zombie API Necropolis

A daily log of how Kiro was used. It feeds the "How Kiro was used" write-up, so keep entries honest and concrete.
For each entry, say what you asked, what Kiro changed, and what a hook, test or MCP call caught.

## 2026-11-10: first drafts (written outside Kiro)

- The first drafts of all steering docs (`.kiro/steering/*.md`) and the 7 specs (`.kiro/specs/*/`) were written
  with **Claude Code**, from the idea in the hackathon notes. No application code exists yet.
- Next: open the repo in Kiro, review and refine each spec there, and record below what Kiro changed.

## 2026-11-10: demo site (raise-the-dead task 1.1, written outside Kiro)

- Built `demo-site/` (Lantern Lane, a fictional shop) with **Claude Code**: FastAPI, v1/v2 front ends, the zombie
  endpoints from the spec, and 19 tests.
- Building it exposed two spec bugs, both fixed in the specs:
  1. **HEAD responses carry no body**, so the autopsy's body signals (`data_exposed`, `verbose_error`) could never
     fire. The prober now sends one GET when HEAD shows the endpoint is alive (raise-the-dead 5.3, safety rule 4).
  2. **The 30-day "current front end" window** would have counted v1 as current, because v1 and v2 are archived days
     apart. The current front end is now the scripts loaded by the newest archived root page (exhumer 4.7).

## 2026-11-10: hosting (written outside Kiro)

- There is no hosting platform and no domain, so the demo site goes on Render's free tier at
  `<name>.onrender.com`.
  - It sleeps after 15 minutes idle, so wake it before archiving or probing.
  - Ownership is proven with the well-known file instead of DNS.
- `onrender.com` is on the Public Suffix List (private section). `tech.md` now loads tldextract with private
  suffixes. Otherwise every Render app would count as one site.
- The v1 JS now names `/api/v1/debug/trace` as a development leftover. The demo no longer depends on the archive
  saving a 500 page.
- Added `render.yaml` (Blueprint), validated against Render's published JSON schema
  (`https://render.com/schema/render.yaml.json`, 0 errors; a typo control was rejected).
  - Render's docs, and the schema itself, disagree on whether Docker paths are relative to `rootDir` or to the repo
    root. So `rootDir` is unset and the paths start at the repo root, which is the same under both readings.
  - A build filter limits redeploys to `demo-site/` changes.

## 2026-11-10: first archive captures (written outside Kiro)

- The archive needs a logged-in archive.org account for Save Page Now; an anonymous submission was refused.
- Saving `/` also captured the resources it loads: `app.v1.js`, `/api/v1/users/1` and `/api/v1/status`, all at
  20261110101636. `/api/v1/users/2`, which the page never loads, was saved on its own at 20261110102038.
- Playback and the availability API showed the captures within minutes, but the CDX index still listed 0 rows.
  CDX lags behind.
- **Raw `id_` copies keep the original `Content-Encoding` (gzip).** A naive check read the bytes undecoded and
  wrongly reported "not the real content". Exhumer 4.2 now requires decoding, with the 2 MiB cap applied to the
  decoded bytes (which also blocks gzip bombs).

## 2026-11-10: endpoint normaliser built (endpoint-normaliser tasks 1 to 6, written outside Kiro)

- Built `backend/` with **Claude Code**:
  - a uv project (uv 0.13.7, installed with pipx);
  - `necropolis.normaliser`, split into `parse`, `path`, `segments`, `query`, `kind` and `models`;
  - 240 tests: an example table per acceptance criterion, Properties 1 to 7 (plus a bare-path round trip and a
    `*.test` rejection property), and a 25-line regression corpus from the demo site's saved URLs and JS paths.
- The whole suite passes with `HYPOTHESIS_PROFILE=ci`. `mypy --strict` is clean on the normaliser, and ruff is
  clean.
- Building it exposed two spec bugs, both fixed in the specs:
  1. **The key split one endpoint into several.** It held the scheme, the parameter names and a MIME-based kind.
     - The spec's own intro example, `/api/v1/users/123?ref=mail` and `/api/v1/users/9876`, would have been two
       tombstones.
     - So would an old `http` capture and a new `https` one. The CDX index collapses rows by URL key, which ignores
       the scheme.

     The key is now host, port, path template and crypt. Scheme, kind, parameter names and example path come back
     beside it on `Normalised`, and the exhumer's `EndpointRecord` aggregates them.
  2. **`.test` is not on the Public Suffix List** (checked in tldextract 5.4.0's bundled snapshot). Every `*.test`
     host the design's strategies were to generate would have been rejected, so they now drive the rejection
     property instead.
- Gaps filled in the requirements:
  - **Path parameters** are dropped (3.5): `cart.do;jsessionid=…` carried session IDs into the key.
  - **Names that look like values** are dropped (3.4): a bare `?<reset-token>`.
  - **No email for file names** (2.1): `logo@2x.png` matched the email class.
  - **Ports and crypts**: ports 80 and 443 both count as default, and crypts are lowercased.
  - **Example paths**: they are empty for JS paths that hold placeholders.
  - **Backslashes** make an input `unparseable`, because browsers and urllib disagree on the host.
- Property tests:
  - The first implementation passed all seven properties at 50, 300 and 4,000 examples, so they found no bug in it.
    The one first-run failure was a wrong unit-test expectation: `"a" * 64` is a 64-character hex string, so
    Req 3.4 rightly drops it as a value-like name.
  - A mutation check then tested the tests: 17 bugs, planted one at a time in a scratch copy. P1 missed "dot segments
    resolved before percent-decoding" until its generator also spelled dot segments as `%2E`. P3 now spells
    unreserved characters as `%XX`.
  - Every planted bug that changes behaviour is now caught. One planted bug changed nothing, because the static and
    script extension lists don't overlap.
- Purity: tldextract and idna load data files on first use, so `parse.py` loads them at import. Property 7 fails if
  the clock, `random`, the environment, a socket or a file is touched during `normalise()`, or if a module is
  imported.
- The token heuristic's cost was measured on 200,000 random base64url tokens: 3.0% of 21-character tokens and 0.7% of
  32-character tokens stay literal. The design records this.

<!-- Entry template
## YYYY-MM-DD: <spec or task>
- Surface: IDE / CLI / Crew
- Asked:
- Kiro changed:
- Caught by (hook / property test / MCP):
- Time saved or lesson:
-->
