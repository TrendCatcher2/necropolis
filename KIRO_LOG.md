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

<!-- Entry template
## YYYY-MM-DD: <spec or task>
- Surface: IDE / CLI / Crew
- Asked:
- Kiro changed:
- Caught by (hook / property test / MCP):
- Time saved or lesson:
-->
