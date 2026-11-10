# Design Document: raise-the-dead

## Overview

Four layers, each with one job:

1. `netguard`: makes a safe HTTP request to a pinned, checked address (low level, active).
2. `ownership`: challenges and proofs (DNS via an injected resolver; file via `netguard`).
3. `prober.gate`: `ProbeGate`, the policy choke point.
4. `prober.runner` and `prober.classify`: run the plan, classify results, and store the minimal facts.

Also `demo-site/`, a separate tiny FastAPI app that we deploy and archive ourselves.

## Architecture

```
EndpointRecords (exhumer) ─► plan_probes(records, proofs, now) ──► [PlannedProbe]
                                           │                              │
                               ProbeGate.authorize(url, workspace, now)   │
                                   │                  │                   ▼
                              AuthorizedTarget     Refusal ─► outcome=refused (no packet sent)
                                   │
                          runner (per-host token bucket, ≤2 in flight)
                                   │
                         GuardedClient.request(target, method, max_bytes)
                          resolve ─► check IPs ─► pin ─► send ─► read ≤64 KiB
                                   │
                autopsy.body_signals(bytes, content_type) ─► signal names ─► bytes dropped
                                   │
                     classify(status, headers) ─► ProbeResult (minimal) ─► SQLite + JobBus
```

### AuthorizedTarget: why it cannot be forged

```python
class AuthorizedTarget:
    __slots__ = ("url", "origin", "proof_id", "_seal")
    def __init__(self, *a, _seal: object):           # the runner checks: _seal is gate._SEAL
        if _seal is not _GATE_SEAL: raise TypeError("AuthorizedTarget is issued by ProbeGate only")
```

`_GATE_SEAL` is a module-private sentinel. The runner calls `assert_sealed(target)`. A property test and a static
check (the safety hook) confirm that nothing else constructs it. This is defence in depth, not a security boundary
against in-process code.

## Components and Interfaces

```python
# netguard
class GuardedClient:
    def __init__(self, resolver: Resolver, transport: httpx.AsyncBaseTransport | None = None): ...
    async def request(self, target: AuthorizedTarget | WellKnownTarget, method: Literal["HEAD","GET"],
                      max_bytes: int) -> RawResponse      # status, headers, body (≤max_bytes), elapsed
def is_blocked_ip(ip: IPv4Address | IPv6Address) -> bool

# ownership
def new_challenge(workspace_id: str, domain: str, now: datetime) -> Challenge
async def verify_dns(ch: Challenge, resolver: Resolver, now) -> Proof | VerifyFailure
async def verify_file(ch: Challenge, origin: Origin, client: GuardedClient, now) -> Proof | VerifyFailure
def covers(proof: Proof, origin: Origin) -> bool          # pure; Requirement 3.2 label matching

# prober
class ProbeGate:
    def authorize(self, url: str, workspace_id: str, now: datetime) -> AuthorizedTarget | Refusal
def plan_probes(records, workspace_id, gate, now) -> list[PlannedProbe]       # pure given the gate
async def run_probes(plan, client, clock, bus) -> ProbeRunResult
def classify(status: int | None, headers: Mapping[str,str], error: str | None, site: Origin) -> Outcome
```

`WellKnownTarget` is a second sealed type, created only by `ownership.verify_file`, for the exact
`/.well-known/necropolis-verification.txt` URL. It lets the file check use the guard without a proof existing yet.

### Network guard details

- Blocked ranges come from `ipaddress` properties (`is_private`, `is_loopback`, `is_link_local`, `is_multicast`,
  `is_reserved`, `is_unspecified`), plus `100.64.0.0/10`, plus IPv4-mapped and 6to4 forms checked on the embedded
  IPv4 address.
- Pinning: a custom httpx transport connects to the chosen IP, with `server_hostname` (SNI) set to the original
  host and the `Host` header preserved. Certificate verification is on, against the original host name.
- If **any** resolved address is blocked, the whole request is refused, not just that address.

### Rate limiting

- One token bucket per host, using an injected `Clock`. The fake clock in tests makes timing properties
  deterministic.
- Per-workspace run limiter: 3 runs per domain per rolling hour, stored in SQLite.

## Data Models

```python
class Challenge(BaseModel): id: str; workspace_id: str; domain: str; token: SecretStr; created_at: datetime; expires_at: datetime
class Proof(BaseModel): id: str; workspace_id: str; method: Literal["dns","file"]; domain: str | None; origin: Origin | None; verified_at: datetime; revoked: bool
class Outcome(StrEnum): OPEN; GUARDED; REDIRECTED; GONE; ERRORING; OTHER; UNREACHABLE; RATE_LIMITED; REFUSED; NOT_PROBEABLE
class ProbeResult(BaseModel):
    key: EndpointKey; probed_at: datetime; method_used: Literal["HEAD","GET"] | None
    status: int | None; outcome: Outcome; elapsed_ms: int | None
    content_type: str | None; content_length: int | None; location_path: str | None
    auth_scheme: str | None; signals: list[str]; body_sha256: str | None
    laid_to_rest: bool = False; previous_outcome: Outcome | None = None
```

There is deliberately **no** field that can hold a body, a header dump or a query string.

## Correctness Properties

### Property 1: No request ever reaches an unverified host
*For any* set of proofs (methods, scopes, ages, revoked flags), any `now`, any kill-switch value, and any endpoint
list with hosts drawn from the proven domains, look-alikes (`evil-example.com`, `example.com.evil.test`) and random
hosts, every request recorded by the mock transport targets an origin covered by a current, unrevoked proof. With
the kill switch on, zero requests are recorded.
**Validates: Requirements 3.1, 3.2, 3.3, 2.4; safety rule 2**

### Property 2: Scope matching is label-exact
*For any* domain `D` and host `h`, `covers(dns_proof(D), h)` is true if and only if `h == D` or `h` ends with
`"." + D`. A file proof covers only its exact origin.
**Validates: Requirements 2.1, 2.2, 3.2**

### Property 3: Blocked addresses are never contacted
*For any* resolution result containing at least one address from a blocked range (generated across all ranges,
including IPv4-mapped IPv6), the GuardedClient refuses and the transport records no request.
**Validates: Requirement 4.1**

### Property 4: Only safe requests are sent
*For any* sequence of mock responses, every recorded request has method HEAD or GET, no body, no query string, only
the `User-Agent` and `Accept` headers, and a GET only directly after a HEAD that got 405, 501, 2xx or 5xx.
**Validates: Requirements 5.2, 5.3**

### Property 5: Limits hold
*For any* plan, the run probes at most 500 endpoints, sends at most 5 requests per endpoint (HEAD, GET, 3 hops), and
on the fake clock the gap between two request starts to the same host is never below `1/rps`, with never more than
2 in flight.
**Validates: Requirements 5.1, 5.4, 5.5**

### Property 6: Bodies are never kept
*For any* response body containing a random 32-character marker, the marker appears in none of: the stored
`ProbeResult` rows, the job events, or captured log output.
**Validates: Requirements 6.2, 6.3, 6.4**

### Property 7: Classification is total and deterministic
*For any* status in 100 to 599 (or none, with an error kind) and any `Location`, `classify` returns exactly one
outcome, consistent with the table in Requirement 6.1.
**Validates: Requirement 6.1**

### Property 8: Redirects are re-gated
*For any* redirect chain from the mock server, the runner follows at most 3 hops, and every followed hop's origin
passes the ProbeGate. An off-scope hop is recorded as `redirected` with no request sent to it.
**Validates: Requirement 5.5**

## Error Handling

| Situation | Outcome or response |
|---|---|
| Gate refuses | `refused`, with the reason (no proof, expired, kill switch, port); no packet sent |
| Blocked IP | `refused`, reason `blocked_address` |
| DNS/connect/TLS failure, timeout | `unreachable`, error kind only |
| 429 twice | `rate_limited`; the host is paused; the run continues with other hosts |
| Run-limit exceeded | 429 from our API, with the next allowed time |
| Re-verification fails | Proof revoked; the run stops before the first probe; the UI asks to verify again |

## Testing Strategy

- All network access is faked: a resolver stub, an httpx `MockTransport` behind the pinning layer (a transport seam
  is injected), and a fake clock.
- Unit tests: challenge format, DNS and file verification paths, each failure message, the classification table,
  and that `AuthorizedTarget` cannot be built outside the gate.
- Property tests: Properties 1 to 8 in `tests/property/test_raise_props.py`. Property 1 is the headline of the
  write-up.
- Demo-site tests: `demo-site/tests` checks v1/v2 behaviour and that all data is marked fake.
- One manual check (logged in `KIRO_LOG.md`): verify the real demo domain by DNS, run probes, and see the expected
  outcomes.
