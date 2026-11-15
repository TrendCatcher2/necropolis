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

## 2026-11-15: exhumer, first pass (state found and committed)
- Surface: **Claude Code**, not Kiro. Kiro isn't installed on this machine yet.
- Found uncommitted from an earlier session:
  - the archive layer `backend/necropolis/archive/` (client, cache, CDX, decode, replay, timestamps) plus SQLite
    migrations;
  - the exhumer modules `backend/necropolis/exhumer/` (target, miner, captures, scripts, aggregate, store, run);
  - a job bus (`jobs.py`) and settings;
  - normaliser helpers `registrable_domain`, `is_public_suffix` and `redact_url`.
- Verified today: 484 tests pass (`HYPOTHESIS_PROFILE=ci`). Fixed 12 ruff findings and 2 `mypy --strict` errors
  (asserts replaced by explicit errors, one list/tuple variance fix in the client's `params`).
- Has unit tests: archive client, cache, CDX, decode, `validate_target`, `mine_js`.
- **No tests yet:** `aggregate`, `captures`, `scripts`, `store`, `run`. The exhumer `tasks.md` boxes are left
  unticked until each task is checked against its acceptance criteria. The paging, same-site, dating and passivity
  property tests (2.3, 3.4, 4.2, 5.2) and the fixture-based integration test (1.3, 5.3) are still to write.

## 2026-11-15: exhumer spec review (first Kiro session)
- Surface: **Kiro IDE 1.4.154** on Windows, built-in **Plan** agent, Supervised mode, model Auto. No files changed.
- Asked: review `.kiro/specs/exhumer/` against `backend/necropolis/exhumer/` and `archive/`, and give each task a
  status of done, partly done or missing.
- Kiro found:
  - done: 1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 3.3, 4.1, 5.1;
  - missing: 1.3 (`scripts/record_fixtures.py`, `tests/fixtures/archive/`), the property tests 2.3, 3.4, 4.2 and
    5.2 (no `tests/property/test_exhumer_props.py`), the integration test 5.3 and checkpoint 6.
- Its top gaps:
  1. none of the exhumer's Hypothesis properties are written;
  2. the fixture recorder is missing, even though `RecordingTransport` and `ReplayTransport` exist;
  3. there is no integration test of `run_exhume`;
  4. there is no property test that the exhumer is passive (Prop 1, the safety one);
  5. `aggregate` has no tests for Props 3 and 4.
- Cross-checked in a shell: every missing file it named is in fact missing. One correction: 4.1 and 5.1 are
  written but **unverified**, because no test exercises them yet, so their boxes stay unticked.
- Lesson: a read-only Plan pass over spec plus code gave a task-by-task gap list in one prompt. That list is the
  build order for the next sessions: Prop 1 first, then the fixtures and integration test, then the dating props.

## 2026-11-15: exhumer task 5.2, passive property test (built in Kiro)
- Surface: **Kiro IDE** on Windows, **Start task** on `tasks.md` 5.2, Supervised mode. Kiro estimated 3.01 credits
  and 2 min 29 s.
- Kiro wrote `backend/tests/property/test_exhumer_props.py`:
  - one Hypothesis property: hostile JS bodies with `fetch`, `axios` and template-literal calls to random non-archive
    hosts, run through `run_exhume` on a recording transport, asserting every request goes to `web.archive.org`;
  - unit tests of the `_ArchiveOnly` guard: 6 refused URLs (`http://`, `web.archive.org.evil.com`, `127.0.0.1`,
    `archive.org` and more) and 1 allowed.
- Kiro also ticked 5.2 in `tasks.md` and created `tasks.meta.json`, its PBT status record.
- Checked outside Kiro by planting bugs in a scratch copy and running the property:

  | Planted bug | Property |
  |---|---|
  | none | passes |
  | request to evil.com via the archive client | **fails** (the guard raises) |
  | the same request with the guard disabled | **fails** (the assertion catches it) |
  | probing the target's own mined endpoint, guard disabled | **fails** |
  | request through a fresh `httpx` client | **fails** (the conftest network block) |
  | leak attempt caught and ignored, guard on | passes. No request left; the guard stopped it |
  | the same, guard off | **fails** |

  A probe showed the setup does reach JS mining: the hostile script is fetched and the run ends `complete`.
- Follow-ups for Kiro:
  - ruff reports 5 small findings in the new file (2 unused imports, 2 en dashes, 1 `and`/`or` precedence);
  - `max_examples=50` is hard-coded, which overrides the `ci` profile's 300.

## 2026-11-15: first agent hook, ruff on save
- Surface: Kiro IDE, Agent Hooks UI. File: `.kiro/hooks/ruff-lint-on-save.json`.
- Trigger `PostFileSave`, matcher `backend/.*\.py$`, action type **command**: `uv run --directory backend ruff check --fix`.
- First draft: the action was **Ask Kiro** with a one-off prompt pasted into the instructions. That would spend
  agent credits on every save. Switched to a plain command, which runs for free.
- Lesson: hooks that only lint should be command hooks; save "Ask Kiro" hooks for work that needs judgement. The
  read-only **Plan** agent answered the fix request with a plan, not an edit, and it listed only 2 of the 5 ruff
  findings, so run ruff itself rather than trusting the plan's count.

## 2026-11-15: lint fixes in the exhumer props (Kiro agent + hook)
- Surface: Kiro IDE, default agent, Supervised mode. Commits `f73198b` and `b19ed85`.
- Asked for 2 fixes. Kiro ran ruff itself, found all 5 findings and fixed them:
  - 2 unused imports;
  - 2 en dashes;
  - the `and`/`or` precedence;
  - it also removed the hard-coded `max_examples=50`, so the `ci` profile's 300 examples now apply.
- What went wrong on the way:
  - a context-gathering sub-agent returned an **invented** version of the file. Kiro noticed it didn't match its
    own earlier reads and discarded it;
  - writing the file through PowerShell 5.1 added a UTF-8 BOM.
- Checked outside Kiro:
  - the diff touches only those lines;
  - BOM removed;
  - `.gitattributes` added (`eol=lf`) so Windows and Kali commits keep LF;
  - ruff, `mypy --strict` and all **492** tests pass;
  - the planted "probe the target, guard off" bug still fails the property.
- Lesson: let ruff (or the hook) produce the findings list rather than trusting a plan's count, and check a
  sub-agent's file contents against the real file before acting on them.

<!-- Entry template
## YYYY-MM-DD: <spec or task>
- Surface: IDE / CLI / Crew
- Asked:
- Kiro changed:
- Caught by (hook / property test / MCP):
- Time saved or lesson:
-->
