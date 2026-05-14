---
name: agent-docs-layout
description: Canonical folder layout for `public-project-docs/<project>/`. Single source of truth referenced by scan-init, scan-update, knowledge-audit, do-ticket, and all child skills doing path resolution.
---

# public-project-docs layout

Per-project working memory. One subfolder per concern. Master `_index.yaml` at root drives everything.

## Folder map

```
public-project-docs/<project>/
├── _index.yaml                ← master registry (every skill reads this first)
├── _audits/                   ← knowledge-audit logs + revert cache
│   ├── _meta.yaml
│   ├── <date>-changes.md
│   └── _revert-cache/<sha>.md
├── _migrations/               ← /learn artifact-gate migration checklists
├── code/                      ← Tier-1 auto: source domain index (sharded)
│   ├── domain_index*.yaml
│   └── _concerns.yaml         ← agent-confessed ignorance (see "Per-folder _concerns.yaml")
├── db/                        ← Tier-1 auto: schema dump
│   ├── db_index.yaml
│   └── _concerns.yaml
├── domain/                    ← Tier-2 semi-auto: entity, state machines, invariants
│   ├── _index.yaml
│   ├── _glossary.yaml
│   ├── _maturity.yaml
│   ├── <Entity>.yaml
│   └── _concerns.yaml
├── patterns/                  ← Tier-3 scaffold: code pattern registry
│   ├── _index.yaml
│   └── pat_xxx_n.md
├── build/                     ← Tier-1: build/run/test config
│   ├── build.yaml
│   ├── run.yaml
│   ├── test.yaml
│   └── _concerns.yaml
├── conventions/               ← Tier-1+2: project conventions
│   ├── git.yaml
│   ├── ci.yaml
│   ├── security.yaml
│   └── _concerns.yaml
├── api/                       ← scan-api-docs output (existing)
├── runbooks/                  ← runbook skill output (existing)
├── specimens/                 ← specimen-sandbox output (existing)
├── concepts/                  ← project-specific judgments (existing)
├── tickets/<ID>/              ← do-ticket per-ticket workspace
├── flows/                     ← /learn canonical flows
└── INDEX.md                   ← human-readable top-level index (doc-manager)
```

## Master `_index.yaml`

```yaml
schema_version: 2
project: <name>
last_full_scan: <iso>
scan_init_version: <semver>

# Baseline + drift tracking — see "Baseline + Drift" section below.
# Optional until first `scan-init verify --establish-baseline` is run.
baseline: { ... }
drift_since_baseline: [ ... ]

artifacts:
  code:
    path: code/domain_index.yaml
    fingerprint: <sha-of-artifact>          # aggregate across all repos when complete
    aggregate_fingerprint_status: complete | incomplete
    source_globs: ["**/*.cs", "**/*.ts"]
    source_mtime_max: <iso>
    source_file_count: <int>
    source_top_dirs: [Modules, Services, Controllers]
    consumer_phases: [6, 9, 10, 11]
    last_updated: <iso>
    status: fresh | partial | stale
    # For multi-repo projects: per_repo tracking
    per_repo:
      <repo-name>:
        status: reconciled | stub | pending
        # reconciled  = real fingerprint computed, shard fully populated, legacy (if any) deleted
        # stub        = shard exists but content is impoverished or legacy still uncleared
        # pending     = no shard yet
        fingerprint: <sha>                  # only when status: reconciled
        file_count: <int>                   # only when status: reconciled
        shards: [<path>, <path>]            # always a list, even if single shard
        concerns_opened: <int>              # count of open entries in _concerns.yaml referencing this repo
        last_reconciled: <iso>              # only when status: reconciled
        reconciled_by: scan-init | scan-update | human   # who/what last wrote this entry
        legacy_deleted: true | false        # only meaningful when status: reconciled
        next_action: null | <command-string>  # e.g. "scan-update code --repo <name>" when known drift exists

  db:
    path: db/db_index.yaml
    fingerprint: <sha>
    source_globs: ["**/Migrations/*.cs", "**/*_migration.sql"]
    source_mtime_max: <iso>
    source_file_count: <int>
    consumer_phases: [9, 11, 14]
    last_updated: <iso>

  domain:
    path: domain/_index.yaml
    fingerprint: <sha>
    consumer_phases: [6, 7, 11, 19]
    last_updated: <iso>

  patterns:
    path: patterns/_index.yaml
    consumer_phases: [9, 11]
    last_updated: <iso>

  build:
    path: build/                  # folder, not single file
    files: [build.yaml, run.yaml, test.yaml]
    consumer_phases: [9, 10, 12, 14]
    last_updated: <iso>

  conventions:
    path: conventions/
    files: [git.yaml, ci.yaml, security.yaml]
    consumer_phases: [17, 18, 21]
    last_updated: <iso>

  api:
    path: api/gateway_api_docs.yaml
    consumer_phases: [15]
    last_updated: <iso>

phase_readiness:
  # Computed by scan-init/scan-update after each artifact write.
  # do-ticket reads phase_readiness[<phase>] before running phase.
  # ready: false → G10 with options rescan/skip/abort.
  # degraded: true → phase can run but on partial/stub data; skill SHOULD warn but not block.
  6:  { ready: true,  degraded: false, missing: [] }
  7:  { ready: false, degraded: false, missing: ["domain/_index.yaml — not yet scaffolded"] }
  9:  { ready: true,  degraded: true,  partial_reason: "code artifact aggregate_fingerprint_status: incomplete (3/11 repos reconciled)" }
  # ... per phase do-ticket may run
```

### `ready` vs `degraded` semantics

- `ready: false` — phase MUST NOT run. Skill blocks with G10 (rescan/skip/abort).
- `ready: true, degraded: false` — phase runs normally.
- `ready: true, degraded: true` — phase runs but downstream skill should:
  1. Emit a one-line warning at phase start (`⚠ running phase N on degraded data: <partial_reason>`)
  2. Lower confidence in any conclusions drawn from the degraded artifact
  3. If the ticket scope intersects a `status: stub` or `status: pending` repo → escalate to user

`degraded: true` is set when EITHER:
- An artifact has `status: partial` (e.g. code multi-repo with `aggregate_fingerprint_status: incomplete`)
- An artifact has open `_concerns.yaml` entries with `severity: high` AND `confidence: confirmed` that touch the consumer phase

## Per-folder `_concerns.yaml` — agent-flagged items future tickets should know about

Every artifact folder (`code/`, `db/`, `domain/`, `build/`, `conventions/`) MUST contain a `_concerns.yaml` file. It records anything the agent flags during scan that a future ticket should be aware of *before* touching the area. Empty list is valid; the file must still exist (proves the scan ran and asked the questions).

### Three independent axes

Every entry is classified along three orthogonal axes. Mixing axes (e.g. one "priority" field encoding both severity AND confidence) hides important distinctions — a `high`-severity `hunch` is treated very differently from a `high`-severity `confirmed` finding.

#### Axis 1 — `type` (what kind of thing is this?)

| `type` | Meaning | Why captured |
|---|---|---|
| `concern` | Agent cannot infer the *business* intent of a piece of logic | Future ticket may guess wrong and break business rule |
| `smell` | Code works but deviates from technical best practice (`Thread.Sleep` to wait async, manual JSON parsing, swallowed exception) | Tech-debt visibility; cheaper to fix when touching nearby |
| `risk` | Code runs correctly today but has a latent bug (race condition, uncovered edge case, hardcoded limit, missing retry/backoff) | Will break later — usually under scale, concurrency, or unusual input |
| `knowledge-gap` | Agent itself doesn't understand a whole flow — needs to read more code / ask | Not a code problem; a *scan* problem. Tracked separately so it doesn't pollute real findings |
| `decision-log` | Code looks unusual but is intentional (comment, commit, or design doc says so) — recorded so future scans don't re-flag as `smell`/`risk` | Stops re-discovery loop; preserves rationale for traded-off choices |

`concern` ≠ `knowledge-gap`: `concern` is about the code's intent being unclear; `knowledge-gap` is about the agent's own understanding being incomplete. A `concern` blocks the user (user must answer). A `knowledge-gap` blocks the agent (agent must investigate further before next ticket).

`decision-log` is the *only* type with status `recorded` instead of `open` by default — it's already resolved at creation time.

#### Locked type-discriminator rules (mandatory)

These rules MUST hold. If they don't, the entry has the wrong `type`.

1. **`risk` is for mechanical bugs only.** A `risk` entry MUST have:
   - `failure_scenario` filled
   - `trigger_condition` filled
   - NO `business_question` field
   - NO "if intentional / if unintentional" branch in `suggested_fix`
   - `intent_assessment: not_applicable` (see "Confidence axes" below)

   Examples that ARE `risk`: NaN division, null-ref on missing element, race condition on singleton, encoding corruption. Examples that ARE NOT `risk` despite having a failure scenario: anything where the agent isn't sure whether the behavior is intentional.

2. **`concern` is for intent-uncertain findings.** A `concern` entry MUST have:
   - `business_question` filled
   - `what_we_dont_know` filled
   - `intent_assessment` is the primary confidence signal (`confirmed`/`likely`/`hunch`)
   - MAY include `failure_scenario` if a wrong interpretation produces a clear failure mode

3. **If an entry has BOTH** a clear failure scenario AND a business question about intent → `type: concern` (not `risk`). The presence of an intent question is the discriminator, regardless of failure clarity.

4. **Agent self-check before writing entry:** if `suggested_fix` says "if intentional ... if unintentional ..." → re-classify as `concern`.

5. **`smell` ≠ `risk` ≠ `concern`:** `smell` is "deviates from best practice but works as intended". A smell entry's `expected_pattern` + `why_unusual` carry the load. If agent is uncertain whether the deviation IS intended → upgrade to `concern`; if certain the deviation IS a latent bug → upgrade to `risk`.

#### Axis 2 — `severity` (how bad if not addressed?)

Severity is **scope-relative**. The same code pattern can be `medium` in a mock service and `high` in a production billing service. The rubric below is the default; per-folder + per-repo qualifiers refine it.

| `severity` | Meaning (default) |
|---|---|
| `low` | Cosmetic, isolated, or unlikely to bite — fix when convenient |
| `medium` | Could cause incorrect behavior or slow future work in a specific scenario |
| `high` | Will cause incident, data corruption, or block multiple tickets if untouched |

##### Per-folder severity scope

| Folder | Severity is measured against |
|---|---|
| `code/` | Blast radius if a ticket touches this code AND ships to production. Mock/test code use lower stakes (see per-repo qualifier). |
| `db/` | Data integrity, migration safety, query correctness under scale |
| `domain/` | Business-rule correctness; invariant enforcement gap |
| `build/` | CI/deployment break risk; reproducibility |
| `conventions/` | Onboarding friction; future inconsistency cost |

##### Per-repo qualifier (code folder only)

When the location is inside a mock/test/seed repo (e.g. `*-3rd-party-mock`, `*-playwright`), shift severity DOWN by one level relative to the default rubric unless the issue would also affect tests producing false positives:

- `high` (in mock) ≈ `medium` (in prod) — "tests will fail / mask real bugs"
- `medium` (in mock) ≈ `low` (in prod) — "test code smell"
- `low` (in mock) — usually skip, not worth recording

This rule prevents mock concerns from drowning out production concerns when downstream skills filter by `severity: high`.

##### Header rubric block

Every `_concerns.yaml` MUST start with a comment block referencing this rubric:

```yaml
# code/_concerns.yaml
# Severity rubric: see _shared/agent-docs-layout.md "Per-folder severity scope".
# Per-repo qualifier active: mock/test repos use shifted scale.
folder: code
...
```

#### Axis 3 — `confidence` (split into two sub-fields)

The single `confidence` field was found to gang two distinct questions: "did agent actually read the code?" and "is agent sure about the intent?". These are orthogonal — agent can have `confirmed` code observation but `hunch` about whether the pattern is intentional. SLA review 2026-05-13 forced this split.

```yaml
confidence:
  code_observation: confirmed | likely | hunch
  intent_assessment: confirmed | likely | hunch | not_applicable
```

##### `code_observation` (did agent read the actual code?)

| Value | Meaning |
|---|---|
| `confirmed` | Agent read the code excerpt verbatim; pattern is verified in source. |
| `likely`    | Agent read partial source OR carried from prior scan with structural evidence (e.g. legacy domain_index pointed to it); pattern is plausible but not freshly verified. |
| `hunch`     | Agent has not read the code; entry exists from description only (legacy carry-over without code excerpt, OR pattern matching across siblings). |

`code_observation: hunch` MUST have `source.origin: legacy_carryover` or `source.origin: partial_reverify`. Fresh scans MUST have at least `likely`.

##### `intent_assessment` (does agent understand whether this is a bug?)

| Value | Meaning |
|---|---|
| `confirmed` | Explicit signal proves the intent (comment `// intentional`, ADR doc, test asserting the behavior). |
| `likely`    | Agent has a leaning (more likely bug than intentional, or vice versa) but no proof. |
| `hunch`     | Could go either way; user input needed. |
| `not_applicable` | Entry type is `risk` (mechanical bug, intent question doesn't apply) OR `decision-log` (intent already known). |

**Per-type defaults:**

| `type` | Expected `intent_assessment` |
|---|---|
| `risk` | MUST be `not_applicable` |
| `concern` | one of `confirmed`/`likely`/`hunch` (never `not_applicable`) |
| `smell` | usually `confirmed` or `likely` |
| `knowledge-gap` | `not_applicable` |
| `decision-log` | `not_applicable` |

**Backwards compatibility:** entries written with single `confidence: <value>` before 2026-05-13 are interpreted as:
- For `type: risk`: `code_observation = <value>`, `intent_assessment = not_applicable`
- For `type: concern`/`smell`: `code_observation = confirmed` (assumed; legacy didn't track separately), `intent_assessment = <value>`

**Why three axes (type + severity + confidence-split):**
A `high` severity `confirmed`-code + `hunch`-intent is "code definitely does X but we don't know if X is bug" — user must clarify intent before any fix.
A `high` severity `confirmed`-code + `confirmed`-intent is "this is definitely a bug" — ticket immediately.
Folding intent + code into one field hides this discriminator.

### Schema

```yaml
# <folder>/_concerns.yaml
folder: code | db | domain | build | conventions
last_updated: <iso>

concerns:
  - id: <folder-prefix>-<nnn>     # c-001 for code/, d-001 for db/, dom-001 for domain/, b-001 for build/, conv-001 for conventions/

    # Three axes (confidence is split into 2 sub-fields):
    type: concern | smell | risk | knowledge-gap | decision-log
    severity: low | medium | high
    confidence:
      code_observation: confirmed | likely | hunch
      intent_assessment: confirmed | likely | hunch | not_applicable

    # Provenance (lock 2026-05-13):
    source:
      origin: fresh_scan | legacy_carryover | partial_reverify
      legacy_scan_date: null | <iso>          # set when origin in (legacy_carryover, partial_reverify)
      reverified_at: null | <iso>             # last time agent re-read source against this entry
      reverified_scope: full | description_only | code_location_only | none

    # Release-blocking flag (lock 2026-05-13):
    blocks_release: true | false              # true → MUST be fixed before next release

    # Optional related entries (omit field entirely if empty — do NOT write `related_concerns: []`):
    # related_concerns: [<id>, ...]

    location: <file:line> | <table.column> | <service:port>
    code_excerpt: |               # 3–10 lines of context (code/db folders only)
      <verbatim snippet>
      # REQUIRED when confidence.code_observation in (confirmed, likely).
      # OMIT entirely when confidence.code_observation: hunch — agent has not read the source, so a
      # verbatim snippet is impossible. Do NOT fabricate or quote the description as a substitute.

    tags: [<string>, ...]         # OPTIONAL. Use canonical vocabulary below.
                                  # Empty list MUST be omitted (do not write `tags: []`).
                                  # `before-release` and other triage tags MAY also be set as top-level booleans
                                  # (e.g. `blocks_release: true` replaces `tags: [before-release]`).

    description: <one-sentence — what the agent sees>
    impact: <one-sentence — what breaks or gets harder if untouched>

    # Type-specific fields (only the section matching `type` is required):

    # type=concern:
    business_question: <"why is this done this way?" — one sentence>
    what_we_dont_know: |          # bullet list — what specifically the agent could not infer
      - <reason 1>

    # type=smell:
    expected_pattern: <best-practice alternative>
    why_unusual: <one-sentence>
    suggested_fix: <low-confidence proposal — may be empty>

    # type=risk:
    failure_scenario: <when it will break — input shape, concurrency, scale>
    trigger_condition: <specific condition that triggers the bug>
    blast_radius: <what is affected when it fires>

    # type=knowledge-gap:
    what_to_learn: <which flow / behavior the agent needs to understand>
    where_to_ask: <suggestion: code path to trace, doc to read, SME to ask>

    # type=decision-log:
    rationale: <why this unusual choice was made>
    traded_off_against: <what was given up>
    decided_by: <person/team or "unknown">
    decided_at: <iso or "unknown">
    source_of_rationale: <comment | commit_msg | ADR_doc | inferred>

    # Common lifecycle fields:
    status: <see state machine below>
    user_note: null | <freeform user text when status changes>
    status_changed_at: null | <iso>
    status_changed_by: null | <user>
```

### Dedup contract: `_concerns.yaml` vs `complexity_flags` in shards

Two parallel systems can flag the same code. To avoid duplication and contradictory state, the contract is:

| System | What it holds | Schema lives in |
|---|---|---|
| `complexity_flags` (per shard, inside `code/domain_index_<service>_*.yaml`) | **Inventory** of structural antipatterns from a fixed registry (12 types: IMPLICIT_STATE, SHARED_MUTABLE_STATE, TEMPORAL_COUPLING, UNSTABLE_SHAPE, HIDDEN_CONVENTION, DEEP_DEPENDENCY, CLUSTER_BRANCH_EXPLOSION, OBSERVABLE_SPAGHETTI, COMPONENT_GOD_OBJECT, CROSS_REMOTE_COUPLING, CROSS_SERVICE_COUPLING, UNKNOWN). Each entry is a (type, location, symptom, risk) tuple. No user-facing prose, no triage. | scan-init/SKILL.md "Complexity Detection" |
| `_concerns.yaml` (per folder, top-level) | **Judgment calls** with user-facing prose. Each entry is a (type, severity, confidence, location, description, ...) tuple. Drives user triage. | `_shared/agent-docs-layout.md` "Per-folder _concerns.yaml" |

**Routing rule — where does a finding go?**

```
finding has registered complexity_flag type (one of 12)?
├── YES, AND agent has location-specific judgment (concrete impact, blast radius, etc.)
│       → BOTH:
│         - shard.complexity_flags entry (inventory, no prose)
│         - _concerns.yaml entry with linked_concern_target field
│         - shard entry has linked_concern: <concern-id> ref (one-way: shard → concern)
│
├── YES, BUT agent only has the pattern recognition, no specific judgment
│       → ONLY shard.complexity_flags entry. _concerns.yaml unused for this finding.
│
└── NO (finding doesn't match any registered type, e.g. business_smell, decision-log, knowledge-gap)
        → ONLY _concerns.yaml entry. shard.complexity_flags unused for this finding.
```

**Cross-link direction is ONE-WAY:** `complexity_flag` may carry `linked_concern: <id>` pointing to a `_concerns.yaml` entry. A `_concerns.yaml` entry does NOT carry a `linked_complexity_flag` back-ref — keeping cross-link unidirectional avoids stale-pair drift.

**Dedup check at scan time:** before adding a new `complexity_flag` entry, check `_concerns.yaml` for an existing entry at the same `location` with status in (`open`, `acknowledged`, `mitigated`, `recorded`). If found AND the new flag's `type` is in the registry → add the flag and set `linked_concern` to the existing concern's id. Do NOT create a duplicate concern entry.

**Lifecycle independence:** a `complexity_flag` entry stays in the shard until refactoring removes the pattern (scan re-detection determines this). A `_concerns.yaml` entry transitions via its own status state machine. Both can coexist for the same code if the situation warrants it (one tracks inventory, the other tracks user-facing triage).

**Stale `linked_concern` handling:** when a `_concerns.yaml` entry transitions to a terminal status:

| Concern terminal status | Action on shard's `linked_concern: <id>` |
|---|---|
| `answered` / `acknowledged` / `mitigated` / `recorded` | KEEP — link still informational; user can re-read the triage history |
| `dismissed` | KEEP but mark — shard SHOULD add `linked_concern_status: dismissed` next to `linked_concern: <id>` so reviewers see the link was rejected without re-reading the concern |
| `fixed` | DROP — refactoring removed the underlying code pattern, so the next scan should NOT re-detect the flag. If next scan still detects the flag → it's a regression, file a new concern (do NOT reuse the fixed id) |
| `superseded` | UPDATE — change `linked_concern: <old-id>` to the new concern id; old id stays in `_concerns.yaml` for audit |

Rationale: keeping a dropped or stale `linked_concern` pointer creates phantom links that confuse re-scan dedup. The shard's `complexity_flag` itself only goes away when the pattern is no longer detected.

### `blocks_release` — top-level boolean

Promoted from the `before-release` tag because release-blocking is a primary filter for triage. Tags are array-contains (slow + error-prone); boolean is direct.

```yaml
blocks_release: true | false      # default false, omit when false to keep YAML clean
```

Rules:
- Setting `blocks_release: true` implies the entry MUST be addressed before the next release. CI / release dashboards SHOULD surface these.
- `blocks_release: true` SHOULD also have `severity: high` (otherwise the agent should justify in a `block_reason` field).
- A `dismissed` or `fixed` entry's `blocks_release` is moot but the field stays for audit.
- Tag `before-release` is allowed but redundant when `blocks_release: true` is set — prefer the boolean.

### `related_concerns` consistency rule

Either omit the field entirely OR provide a non-empty list. NEVER write `related_concerns: []`.

```yaml
# OK: omit field entirely if no related entries
- id: c-001
  type: risk
  ...
  # (no related_concerns field)

# OK: at least one related entry
- id: c-014
  type: risk
  ...
  related_concerns: [c-023]

# NOT OK — do not write empty list
- id: c-029
  related_concerns: []     # ← reject in linting
```

### Canonical tag vocabulary

`tags:` MUST draw from this vocabulary. Agent MAY invent a new tag, but must log it under `tag_inventions:` in the shard's `scan_metadata:` so reviewers can promote it into canonical OR rename to an existing tag.

```yaml
canonical_tags:
  topic:                          # what kind of issue
    - concurrency
    - error-handling
    - exception-swallowing
    - silent-failure
    - retry
    - validation
    - authentication
    - authorization
    - logging
    - performance
    - hot-path
    - n-plus-1
    - dependency-injection
    - encoding
    - injection
    - null-reference
    - division-by-zero
    - dry
    - dead-code
    - naming
    - magic-numbers
    - hidden-convention
    - business-semantics
    - status-transition
    - update-semantics

  scope:                          # blast radius
    - mock-only
    - test-only
    - ci-only
    - prod-impact

  subsystem:                      # which module — populated dynamically from variability_axes + module names
    # e.g. cogas, indication, sync, deadline, kpi, dashboard, email-parsing, attachments

  triage:                         # workflow hints
    - on-touch                    # fix when you next touch this file
    - sprint-Q2
    - before-release              # → consider also setting top-level blocks_release: true
    - needs-business-confirm
```

**Vocabulary lifecycle:** new candidate tags accumulate in shard `scan_metadata.tag_inventions`. `/learn` skill periodically reviews and either promotes to canonical or rewrites entries to use existing tags.

### `complexity_flag` registry growth discipline

The 12-type registry (defined in `scan-init/SKILL.md` "Complexity Detection") is intentionally tight. Adding a new type changes future scan behavior across all repos, so promotion needs evidence — not one-off ideas.

**Escape hatch when a finding doesn't fit any of the 12 types:**

```yaml
- type: UNKNOWN
  location: <file:line>
  symptom: "<one-line description of the actual pattern>"
  risk: low | medium | high
  linked_concern: <c-id>           # always link to a _concerns.yaml entry
  needs_skill_update: true         # signal that registry may need expansion
  hint: "Consider adding type X for ..."   # OPTIONAL — agent's proposal
```

`UNKNOWN` is NOT a failure mode — it is the canonical way to flag findings that don't fit the registry. Future scans accumulate these as evidence.

**Promotion to the registry — gate:**

A proposed new type (e.g. `DATA_CORRUPTION_AT_BOUNDARY` suggested by scheduler c-016) is added to the registry only when:

1. **≥3 confirmed instances** across at least 2 different repos (proves recurrence, not one-off) — OR —
2. **Cross-skill consensus**: another scanning skill (e.g. `scan-api-docs`, `domain-problem-solver`) independently flags the same pattern under a different name.

Until promotion, `UNKNOWN` entries with the same `hint:` accumulate as evidence. The `/learn` skill periodically reviews all `UNKNOWN` flags and triggers promotion / rename / dismiss.

**What promotion entails:**
- Update scan-init/SKILL.md "Complexity Detection" table with the new type + 1-line symptom + default risk
- Migrate accumulated `UNKNOWN` entries with matching `hint:` to the new type (preserve `linked_concern`)
- Bump scan-init minor version
- Note in `_index.yaml.scan_init_version` + drift entry if applicable

**What "deferred" looks like:**
- Entry stays `UNKNOWN`. Future scans MAY re-add the same `UNKNOWN` with the same `hint:` — that IS the evidence collection mechanism. Do NOT rename to a non-registry type to avoid `UNKNOWN`.

### `source:` block — provenance tracking

Every `_concerns.yaml` entry MUST have a `source:` block. It tracks WHERE this entry came from and WHEN agent last verified it against current source. Replaces the previous practice of writing "Carried from legacy" prose in `description` or `code_excerpt`.

```yaml
source:
  origin: fresh_scan | legacy_carryover | partial_reverify
  legacy_scan_date: null | <iso>
  reverified_at: null | <iso>
  reverified_scope: full | description_only | code_location_only | none
```

| `origin` | When agent set this | Required fields |
|---|---|---|
| `fresh_scan` | Agent deep-read the source file this pass. | `reverified_at: <iso>`, `reverified_scope: full`. `legacy_scan_date: null` |
| `legacy_carryover` | Entry created from a prior scan's domain_index without re-reading source. | `legacy_scan_date: <iso>`, `reverified_at: null`, `reverified_scope: none` |
| `partial_reverify` | Agent verified part of the legacy claim (e.g. confirmed file+line still exists but didn't re-read full content) | `legacy_scan_date: <iso>`, `reverified_at: <iso>`, `reverified_scope: code_location_only` or `description_only` |

#### `reverified_scope` rubric

| Value | Agent action | When to use |
|---|---|---|
| `full` | Read the file's full content; confirmed both the code pattern AND the line/location | Default when deep-reading legacy carry-over or doing fresh scan. Allows upgrading `code_observation: hunch → confirmed`. |
| `code_location_only` | Verified file path + line/symbol still exists (via Glob/Grep) but did NOT read file contents | Touch-up pass: legacy says "X in FileA.cs:42" — agent confirms FileA.cs exists and line 42 has the named symbol. Does NOT upgrade `code_observation` (still `hunch`/`likely`). |
| `description_only` | Re-read the entry's `description` field for staleness/clarity but did NOT touch source | Editorial pass: clean up wording, fix typo in `business_question`, reword `failure_scenario`. No code verification. |
| `none` | Untouched since legacy scan | Default for `legacy_carryover` until first reverify. |

A `partial_reverify` entry uses `code_location_only` or `description_only` (never `full` — that promotes the entry to "fully reverified", drop `partial_reverify` origin in favor of keeping `legacy_carryover` with `reverified_scope: full`).

**Lifecycle:** when a `legacy_carryover` entry is later deep-read, agent updates the entry in-place: set `reverified_at`, set `reverified_scope: full`, and may upgrade `code_observation` from `hunch`/`likely` to `confirmed`. `origin` stays `legacy_carryover` (provenance is permanent); the `reverified_*` fields capture the upgrade.

**Filtering:** downstream skills can filter `where source.origin == legacy_carryover` to find entries needing re-verification. `scan-init verify` MUST report count of `legacy_carryover` entries per folder.

### Status state machine per `type`

| `type` | Default status | Valid terminal status | Meaning of each |
|---|---|---|---|
| `concern` | `open` | `answered` / `dismissed` | answered: user filled answer; dismissed: turned out obvious / non-issue |
| `smell` | `open` | `acknowledged` / `fixed` / `dismissed` | acknowledged: known, accepted; fixed: refactored; dismissed: not actually a smell |
| `risk` | `open` | `acknowledged` / `mitigated` / `fixed` / `dismissed` | mitigated: risk reduced (guard added) but root remains; fixed: root cause gone; dismissed: false positive |
| `knowledge-gap` | `open` | `learned` / `dismissed` | learned: agent investigated, summary captured in `user_note`; dismissed: not worth learning |
| `decision-log` | `recorded` | `superseded` | superseded: a later decision changed the rationale (link new entry id in `user_note`) |

**Re-scan dedupe by status:**
- `(open, answered, acknowledged, mitigated, recorded)` → DO NOT re-add the same `(location, type, description)`.
- `(dismissed, fixed, learned, superseded)` → MAY re-add if scan re-detects (signal previously closed; current scan found it again — could mean fix regressed or decision no longer applies).

### Per-folder examples by `type`

| Folder | `concern` | `smell` | `risk` | `knowledge-gap` | `decision-log` |
|---|---|---|---|---|---|
| `code/` | Magic number `7200` with no comment in business logic | `Thread.Sleep(500)` to wait for async; manual JSON parse where `IConfiguration` fits | Repository method does `Where().First()` without `OrderBy` — order is non-deterministic; retry loop without backoff | Whole task-lifecycle flow spans 6 files and 2 services — agent traced 4 of 6 | Comment says `// keep this synchronous, async breaks the legacy webhook` |
| `db/` | Column `task.aux_flag` has no obvious business meaning | Nullable column that semantically can't be null; JSONB where relational shape fits | Missing `ON DELETE` rule on FK; missing unique index on column used as key in code | Schema has 47 tables; agent indexed structure but didn't trace which tables participate in which business flow | Migration comment: `// not adding FK because legacy system writes orphan rows` |
| `domain/` | Entity field name says `IsLocked` but no enforcement code found — is it an invariant or a label? | Entity exposes mutable state instead of state-machine transitions | Invariant enforced in service layer but bypassable via direct repo write | Aggregate boundary unclear — does `Task` own `Address` or reference it? | Docstring: `// Address kept as value object intentionally — legal team requires immutability` |
| `build/` | Env var `LEGACY_MODE` referenced but not in any config | docker-compose `depends_on` contradicts code service refs | Port assignment overlaps between two services in different repos | Microservice dependency graph — agent has node list but not edge list | `// docker-compose pins to image v1.4 — v1.5 breaks DB schema` |
| `conventions/` | Why does `service-sla` not have the standard PR template? | Commit format inconsistent across repos | Security regex catches `password=` but not `pwd=` — bypass path | Branch protection rules vary by repo — agent has rules but not the reasoning | `// hotfix/* allowed to bypass review per ops policy 2025-Q3` |

### Treatment matrix

With split confidence, triage uses `severity` × `intent_assessment` (for `concern`/`smell`) OR `severity` × `code_observation` (for `risk`/`knowledge-gap`).

**For `risk` (intent_assessment = not_applicable):**

|           | `hunch` code | `likely` code         | `confirmed` code       |
|-----------|--------------|------------------------|------------------------|
| **high**  | Re-read source first | Verify in code then ticket | Ticket immediately + check `blocks_release` |
| **medium**| Re-read source first | Backlog                | Ticket when capacity   |
| **low**   | Dismiss                | Note only                | Fix opportunistically  |

**For `concern` / `smell` (code is usually confirmed; uncertainty is about intent):**

|           | `hunch` intent | `likely` intent           | `confirmed` intent      |
|-----------|-----------------|----------------------------|--------------------------|
| **high**  | Stop, ask user before any action | Investigate + clarify before ticket | Ticket immediately       |
| **medium**| Glance; consider ignoring | Backlog with note         | Ticket when capacity     |
| **low**   | Bulk-dismiss OK | Note only                  | Fix opportunistically    |

Drift integration uses `severity` (not `confidence`) for fire thresholds.

### Lifecycle rules

- **Append-only during scan.** scan-init code/db/domain/build/conventions add new entries with `status: open`.
- **Re-scan dedupe.** If a concern with the same `location + question` already exists with `status` in (`open`, `answered`), do NOT re-add. If `dismissed`, may re-add (signal user previously dismissed).
- **User answers via direct edit OR slash command** (future: `/concerns answer <id> <text>`). Sets `status: answered` + fills `answer`, `answered_at`, `answered_by`.
- **Archival on baseline refresh.** During `scan-drift refresh-baseline`, concerns with status `answered`/`dismissed` and `answered_at < baseline.established_at` are moved to `_audits/concerns-archive-<baseline-date>.yaml`.

### Verify integration

`scan-init verify` checks:
1. Every artifact folder has `_concerns.yaml` (file presence — empty list OK).
2. Each open concern's `location` is still valid (file exists; line number within file bounds; table still exists in DB).
3. Concerns referencing files outside `source_globs` → flag for cleanup.

### Drift integration

`scan-drift check` adds a new drift type:
- `type: new_concerns` — fires when scan-init re-runs and produces new entries since baseline. Severity rule (uses concern.severity, NOT concern.confidence):
  - Any new entry with `severity: high` AND `confidence: confirmed` → drift severity `high` (regardless of count)
  - Any new entry with `severity: high` AND `confidence: likely` → drift severity `medium`
  - Else if total new entries > 20 → drift severity `medium`
  - Else if total new entries > 5 → drift severity `low`
  - Else → no drift entry

`hunch`-confidence entries never raise drift severity beyond `low` — they're meant to be reviewed, not to fire alarms.

---

## Baseline + Drift

A baseline is a verified, timestamped snapshot proving "as of this date, every repo in scope was fully converted to v2 layout and every artifact matches its source". Anything that changes after the baseline date is tracked as drift until processed.

### Why

`artifacts.<x>.last_updated` only proves "the artifact file was rewritten on this date". It does NOT prove "every source file as of this date is reflected in the artifact". The baseline answers the second question; without it, `fresh` is just self-declaration.

### `baseline:` block

Written only by `scan-init verify --establish-baseline` after a full verification pass (real fingerprints match, no legacy layout, no `present_unverified` artifacts, schema validators all green). Never touched by routine delta scans.

```yaml
baseline:
  established_at: <iso>
  established_by: "scan-init verify --establish-baseline (run #<n>)"
  status: verified                   # verified | partial | pending_reverify

  scan_init_version: <semver>        # skill version at baseline time

  repos:                             # one entry per repo in scope
    <repo-name>:
      commit: <git-sha>              # HEAD at baseline time
      branch: <branch-name>
      file_count: <int>              # files inside source_globs at baseline

  artifacts_locked:                  # real fingerprints at baseline
    code:        <sha256>
    db:          <sha256>
    domain:
      fingerprint: <sha256>
      schema_version: 2
      entity_count: <int>
    build:       <sha256>
    conventions: <sha256>

  notes: ""                          # free text — what was cleared / migrated
```

**Update rules:**
- Created by `scan-init verify --establish-baseline` only when verify passes 100%.
- Never overwritten by per-artifact scan or delta scan.
- Refreshed (i.e. `established_at` bumped) only by `scan-drift refresh-baseline` after all drift entries are `processed` or `dismissed`.

### `drift_since_baseline:` block

Append-only list. Each entry records a single drift event detected after `baseline.established_at`. Processed entries stay in the list (as audit trail) — they are not deleted.

```yaml
drift_since_baseline:
  - id: drift-<nnn>
    detected_at: <iso>
    type: source_change | skill_change | schema_change
    detail:
      # source_change:
      repo: <repo-name>
      commits_ahead: <int>
      files_changed: <int>
      via: "git log <baseline.commit>..HEAD --name-only"
      # skill_change:
      skill: <skill-name>
      from: <semver>
      to: <semver>
      breaking_changes: [<list of strings>]
      # schema_change:
      artifact: <artifact-name>
      reason: <string>
    severity: low | medium | high
    proposed_action: "<command to resolve>"
    status: open | processed | dismissed
    processed_at: <iso-or-null>
    processed_by: "<command that resolved it>"
```

### Severity rules (deterministic, no AI judgement)

| Drift type | Signal | Severity |
|---|---|---|
| source_change | files_changed < 5 | low |
| source_change | 5 ≤ files_changed ≤ 50 | medium |
| source_change | files_changed > 50 OR contains migration | high |
| skill_change | minor version bump, no breaking_changes | low |
| skill_change | minor version bump with breaking_changes | medium |
| skill_change | major version bump | high |
| schema_change | any | high |

### Status field on `baseline`

| Status | Meaning | When set |
|---|---|---|
| `verified` | Baseline valid; no open drift OR only `low`/`medium` drift entries | After `scan-init verify --establish-baseline` or `scan-drift refresh-baseline` |
| `partial` | Open drift exists but max severity is `medium` | After `scan-drift check` finds medium drift only |
| `pending_reverify` | Open drift with `high` severity exists — full re-scan required | After `scan-drift check` finds any high drift |

`phase_readiness` does not consult `baseline.status` directly (still uses per-artifact `status`), but downstream skills SHOULD warn when `baseline.status: pending_reverify`.

---

## Tier convention

| Tier | Meaning | Producer |
|---|---|---|
| 1 | Auto-fill from source code (no human input) | `scan-init <subcmd>` |
| 2 | Scaffold from source + user confirms semantics | `scan-init <subcmd>` then user edits |
| 3 | Scaffold-only; content grows organically over time | other skills (e.g. `/learn` proposes patterns) |

## Path resolution rules (for all skills)

1. Read `<output_root>/_index.yaml` first. `<output_root>` from `_config/projects.yaml`.
2. For consumer phase X, resolve required artifact paths from `_index.yaml.artifacts[*].path` where `consumer_phases` contains X.
3. Check `phase_readiness[X].ready` before consuming. If false → block per `_shared/pre-flight-protocol.md`.
4. After producing/updating an artifact, write its record back to `_index.yaml.artifacts[<name>]` and recompute `phase_readiness`.

## Anti-patterns

- ❌ Skill reads artifacts by hardcoded path. Always go through `_index.yaml`.
- ❌ Skill writes artifact without updating `_index.yaml`. Master must stay consistent.
- ❌ Add a new artifact category without going through `/learn artifact-gate`.
- ❌ Move output away from `public-project-docs/<project>/`. Layout is canonical.
- ❌ Any skill other than `scan-init verify --establish-baseline` writes to `baseline:`. Use `scan-drift refresh-baseline` to update.
- ❌ Delete entries from `drift_since_baseline`. Append-only — change `status` field instead.
