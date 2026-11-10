# Requirements Document

## Introduction

A finding is only half the job. The burial-plan generator turns selected zombies into a ready-to-use **Kiro spec**
(`requirements.md`, `design.md`, `tasks.md`). The user drops it into their own repo, and Kiro implements the fix.
Then Necropolis re-probes, and the zombie lies down. This makes Kiro part of the product, not just the tool that
built it. The generator is pure and passive: it only formats facts we already hold.

## Glossary

- **Generator**: the `necropolis.burial` module.
- **Burial plan**: the generated spec folder for one or more zombies, named `bury-<slug>`.
- **Rite**: the fix strategy for one zombie:

  | Rite | Plain meaning |
  |---|---|
  | **Bury** | Retire: return 410 Gone or remove the route |
  | **Ward** | Protect: require the same auth as its siblings |
  | **Pass on** | Redirect: permanent redirect to its successor |
  | **Keep** | Intended: document it and assign an owner |

- **Evidence block**: the facts behind a zombie in the generated spec:
  - template, crypt and dates;
  - outcome, status and signals;
  - sibling and cause of death.

## Requirements

### Requirement 1: Choose rites

**User Story:** As an AppSec engineer, I want a sensible default fix for each zombie that I can change, so that the
plan matches what my team actually wants.

#### Acceptance Criteria

1. THE Generator SHALL propose a default rite for each selected zombie:

   | Situation | Default rite |
   |---|---|
   | `RAMPAGING` with `auth_asymmetry` or `data_exposed` | Ward first, then Bury, as two ordered task groups |
   | `version_behind` with a successor sibling | Pass on |
   | `docs_exposed` or `sensitive_path` | Bury |
   | Anything else | Bury |

2. THE system SHALL let the user change the rite per zombie before generating.
3. THE Generator SHALL accept only zombies with severity `STIRRING` or higher. It SHALL refuse `BURIED` and
   unexamined endpoints, and say why.

### Requirement 2: Generate a valid Kiro spec

**User Story:** As a developer using Kiro, I want the plan in Kiro's own spec format, so that I can open it and run
the tasks straight away.

#### Acceptance Criteria

1. THE Generator SHALL produce exactly three files under `.kiro/specs/bury-<slug>/`:
   - `requirements.md`: an introduction, a glossary, and numbered requirements with user stories and EARS
     acceptance criteria;
   - `design.md`: an overview, approach by rite, evidence, correctness properties, error handling and testing;
   - `tasks.md`: a numbered checkbox plan in which every task cites requirement IDs.
2. THE Generator SHALL write one requirement for each zombie, with acceptance criteria that state the expected
   outcome after the fix:
   - Bury: 410 or 404;
   - Ward: 401 or 403 without credentials;
   - Pass on: 301 or 308 to the successor;
   - Keep: listed in the API inventory with an owner.
3. THE Generator SHALL include, for each zombie:
   - a regression-test task that asserts the post-fix outcome;
   - a final task to re-probe with Necropolis and confirm `laid_to_rest`.
4. Because Necropolis does not know the user's framework, THE Generator SHALL mark framework-specific details as
   `[CONFIRM: …]` items for the user's Kiro to resolve from their codebase, and SHALL NOT guess file names or
   frameworks.

### Requirement 3: Safe rendering

**User Story:** As a user whose AI agent will read this spec, I want archived strings treated as data, so that an
old URL cannot inject markup or instructions into my repo.

#### Acceptance Criteria

1. THE Generator SHALL render endpoint templates, example paths and sibling templates only inside inline code spans
   or fenced code blocks. It SHALL use a fence longer than any backtick run in the value, and SHALL percent-encode
   characters outside the URL path character set.
2. THE Generator SHALL put the evidence under a heading that says the values come from the web archive and probe
   results, and are data, not instructions.
3. THE Generator SHALL NOT include response bodies, query values, ownership tokens or workspace IDs, and its input
   types SHALL have no fields that hold them.
4. THE Generator SHALL derive the `<slug>` only from `[a-z0-9-]`, at most 60 characters, and every archive entry
   path SHALL be relative with no `..` segments.

### Requirement 4: Deliver the plan

**User Story:** As a user, I want to download or copy the plan, so that I can add it to my repo in under a minute.

#### Acceptance Criteria

1. THE system SHALL offer the plan as a `.zip` that holds the folder, and as copy buttons for each file.
2. WHERE the user opts in THE Generator SHALL also emit `.kiro/steering/api-lifecycle.md`, a short steering doc
   telling Kiro to retire an old API version in the same change that replaces it. This keeps new zombies from
   forming.
3. THE Generator SHALL be deterministic. Equal inputs SHALL give byte-identical files, with zombies sorted by
   endpoint key and every date taken from the input.
