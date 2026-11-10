# Requirements Document

## Introduction

"Raise the dead" is the only **active** part of Necropolis. A user proves they own a domain, and then Necropolis
sends one safe request to each archived endpoint in that scope to see what still answers. This spec covers
ownership proof, the probe gate, the network guard (SSRF protection), the probe runner, result classification,
re-probing, and the demo site we probe in the video. Every rule in `safety.md` sections 2 to 5 is a requirement
here.

## Glossary

- **Workspace**: the browser session that owns challenges, proofs and runs. There are no user accounts: a random
  workspace ID is kept in an HttpOnly cookie.
- **Challenge**: a random token issued for a domain or host, which the user publishes by DNS or by file.
- **Proof**: a verified challenge, with method (`dns` or `file`), scope and `verified_at`.
- **ProbeGate**: the component that turns a URL into an `AuthorizedTarget` or a `Refusal`.
- **GuardedClient**: the HTTP client that resolves, checks and pins IP addresses and never follows redirects by
  itself.
- **Probe**: one or more requests for one endpoint (HEAD, a possible GET fallback, up to 3 redirect hops).
- **Outcome**: `open`, `guarded`, `redirected`, `gone`, `erroring`, `other`, `unreachable`, `rate_limited`,
  `refused`, or `not_probeable`.

## Requirements

### Requirement 1: Issue ownership challenges

**User Story:** As a domain owner, I want a simple proof step like the ones search consoles use, so that I can
unlock active checks for my own domain only.

#### Acceptance Criteria

1. WHEN a user requests a challenge for a domain THE system SHALL generate a token from at least 128 bits of
   cryptographic randomness, tied to the workspace and the domain, valid for 72 hours if not verified.
2. THE system SHALL show both options with copy buttons:
   - a DNS TXT record at `_necropolis.<domain>` with the value `necropolis-verification=<token>`;
   - a file at `https://<host>/.well-known/necropolis-verification.txt` that contains only the token.
3. THE system SHALL store the token only in the challenge record of its workspace, so it can be shown again. It
   SHALL never write the token to logs or job events, and SHALL compare it in constant time.

### Requirement 2: Verify ownership

**User Story:** As a domain owner, I want verification to be quick and its scope clear, so that I know exactly which
hosts I have unlocked.

#### Acceptance Criteria

1. WHEN the user asks to verify by DNS THE system SHALL look up TXT records at `_necropolis.<domain>`. WHEN one
   equals the expected value THE system SHALL record a proof whose scope is the domain and all its subdomains.
2. WHEN the user asks to verify by file THE system SHALL fetch the well-known URL through the GuardedClient, without
   following redirects, reading at most 1 KiB. WHEN the trimmed body equals the token THE system SHALL record a proof
   whose scope is that exact origin (scheme, host and port).
3. IF verification fails THEN THE system SHALL say which check failed (no record, wrong value, HTTP status, blocked
   address, timeout), without echoing the fetched content.
4. THE system SHALL treat a proof as current for 24 hours after `verified_at`. Before a probe run uses an older
   proof, it SHALL re-verify, and it SHALL revoke the proof if re-verification fails.
5. THE system SHALL let the user revoke a proof at any time.

### Requirement 3: The probe gate

**User Story:** As the maintainer, I want one choke point that decides what may be contacted, so that no bug
elsewhere can send traffic to a host nobody verified.

#### Acceptance Criteria

1. THE ProbeGate SHALL return an `AuthorizedTarget` only when the URL's scheme is http or https, its port is
   allowed, and its origin is covered by a current proof in the same workspace.
2. THE ProbeGate SHALL match DNS scope by labels: host `h` is covered by domain `D` only if `h == D` or `h` ends with
   `"." + D`.
3. THE ProbeGate SHALL refuse every request WHILE `NECROPOLIS_PROBES_DISABLED=1` is set.
4. THE probe runner SHALL accept only `AuthorizedTarget` values, which only the ProbeGate can construct. No other
   code path SHALL issue a probe request.

### Requirement 4: Network guard

**User Story:** As the operator of a hosted instance, I want archive-derived URLs unable to reach my own
infrastructure, so that Necropolis cannot be turned into an SSRF tool.

#### Acceptance Criteria

1. THE GuardedClient SHALL resolve the host and SHALL refuse the request IF any resolved address is loopback,
   private, link-local, shared (CGNAT), multicast, reserved, unspecified, or an IPv4-mapped IPv6 form of these.
2. THE GuardedClient SHALL connect to the checked address (pinned), and send the original Host header and TLS SNI.
3. THE GuardedClient SHALL NOT follow redirects by itself.
4. THE GuardedClient SHALL apply a 10 s total timeout and read at most the byte limit it is given.

### Requirement 5: Plan and run probes safely

**User Story:** As a domain owner, I want each archived endpoint checked once, gently, so that I learn what still
answers without loading or changing my systems.

#### Acceptance Criteria

1. WHEN a probe run starts THE system SHALL plan one probe per endpoint in the verified scope that has an example
   path, with zombie candidates first, up to 500 endpoints. Endpoints without an example path SHALL get the outcome
   `not_probeable` and SHALL NOT be guessed.
2. THE system SHALL send `HEAD` with only the `User-Agent` and `Accept` headers, no body, no cookies, no credentials,
   and no query string.
3. WHEN `HEAD` returns 405, 501, 2xx or 5xx THE system SHALL send one `GET` with the same constraints. A HEAD
   response carries no body, and the body signals need one (found while building the demo site).
4. THE system SHALL send at most `NECROPOLIS_PROBE_RPS` requests per second per host (default 1, maximum 2), with at
   most 2 in flight per host.
5. WHEN a response is a redirect THE system SHALL record its target. It SHALL follow it only if the target passes
   the ProbeGate, and for at most 3 hops.
6. WHEN a host returns 429 THE system SHALL pause that host for 60 s (or for `Retry-After`, up to 300 s), retry that
   probe once, and record `rate_limited` if it repeats.
7. THE system SHALL allow at most 3 probe runs per domain per workspace per hour, and SHALL let the user cancel a
   run.

### Requirement 6: Classify and keep only what is needed

**User Story:** As a privacy-minded user, I want results that explain what answered without storing anything the
endpoint returned, so that Necropolis never becomes a copy of my data.

#### Acceptance Criteria

1. THE system SHALL classify each probe as exactly one outcome:

   | Response | Outcome |
   |---|---|
   | 2xx | `open` |
   | 401 or 403, or a 3xx whose same-site target path contains `login`, `signin`, `auth` or `sso` | `guarded` |
   | Any other 3xx | `redirected` |
   | 404 or 410 | `gone` |
   | 5xx | `erroring` |
   | Any other 4xx | `other` |
   | DNS, connect or TLS failure, or timeout | `unreachable` |

2. THE system SHALL read at most 64 KiB of a response body in memory, pass it to the autopsy's body-signal function,
   and then discard it.
3. THE system SHALL store only:
   - status, outcome and timing;
   - `Content-Type` and `Content-Length`;
   - the path of a same-site `Location`;
   - the `WWW-Authenticate` scheme name;
   - signal names;
   - a SHA-256 of the bytes read.
4. THE system SHALL NOT write response bodies, query values or challenge tokens to the database, the logs or the
   job events.

### Requirement 7: Re-probe ("is it still risen?")

**User Story:** As a developer who just shipped a burial plan, I want to re-check the zombies it covered, so that I
can see them lie down.

#### Acceptance Criteria

1. WHEN the user re-probes an endpoint or a burial plan's endpoints THE system SHALL run the same safe probe and
   compare it with the previous result.
2. WHEN the outcome moves from `open`, `redirected` or `erroring` to `gone` or `guarded` THE system SHALL mark the
   endpoint `laid_to_rest`, with both results' timestamps.

### Requirement 8: The demo site (our own target)

**User Story:** As the presenter, I want a target I own that shows real zombie behaviour with fake data, so that the
video never touches anyone else's system.

#### Acceptance Criteria

1. THE demo site SHALL serve a v2 front end and a v2 API, and SHALL keep a v1 API answering that the front end no
   longer references.
2. THE demo site SHALL contain only invented data, clearly marked fake. That data SHALL include:
   - one v1 endpoint that returns fake user records without auth while its v2 sibling requires auth;
   - one debug endpoint that returns a fake stack trace;
   - one v1 endpoint that already returns 410.
3. THE demo site SHALL be deployable on its own, and its v1 pages SHALL be archived with Save Page Now before the v1
   links are removed from the front end.
