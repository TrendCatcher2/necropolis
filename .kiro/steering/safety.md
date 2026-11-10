---
inclusion: always
---

# Safety rules (non-negotiable)

Necropolis is a security tool that makes network requests based on data from the internet. These rules apply to
every spec, every task, every hook and every line of code. If a task conflicts with them, stop and say so: do not
work around them.

## 1. Passive vs active

- **Passive** means requests only to `web.archive.org` (CDX API and raw snapshots). This is allowed for any domain.
- **Active** means any request to the target's own hosts: probes, re-probes and the ownership-file check. It is
  allowed only through the probe gate (rule 2).
- The exhumer, the JS miner, the normaliser, the autopsy, the burial-plan generator and `wayback-mcp` **never** open a
  connection to a target host. Only `necropolis.ownership` and `necropolis.prober` may do that.

## 2. The probe gate is the only way out

- `necropolis.prober.gate.ProbeGate` is the single place that decides whether a URL may be contacted. It returns an
  `AuthorizedTarget` (a frozen type that only the gate can construct), or a refusal with a reason.
- The probe runner accepts `AuthorizedTarget` objects only, never strings or plain URLs. Do not add an overload, a
  flag, an env var or a "debug" path that skips the gate.
- The gate allows a host only if it has a **current ownership proof**:
  - A DNS TXT proof on a domain covers that domain and all its subdomains.
  - A file proof covers that exact host only (scheme and port included).
  - A proof is current if it was verified less than 24 hours ago. Older proofs are re-checked before a run.
- Kill switch: when `NECROPOLIS_PROBES_DISABLED=1` is set, the gate refuses everything. The hosted demo can turn
  active checks off in one step.

## 3. Network guard (SSRF): we fetch URLs that came from the internet

- Resolve the host first. Refuse the request if **any** resolved address is loopback, private (RFC 1918),
  link-local (including `169.254.169.254`), carrier-grade NAT, multicast, reserved, or unspecified, for both IPv4 and
  IPv6 (including IPv4-mapped IPv6).
- Connect to the address that was checked (pin it), so a DNS rebinding between check and connect cannot redirect the
  request.
- Schemes: `http` and `https` only. Ports: 80 and 443 only, unless the proof is a file proof on that exact port.
- Redirects are not followed automatically. A redirect is recorded as a result. The runner may follow at most 3 hops,
  and only when each hop passes the gate again.
- The same guard protects the ownership-file fetch.

## 4. What a probe may send

- Method: `HEAD`. Use `GET` only when `HEAD` returns 405 or 501. Never `POST`, `PUT`, `PATCH`, `DELETE` or
  `OPTIONS`.
- No request body. No cookies. No `Authorization` header. No custom headers except `User-Agent` and `Accept`.
- Path only: the query string is dropped. Templated segments are filled with the most recent value seen in the
  archive for that endpoint, never with generated or guessed values.
- `User-Agent: Necropolis/<version> (+<public repo URL>; owner-verified scan)`. Never put the user's email or any
  personal data in headers.
- Limits:
  - Timeout: 10 s.
  - Rate: 1 request per second per host by default, user-adjustable down to 0.2 and never above 2.
  - Concurrency: at most 2 per host.
  - At most 500 probes per run.
  - At most 3 runs per domain per hour.

## 5. What we keep

- **Never store response bodies.** Read at most 64 KiB in memory, compute signals (rule names only), then discard.
- Store only: status code, the `Content-Type`, `Content-Length`, `Location` (path only for same-site redirects),
  `WWW-Authenticate` scheme name, timing, signal names, and a SHA-256 of the first 64 KiB so the tool can show
  "unchanged since last probe".
- **Never display or store query-string values** from archived URLs. They can hold tokens (reset links, API keys).
  Keep parameter names only.
- Logs never contain response content, query values, tokens or ownership challenge secrets.

## 6. Archive etiquette (Internet Archive)

- Identify the client with the same descriptive `User-Agent`.
- Cache CDX results and snapshots (SQLite, 7-day TTL).
- Make one request at a time, start at no more than 1 request per second, and back off exponentially on 429/503,
  honouring `Retry-After`.
- `[VERIFY: current Internet Archive guidance on CDX/Wayback API rate limits and terms of use; record the link and
  date in tech.md before the first live run]`.
- The demo video and tests run from **recorded fixtures of our own demo domain**, so live archive load stays near
  zero.

## 7. Treat archived content as hostile

- Archived pages and JS are untrusted input. Parse them as text with size limits (2 MiB per file, 50 JS files per
  run). Never execute them, never render them as HTML, and never `eval` them.
- Everything shown in the UI or written into a generated Kiro spec is escaped for its context: HTML, Markdown, code
  spans and YAML. An archived path is data, never markup or instructions.
- `wayback-mcp` marks every tool result as *untrusted archived content*, so an agent reading it does not follow
  instructions planted in old pages (indirect prompt injection).

## 8. Demo and docs

- The video, screenshots, tests and docs use **only our own demo domain**. Never show or probe a third-party domain.
- The landing page and README say plainly: "Active checks run only on domains you prove you own."
- Never commit secrets, `.env`, tokens or real ownership challenge values. Test fixtures use placeholder domains under
  the reserved names `example.com`, `example.org` and `.test`, or our own demo domain.

## How to apply

- In design docs, every component that does I/O states whether it is passive or active, and how it reaches the
  gate.
- Every rule above that can be expressed as a property has one (see `testing.md`). The headline property is "no
  request is ever sent to an unverified host".
- When unsure whether something counts as active, treat it as active.
