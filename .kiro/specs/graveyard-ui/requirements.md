# Requirements Document

## Introduction

The graveyard is the face of Necropolis: the HTTP API plus a React front end that takes a user from "type a domain"
to "zombie laid to rest" in one flow. The theme does real work. Crypts group endpoints by API version, tombstones
carry dates, and the glow shows severity. The timeline replays the years. Every themed element also has a plain
label, and an accessible table view shows the same data. "Design" is a judging criterion: one complete,
polished flow, with empty, loading, partial and error states done.

## Glossary

- **UI**: the `web/` React app.
- **API**: the FastAPI routers in `necropolis.api`.
- **Workspace cookie**: an HttpOnly cookie holding a random workspace ID (see the raise-the-dead spec).
- **Fixture mode**: `NECROPOLIS_FIXTURE_MODE=1`. It serves the recorded demo-domain archive data and a fake prober,
  with no network access. It powers "Try the demo graveyard", the tests and the backup for the video.

## Requirements

### Requirement 1: Landing and start

**User Story:** As a first-time visitor, I want to understand what this does and start in one step, so that I reach
the graveyard within seconds.

#### Acceptance Criteria

1. THE UI SHALL show:
   - a one-line pitch;
   - a domain input with a scope toggle (this host / include subdomains);
   - the sentence "Archive search works for any domain. Active checks run only on domains you prove you own.";
   - a "Try the demo graveyard" button.
2. WHEN the user submits an invalid domain THE UI SHALL show the API's plain message inline, without navigating.
3. WHEN the user clicks "Try the demo graveyard" THE UI SHALL load the recorded demo run without any network
   request to the archive or to the demo domain.

### Requirement 2: Live exhumation

**User Story:** As a user, I want to watch the graveyard fill in as the archive is searched, so that waiting feels
like progress, and partial results are useful straight away.

#### Acceptance Criteria

1. WHILE an exhume job runs THE UI SHALL show the phase, pages, captures, endpoints and scripts mined, from SSE
   events. Tombstones SHALL appear as endpoints are found.
2. IF the SSE connection drops THEN THE UI SHALL reconnect, and SHALL fetch the job state to fill any gap.
3. THE UI SHALL provide a cancel button, and SHALL show distinct states for `empty` ("Nothing buried here: the
   archive has no captures for this domain"), `partial` (a banner naming the failed phase) and `cancelled`.

### Requirement 3: The necropolis map

**User Story:** As an AppSec engineer, I want the API's history laid out as a graveyard, so that I can see at a
glance which versions are dead, which are haunted, and where the worst zombies are.

#### Acceptance Criteria

1. THE UI SHALL draw one crypt per API version and one tombstone per `api` endpoint. Each tombstone SHALL be engraved
   with its short template and its first and last seen years.
2. THE UI SHALL style tombstones by severity:
   - Buried: dim, settled;
   - Stirring: cracked;
   - Risen: glowing;
   - Rampaging: glowing and twitching;
   - Unexamined: grey.
   Each style SHALL also carry an icon and a text label, never colour alone.
3. THE UI SHALL show a legend with the themed and plain names (from `product.md`).
4. WHEN more than 500 tombstones are on screen THE UI SHALL collapse each crypt into a cluster with counts by
   severity, and SHALL expand it on click.
5. THE UI SHALL let the user filter by severity, crypt and zombie candidate, and search templates.

### Requirement 4: Timeline

**User Story:** As a user, I want to replay the years, so that I can see when endpoints were born and when the front
end abandoned them.

#### Acceptance Criteria

1. THE UI SHALL provide a year slider and a "Replay the years" play button, from the earliest to the latest capture
   year.
2. WHEN the selected year is `y` THE UI SHALL show only endpoints with `first_seen.year <= y`. It SHALL mark as
   abandoned those with `last_seen_in_frontend.year < y`.
3. WHILE `prefers-reduced-motion` is set THE UI SHALL step through years without animation.

### Requirement 5: Tombstone detail

**User Story:** As a user who clicks a tombstone, I want every fact and the evidence behind it, so that I can trust
the finding and act on it.

#### Acceptance Criteria

1. THE UI SHALL show:
   - the template, crypt, first seen, last seen and last seen in the front end;
   - capture count and sources;
   - the probe outcome, status and time;
   - signals with one-line plain explanations;
   - the cause of death.
2. THE UI SHALL link to archive captures as `https://web.archive.org/web/<timestamp>/<url without query>`, opening in
   a new tab with `rel="noopener noreferrer"`.
3. THE UI SHALL offer actions that depend on state:
   - "Prove ownership to raise" when the endpoint is unverified;
   - "Re-probe" when it is verified and has been probed;
   - "Add to burial plan" when its severity is Stirring or higher.

### Requirement 6: Ownership wizard

**User Story:** As a domain owner, I want a short guided proof step, so that I can unlock active checks without
reading documentation.

#### Acceptance Criteria

1. THE UI SHALL guide the user through choosing a method (DNS or file), showing the exact record or file with copy
   buttons, and a "Verify" button with the result.
2. THE UI SHALL list the workspace's proofs, with their scope and age, and let the user revoke one.
3. IF verification fails THEN THE UI SHALL show the API's specific reason and a hint (for example "DNS changes can
   take a few minutes").

### Requirement 7: Raise the dead and re-probe

**User Story:** As a verified owner, I want to start the active check and watch the dead rise, so that the result is
clear and memorable.

#### Acceptance Criteria

1. WHEN a probe run starts THE UI SHALL show live progress. As results arrive, each tombstone SHALL animate from
   grey to its severity ("rising").
2. WHEN a re-probe marks an endpoint `laid_to_rest` THE UI SHALL play a short "lay to rest" transition and show the
   before and after outcomes.
3. IF the API refuses a run (no proof, run limit, kill switch) THEN THE UI SHALL explain why and what to do next.

### Requirement 8: Burial plan builder and reports

**User Story:** As an engineer, I want to pick zombies, choose fixes and take away a Kiro spec and a report, so that
the fix starts in my repo today.

#### Acceptance Criteria

1. THE UI SHALL let the user select eligible zombies, change each rite, preview the three generated files, download
   the `.zip`, and copy each file.
2. THE UI SHALL export the current graveyard as Markdown and as JSON. The export SHALL contain only stored facts,
   with no query values.

### Requirement 9: Accessible and safe by default

**User Story:** As any user, including keyboard and screen-reader users, I want the full product without the visual
map, so that the theme never blocks the function.

#### Acceptance Criteria

1. THE UI SHALL provide a table view with every tombstone's data, sortable by severity, score, crypt and dates.
2. THE UI SHALL be fully keyboard-operable with visible focus. The map SHALL expose tombstones as focusable buttons
   with accessible names: template, plain severity label and years.
3. THE UI SHALL meet WCAG 2.2 AA contrast for text and essential icons.
4. THE UI SHALL render all archive-derived strings as text only. It SHALL NOT use `dangerouslySetInnerHTML`.

### Requirement 10: API surface and request safety

**User Story:** As the maintainer, I want a small, consistent API that resists cross-site abuse, so that a malicious
page cannot drive a visitor's workspace.

#### Acceptance Criteria

1. THE API SHALL expose the routes listed in `design.md`, using the error format in `tech.md`.
2. THE API SHALL create the workspace cookie when it is missing (`HttpOnly`, `SameSite=Lax`, `Secure` outside
   localhost).
3. THE API SHALL reject state-changing requests (POST, DELETE) unless they carry `Content-Type: application/json`
   and the header `X-Necropolis: 1`.
4. THE API SHALL scope every challenge, proof, run and plan to the workspace. A workspace SHALL NOT see or use
   another's.
