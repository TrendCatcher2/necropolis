---
inclusion: always
---

# Repo structure

```
necropolis/                       repo root (public, MIT)
├── .kiro/                        NEVER gitignored
│   ├── steering/                 product, tech, structure, testing, safety
│   ├── specs/<feature>/          requirements.md, design.md, tasks.md
│   ├── hooks/                    *.kiro.hook (PBT on save, safety review, docs refresh)
│   ├── settings/mcp.json         wayback-mcp (+ Context7 for library docs)
│   └── agents/                   "Gravedigger" custom agent
├── backend/
│   ├── pyproject.toml
│   ├── necropolis/
│   │   ├── settings.py           env config (only place that reads env)
│   │   ├── models.py             shared Pydantic models (Endpoint, Capture, ProbeResult, ...)
│   │   ├── archive/              ArchiveClient, CDX paging, snapshot fetch, cache    (passive)
│   │   ├── exhumer/              exhume job, JS miner, endpoint dating               (passive)
│   │   ├── normaliser/           URL → EndpointKey templating (pure, no I/O)
│   │   ├── netguard/             GuardedClient: resolve, IP checks, pinning          (active, low level)
│   │   ├── ownership/            challenges, DNS TXT + file verification             (active)
│   │   ├── prober/               gate.py (ProbeGate), runner.py, classify.py         (active)
│   │   ├── autopsy/              signals, severity, cause-of-death text (pure)
│   │   ├── burial/               Kiro spec generator + templates (pure)
│   │   ├── db/                   connection, migrations/
│   │   └── api/                  FastAPI routers, SSE, static files
│   └── tests/
│       ├── unit/
│       ├── property/             Hypothesis tests, one file per spec
│       └── fixtures/             recorded CDX + snapshots (demo domain / example.com only)
├── mcp/wayback_mcp/              custom MCP server (imports archive + normaliser only)
├── web/                          React + Vite + TS graveyard UI
│   └── src/{api,components,graveyard,pages,styles}/
├── demo-site/                    tiny FastAPI app with v1 (zombie) and v2 APIs: our own demo target
├── docs/                         architecture.md, api.md, CREDITS.md, screenshots/
├── KIRO_LOG.md                   daily log of how Kiro was used (feeds the write-up)
├── Dockerfile
├── LICENSE                       MIT
└── README.md
```

## Dependency rules (enforced by review and the safety hook)

- `normaliser`, `autopsy` and `burial` are **pure**: no I/O, no clock reads (time is passed in), no randomness.
- `archive` and `exhumer` may import `normaliser`. They must never import `netguard`, `ownership` or `prober`.
- Only `ownership` and `prober` import `netguard`.
- `api` wires modules together. Business rules live in the modules, not in routers.
- `mcp/wayback_mcp` may import `archive`, `normaliser` and `models` only.
- `web/` talks to the backend only through `web/src/api/`, a typed client generated from or matched to
  `docs/api.md`.

## Specs and build order

| Order | Spec folder | Module(s) |
|---|---|---|
| 1 | `endpoint-normaliser` | `normaliser` |
| 2 | `exhumer` | `archive`, `exhumer` |
| 3 | `wayback-mcp` | `mcp/wayback_mcp` |
| 4 | `raise-the-dead` | `netguard`, `ownership`, `prober`, `demo-site` |
| 5 | `autopsy` | `autopsy` |
| 6 | `burial-plan` | `burial` |
| 7 | `graveyard-ui` | `api`, `web` |

## Naming

- Python: modules `snake_case`, classes `PascalCase`. Domain words from `product.md` are used in code only where
  they are precise (`Crypt`, `Tombstone`, `Severity.RAMPAGING`). Otherwise use plain names (`EndpointKey`,
  `ProbeResult`).
- Spec requirement IDs are cited in code docstrings and tests as `Req <spec>:<n>.<m>`, for example
  `Req endpoint-normaliser:2.3`.
- Commits are small, one task per commit where possible, with the message referencing the spec task:
  `normaliser: id placeholders (endpoint-normaliser task 2.1)`.
