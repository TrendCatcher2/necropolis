---
inclusion: always
---

# Product: Zombie API Necropolis

## One line

The web forgot your old APIs. The Wayback Machine didn't, and neither do attackers. Necropolis digs up every
endpoint your site has ever exposed, checks which ones still answer, and gives each zombie a tombstone, an autopsy
and a burial plan.

## The problem

Zombie and shadow APIs are old versions and endpoints that were removed from the front end but still answer on the
server. They are **OWASP API Security Top 10 2023, API9: Improper Inventory Management**. Teams have no list of what
they used to expose. Attackers and bug hunters rebuild that list from public web archives, so they find these
endpoints first.

## Who it is for

- **AppSec engineers and startup CTOs** who want to know what their domain still exposes from past releases.
- **Bug bounty programme owners** who want to find zombies before hunters report them.
- Not for testing other people's sites. Active checks only run on domains the user has proven they own.

## The core flow (the demo shows this end to end)

1. **Exhume** (passive, any domain): query the Wayback Machine CDX API for every archived URL of the domain, mine
   archived JavaScript bundles for API paths, normalise them into endpoint templates, and date each one with first
   seen, last seen, and last seen in the front end.
2. **Prove ownership**: a DNS TXT record (covers the domain and its subdomains) or a file under `/.well-known/`
   (covers that exact host only).
3. **Raise the dead** (active, verified scope only): one safe request per endpoint. HEAD, then GET only if HEAD is not
   allowed. No request body, no credentials, rate limited. Each endpoint is classified as gone, guarded, open,
   redirected, erroring or unreachable.
4. **Autopsy**: deterministic risk signals. The endpoint is an older version than the live one, has no auth where its
   siblings need it, returns verbose errors, sits on a debug or admin path, or was removed from the front end but
   still answers. Each zombie gets a plain-language cause of death.
5. **Burial plan**: generate a **Kiro spec** (requirements, design, tasks) to retire, protect or redirect each zombie,
   which Kiro then implements in the user's own repo. Then **re-probe**: the zombie lies down.

## Vocabulary: every spooky word has a plain meaning

The theme must help the function, never hide it. The UI shows the plain label next to, or as a tooltip on, every
themed term.

| Themed term | Plain meaning |
|---|---|
| Exhume | Passive discovery from web archives |
| Crypt | One API version (`v1`, `v2`, unversioned) |
| Tombstone | One endpoint template, such as `/api/v1/users/{id}` |
| Raise the dead | Active check of verified endpoints |
| Zombie | Missing from the current front end, but still answering |
| Autopsy | Risk signals plus an explanation |
| Burial plan | A generated Kiro spec to fix it |

Severity ("how far it has risen"), in order:

| Level | Plain label | Rule summary (exact rules in the `autopsy` spec) |
|---|---|---|
| Buried | Gone | 404/410, or unreachable |
| Stirring | Alive, auth required | 401/403, or a redirect to login |
| Risen | Alive and open | 2xx with no risk signal |
| Rampaging | Alive, open and risky | 2xx plus at least one risk signal |

An endpoint that has not been probed (no proof, or no concrete example path) has no severity. It shows as
"Unexamined" in grey.

## Scope

In scope:
- Exhume, ownership proof, raise the dead, autopsy, burial plan, re-probe.
- Graveyard UI with a timeline.
- `wayback-mcp`, a custom MCP server.
- JSON and Markdown export.

Out of scope, on purpose:
- Exploitation, fuzzing and payloads.
- Authenticated testing with user credentials.
- Brute-forcing paths that are not in the archive.
- Probing any domain the user has not verified.
- Storing response bodies.

## Hackathon constraints (Kiroween 2026, Resurrection category)

- **All code is new**, written from 30 Oct 2026. No code is copied from earlier projects (Bug Hunter OS, TrendSAST,
  Break The Bot). Any third-party code is a declared dependency, never pasted in.
- MIT licence at the repo root, shown in the GitHub About box. `/.kiro` lives at the repo root and is **never
  gitignored**.
- Submission deadline: Fri 4 Dec 2026, 2:00 PM PT. The demo video is under 3 minutes and uses only the user's own
  demo domain.
- The five judging criteria have equal weight: Impact, Technological Implementation, Design, Innovation and
  Presentation. "Design" means one polished end-to-end flow with empty, loading and error states done, not a
  proof of concept.

## Product principles

1. **Passive by default, active by proof.** No proof, no packet to the target.
2. **Evidence over guesses.** Every claim on a tombstone links to a capture timestamp or a probe result.
3. **Never store what it found.** Probe results keep the status, headers we need and signal names, never response
   bodies.
4. **The fix is part of the product.** A finding ends with a Kiro spec and a re-probe, not just a red badge.
