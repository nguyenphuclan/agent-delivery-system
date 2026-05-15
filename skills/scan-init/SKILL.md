# SKILL: scan-init
Version: 2.1.0
Description: >
  Scan a project and produce structured artifact groups consumed by do-ticket and other skills.
  Supports sub-commands per artifact group. Outputs to public-project-docs/<project>/.
  Stale-checks before each scan; calls live-sync after each write.

**Companion specs (authoritative — do NOT inline here):**
- `surface-layers.md` — 8 mandatory navigation surfaces (S1-S8) + 4 content-coverage rules (C1-C4) every scan emits. Required for agents to answer general questions without re-reading code. Verified by `scan-init verify`. Highlights: S1 features_summary; S2 overloaded_terms registry; S3 subtypes per entity; S4 see_also cross-links; S5 side-by-side comparison artifacts for ≥2-variant concerns; S6 acronyms.yaml glossary; S7 `consumer_resolved:` on topology orphan flags; **S8 lifecycle_traces/<entity>.yaml promoted from DPS findings**; C1 gateway_contract; C2 background_workers per service; C3 feature_flags_catalog; C4 failure-mode template. Empirically derived from (a) the 34-case scan-quality test (28 pass / 6 partial → S1-S7 + C1-C4) and (b) the PROJ-10869 do-ticket-analyze test (80% impact coverage; 3 code-lifecycle traps missed → S8).

---

## Sub-commands

| Command | Produces | Tier |
|---|---|---|
| `scan-init code` | `code/domain_index.yaml` + shards | 1 (auto) |
| `scan-init db` | `db/db_index.yaml` | 1 (auto) |
| `scan-init domain` | `domain/_index.yaml`, `domain/<Entity>.yaml`, `domain/_glossary.yaml`, `domain/_maturity.yaml` | 2 (scaffold + user confirm) |
| `scan-init build` | `build/build.yaml`, `build/run.yaml`, `build/test.yaml` | 1 (auto) |
| `scan-init conventions` | `conventions/git.yaml`, `conventions/ci.yaml`, `conventions/security.yaml` | 1 (auto) |
| `scan-init incidents` | `incidents/incidents.yaml`, `incidents/_concerns.yaml` | 1 (auto) — Jira-sourced |
| `scan-init topology` | `topology/topology.yaml`, `topology/_concerns.yaml` | 1 (auto) — cross-repo + optional infra |
| `scan-init flows` | `flows/flow_index.yaml`, `flows/_concerns.yaml` | 2 (scaffold + user confirm) — business flows (rerouting, indication, sync, etc.) with triggers × effects × known_gates. Consumed by do-ticket Phase 6c flow-gate. |
| `scan-init all` | Runs all sub-commands in order above | — |
| `scan-init verify` | Coverage + schema validation across all artifact groups | 1 (auto) |
| `scan-init verify --establish-baseline` | After verify passes 100% → write `baseline:` block to `_index.yaml` | 1 (auto, gated by verify pass) |
| `scan-drift check` | Detect source/skill/schema drift since baseline → append entries to `drift_since_baseline` | 1 (auto) |
| `scan-drift resolve <drift-id>` | Run the `proposed_action` for a drift entry → mark `status: processed` | 1 (user invokes per entry) |
| `scan-drift refresh-baseline` | After all drift entries are `processed`/`dismissed` → bump `baseline.established_at` to now | 1 (user-confirmed) |

**Write-back artifacts (not produced by scan-init — written by other skills):**
- `patterns/_index.yaml` — bootstrapped by `do-ticket` plan phase auto-induction on first run; accumulates ticket-by-ticket. scan-init only tracks its status in `_index.yaml`.
- `api/gateway_api_docs.yaml` — produced by `scan-api-docs`. scan-init only tracks its status.

`scan-init all` is the first-time onboarding command. Individual sub-commands refresh one artifact group.

---

## Common — Startup & Per-sub-command Pattern

### Resolve output path

```
1. Read active project name from _config/projects.yaml → active
2. Output root: public-project-docs/<project>/
3. Create subfolders if missing: code/ db/ domain/ build/ conventions/ incidents/ topology/
4. Read public-project-docs/<project>/_index.yaml (master registry)
```

### Per-sub-command execution pattern

Invoke with `--force` to skip the stale check and run unconditionally (used by `scan-update`).

**`max_defer_days` per artifact group** (used in stale check step 1):

| Sub-command | max_defer_days | Reason |
|---|---|---|
| code | 7 | Code changes frequently |
| db | 3 | Migrations happen regularly |
| domain | 30 | Domain docs are stable |
| build | 14 | Build config rarely changes |
| conventions | 30 | Conventions very stable |
| incidents | 14 | Bugs are resolved on weekly cadence; daily refresh is overkill |
| topology | 10 | Infra changes slowly, code changes weekly — compromise. Cross-links incidents on every refresh. |
| flows | 30 | Business flows are very stable (rerouting, indication, sync don't change shape often). Re-scan when a major new feature lands or a flow gains a new trigger channel. |

For every sub-command (except `all`):

```
1. STALE CHECK  (skipped when --force)
   Read _index.yaml → artifacts.<sub-cmd>.fingerprint + last_updated
   Compute source fingerprint (see per-sub-cmd section for source_globs)
   If fingerprint matches AND last_updated < max_defer_days → emit "FRESH, skip" and exit

2. EXTRACT
   Run sub-command-specific scan (see below)

3. WRITE ARTIFACT(S)
   Write artifact file(s) to output subfolder
   Increment: never buffer all output, write each file as it completes

4. LIVE-SYNC
   Call: doc-manager live-sync <artifact_path> edit
   (or `create` if new file)

5. UPDATE _index.yaml
   Update artifacts.<sub-cmd>: path, last_updated, fingerprint, status: fresh
   Recompute phase_readiness for all phases that consume this artifact group
```

### scan_state.json location

Each sub-command has its own state file:

| Sub-command | State file |
|---|---|
| code | `code/scan_state.json` |
| db | `db/db_scan_state.json` |
| domain | `domain/domain_scan_state.json` |
| build | `build/build_scan_state.json` |
| conventions | `conventions/conventions_scan_state.json` |
| incidents | `incidents/incidents_scan_state.json` |
| topology | `topology/topology_scan_state.json` |
| flows | `flows/flow_scan_state.json` |

Resume rule: if state file exists with `status: in_progress` → resume from `last_position`. If `status: done` → skip (already fresh, confirmed by stale check).

---

## scan-init code

Analyzes source code structure across all repos in the project. Produces a unified sharded domain index.

**source_globs**: `**/*.cs`, `**/*.ts` (excluding test projects and generated output)

**Output files:**

```
public-project-docs/<project>/code/
  domain_index.yaml                       ← TOC: services + variability_axes + shard manifest
  domain_index_shared.yaml                ← shared lib entities (cross-service)
  domain_index_<service>_<domain>.yaml    ← one per (service, data_domain) pair
  domain_index_<service>_infra.yaml       ← if infra domains exist in a service
  domain_index_cross_cutting.yaml         ← cross-service concerns (auth, logging, events)
  scan_state.json
```

### Multi-repo discovery

**Do not scan `repos_root` as a single tree.** Read `projects.yaml → repos` map → iterate each repo explicitly.

```
repos:
  shared_lib:       acme-shared-lib        ← scan FIRST (others depend on it)
  api_task:         acme-api-task
  api_portal:       acme-api-portal
  identity:         acme-identity
  frontend:         acme-frontend
```

**Scan order (mandatory):**
1. `shared_lib` repo first — entities defined here are referenced by all other repos
2. Backend `.NET` repos — alphabetical within type
3. Frontend Angular repos — last

If `repos` map is absent from `projects.yaml` → fall back to scanning `repos_root` as a single tree (single-repo mode). Log `scan_state.json.mode: single_repo`.

### Directory Exclusion Rules

**Always excluded:**
```
node_modules/  dist/  build/  bin/  obj/  .angular/
coverage/  .git/  .vs/  .idea/  TestResults/
```

**Agent-judged exclusions:** log to `scan_state.json.agent_excluded_dirs` with reason. Exclude auto-generated code, migration snapshots, seed data, static assets, test fixtures.

### Stack detection (per-repo — runs before Phase 1 for each repo)

For each repo in scan order:
1. Read repo root directory (depth 1)
2. Detect stack: `*.csproj`/`*.sln` → .NET backend; `angular.json` → Angular (single or micro-FE)
3. If Angular: read `angular.json → projects` to determine single vs micro-FE per Angular shell/remote detection rules below
4. Log to `scan_state.json.repos[<service_key>].detected_stack`

### Phase 1 — Variability Axis Detection (global — runs across ALL repos before any domain scan)

Must complete before any repo's domain is classified. Run across all repos simultaneously — system-level axes (cluster, module, role, party, run_mode, env) span services.

Answer: *"What dimensions does this system vary across at the product level?"*

**Naming note:** previously called `project_layers` (pre-2026-05-13). Renamed to `variability_axes` — `layer` was confusable with architectural layers (controller/service/repo). An axis is a dimension along which the system's behavior branches. Values along an axis are mutually exclusive at any given runtime point (e.g. one cluster at a time, one party identity at a time).

**Detection patterns:**

| Pattern | Signal | Conclusion |
|---|---|---|
| Repeated conditional variable | `if (cluster === ...)` in >5 places across >3 files | Cluster axis |
| Module/source branching | `if (module === 'X')` | Module axis |
| Role/permission branching | `if (role === 'PO')` | Role axis |
| Group-specific config files | `cluster-A.config.js`, `contractor.config.json` | Confirms/adds an axis |
| Repeated directory structure | `/Modules/Service/Task`, `/Modules/Fulfillment/Task` | Module axis |
| Environment branching (Angular) | `environment.prod.ts`, `if (environment.production)` | Environment axis |
| Route guard / feature flag (Angular) | `canActivate: [RoleGuard]`, `*ngIf="hasFeature('X')"` | Role/feature-flag axis |

**Axis vs business logic:**
```
NOT an axis: if (status === 'open'), if (count > 10), if (isDeleted)    → local scope
IS an axis:  if (cluster === 'A'), if (module === 'X'), if (role === 'Y') → cross-domain behavior
```

**Low-confidence axis guard:** if any axis has `confidence: low` → do NOT proceed to shard assignment. Instead: *"Axis `<name>` detected with low confidence (only N occurrences across M files). Confirm this is a real system axis, or dismiss? (confirm / dismiss)"*. Dismissed axes are excluded from shard assignment.

**Phase 1 output** → `scan_state.json.detected_axes` (global), and `variability_axes` block in `domain_index.yaml`.

### Phase 1.5 — Business vs Technical Classification (per file)

Decides read depth in Phase 2. Business code must be read line-by-line; technical code can be read at signature level.

**Classification heuristic:**

```
Business if ANY of:
  - File path contains: /Modules/, /Domain/, /Services/, /Controllers/, /Features/, /Workflows/, /Handlers/
  - Class name matches an entity in domain/_index.yaml (or any code shard)
  - Class name ends with: Service, Processor, Handler, Workflow, Validator, Specification, Policy
  - File contains state-machine vocabulary in identifiers: Status, Transition, State, Lifecycle
  - Controller endpoint method (HTTP attribute on method)

Technical if ANY of (and NO business signal above):
  - File path contains: /Infrastructure/, /Configuration/, /Startup, /Migrations/, /Mappers/, /Extensions/, /Helpers/, /Utils/
  - Class derives from: Background[Job|Service|Worker], IHostedService, *Middleware, *Factory, *Provider, *Builder
  - File is generated: header starts with "// <auto-generated>", filename matches *.designer.cs, *.g.cs, *.Generated.cs
  - DTO/Model with only public properties (no methods, no logic)

Ambiguous (no clear signal) → treat as business (safer to read deeply).
```

Log each file's classification to `scan_state.json.repos[<service_key>].file_classifications` (only counts, not full list).

### Phase 2 — Domain Scan (per-repo, in scan order)

For each repo:

**Shard target per repo:**
- `shared_lib` repo → all entities go to `domain_index_shared.yaml`
- Other repos → entities go to `domain_index_<service_key>_<data_domain>.yaml`
- Infra/platform concerns in any repo → `domain_index_<service_key>_infra.yaml`
- Auth, event bus, logging patterns appearing in ≥2 repos → `domain_index_cross_cutting.yaml`

**Scan priority by stack (per repo):**

- **.NET**: `/Models` → `/Services` → `/Controllers` → `/Middleware` → `/Utils` → remaining
- **Angular single**: `core` → `shared` → `features`/`modules` → `environments` → remaining
- **Angular micro-FE**: shell → shared-lib → each remote (each using single-app order)

  **Shell vs remote detection** (read `angular.json → projects` before scanning):
  - Project with `architect.build.options.remotes` → **shell/host**
  - Project with `architect.build.options.exposes` → **remote**
  - Project with neither → **shared-lib** (or standalone app — log to scan_state for user review)
  - If no project has `remotes` key → not a micro-FE; fall back to **Angular single** scan order

**Shared lib entity reference:** when scanning non-shared repos, if a class/type is defined in `shared_lib` → note `defined_in: shared` in the domain block instead of re-describing it. Prevents duplication.

**Per-file loop (within per-directory loop):**
1. Apply Phase 1.5 classification (business | technical | ambiguous)
2. Read depth:
   - **Business or ambiguous** → read full file content
   - **Technical** → read class/function signatures only (only deep-read on contradictory signature)
3. While reading, accumulate entries into `code/_concerns.yaml` along the 3 axes from `_shared/agent-docs-layout.md`:

   **For each finding, pick exactly one `type`:**
   - `concern` — cannot infer *business* intent (magic numbers in business logic, conditional branches without rationale, naming that contradicts behavior)
   - `smell` — code works but deviates from technical best practice (`Thread.Sleep` to wait async, manual JSON parsing where `IConfiguration` fits, reinvented stdlib, exception swallowing)
   - `risk` — code runs correctly today but has latent bug (race, missing `OrderBy` on `First()`, retry without backoff, hardcoded limit that won't scale, missing input validation at boundary)
   - `knowledge-gap` — agent cannot trace whole flow (started but couldn't follow across files/services). Use sparingly — for genuine gaps in agent's own understanding, not for things it could trace given more time.
   - `decision-log` — agent saw explicit rationale in code (comment, commit msg referenced via blame, ADR link) explaining an otherwise-weird choice. Record with `status: recorded`.

   **Then set `severity` (consequence if untouched):** `low` / `medium` / `high`
   **Then set `confidence` (agent certainty):** `hunch` / `likely` / `confirmed`

   These three axes are independent — fill each on its own merits. Do NOT collapse confidence into severity.

4. Assign layer based on Phase 1 results
5. Write domain block to correct shard file (incremental — do not buffer)
6. Detect complexity flags (see below — these are structural antipatterns that go into shard files' `complexity_flags`, NOT `_concerns.yaml`. A complexity flag MAY also become a `_concerns.yaml` entry of `type: smell` or `type: risk` if the agent has location-specific judgment — the two systems coexist)

**Per-directory loop:**
1. Run the per-file loop for every file in the directory
2. Move dir: `pending_dirs` → `scanned_dirs`
3. Update `scan_state.json.repos[<service_key>]` **after every directory**
4. Flush `code/_concerns.yaml` after every directory (incremental write)

### Writing concerns during scan

Each scan sub-command writes to `{output_root}/<folder>/_concerns.yaml`:

All sub-commands write to `{output_root}/<folder>/_concerns.yaml` using the schema in `_shared/agent-docs-layout.md`. Per-folder example matrix (`concern` / `smell` / `risk` / `knowledge-gap` / `decision-log`) is in that same doc — do NOT duplicate it here.

| Sub-command | File | Notes |
|---|---|---|
| `scan-init code` | `code/_concerns.yaml` | All 5 types apply; smells and risks dominate in volume |
| `scan-init db` | `db/_concerns.yaml` | `risk` (missing FK, missing index) and `concern` dominate |
| `scan-init domain` | `domain/_concerns.yaml` | `concern` (unclear invariants) and `decision-log` dominate |
| `scan-init build` | `build/_concerns.yaml` | `risk` (port conflicts) and `concern` dominate |
| `scan-init conventions` | `conventions/_concerns.yaml` | `smell` (inconsistency across repos) and `decision-log` dominate |
| `scan-init incidents` | `incidents/_concerns.yaml` | `knowledge-gap` (tickets too thin to extract) and `concern` (recurring pattern detected ≥3 times) dominate |
| `scan-init topology` | `topology/_concerns.yaml` | `risk` (queue not durable, auto-ack + high prefetch, no DLX) and `concern` (orphan queue, dynamic name) dominate |

**Concern entry format** — see `_shared/agent-docs-layout.md` "Per-folder _concerns.yaml" section. All sub-commands MUST use the same schema.

**De-duplication rule:** Before adding a new entry, check if an entry with the same `(location, type, description)` tuple already exists in the file. If it exists with status in (`open`, `answered`, `acknowledged`, `mitigated`, `recorded`) → skip (do not append). If it exists with status in (`dismissed`, `fixed`, `learned`, `superseded`) → MAY re-add (signal that the issue was previously closed but scan re-detected it; could mean regression or decision no longer applies). See `_shared/agent-docs-layout.md` "Re-scan dedupe by status" for the full table.

**Empty file rule:** If a sub-command runs and finds zero concerns, still write `_concerns.yaml` with an empty `concerns: []` list and updated `last_updated`. The file's presence is what verify checks.

**Write `domain_index.yaml` (TOC) LAST** — after ALL repos complete.

### `scan_state.json` — multi-repo structure

```json
{
  "mode": "multi_repo",
  "detected_layers": [],
  "repos": {
    "shared_lib": { "status": "done", "detected_stack": "dotnet", "scanned_dirs": [], "pending_dirs": [] },
    "api_task":   { "status": "in_progress", "detected_stack": "dotnet", "scanned_dirs": [], "pending_dirs": [] },
    "frontend":   { "status": "pending", "detected_stack": null }
  },
  "agent_excluded_dirs": []
}
```

Resume rule: on restart, skip repos with `status: done`; resume `in_progress` repo from its `pending_dirs`; start `pending` repos fresh.

### Shard Assignment (first-match wins, evaluated per entity)

```
1. Repo = shared_lib                                       → shared shard
2. layer: platform + infra type (kafka, k8s, monitoring)   → <service>_infra shard
3. Same pattern in ≥2 repos (auth, events, logging)        → cross_cutting shard
4. layer: cross-cutting                                    → cross_cutting shard
5. layer: module + has parent                              → same shard as parent
6. domain name matches a data_domain keyword               → <service>_<data_domain> shard
7. (default)                                               → <service>_platform shard
```

Data domain keywords = `known_values` of the `module` layer from Phase 1.

### Complexity Detection

Flag any of these when encountered. Never skip, never force-fit — use `UNKNOWN` for anything unclassifiable.

| Type | Symptom | Risk |
|---|---|---|
| `IMPLICIT_STATE` | `save()`/`emit()`/`dispatch()` with unclear side effects | high |
| `TEMPORAL_COUPLING` | init/load/execute must run in order, not enforced by code | high |
| `SHARED_MUTABLE_STATE` | Single object written by multiple files | high |
| `UNSTABLE_SHAPE` | Same field has different types across callers | medium |
| `HIDDEN_CONVENTION` | Pattern repeats but is undocumented | medium |
| `DEEP_DEPENDENCY` | A→B→C→D chain where changing D breaks A | medium |
| `CLUSTER_BRANCH_EXPLOSION` | Nested if/else across cluster/module/role layers | high |
| `OBSERVABLE_SPAGHETTI` | Long switchMap chains, nested subscribes, 3+ combined streams | high |
| `COMPONENT_GOD_OBJECT` | Component >300 lines, mixes HTTP + state + form + UI | medium |
| `CROSS_REMOTE_COUPLING` | Remote imports another remote's internals | high |
| `CROSS_SERVICE_COUPLING` | Service A directly imports classes from Service B (not via shared_lib) | high |
| `UNKNOWN` | Complex but unclassifiable — set `needs_skill_update: true` | unknown |

**Flag structure:**
```yaml
complexity_flags:
  - type: IMPLICIT_STATE
    location: acme-api-task/services/task/processor.cs:47
    symptom: "save() triggers unclear downstream events"
    risk: high
    service: api_task
```

### High-severity complexity_flag — linked_concern mandatory

If a `complexity_flags` entry in any shard has `risk: high`, it MUST have a `linked_concern: <id>` pointing to a `_concerns.yaml` entry. The agent's structural recognition without a location-specific judgment is suspicious at high-risk level.

```yaml
# OK: high risk with linked_concern
- type: IMPLICIT_STATE
  location: Services/SlaPartyUpdater.cs:39
  risk: high
  linked_concern: c-024

# NOT OK: high risk without linked_concern
- type: TEMPORAL_COUPLING
  location: SlaKpi/KpiCalculator.cs
  risk: high
  # ← missing linked_concern → scan-init MUST emit a warning and create a stub _concerns entry
```

`scan-init` emits a warning if any shard has `risk: high` flags without `linked_concern` after the pass. Agent SHOULD create a stub `_concerns.yaml` entry of `type: concern` with `intent_assessment: hunch` for review.

### Cross-shard severity calibration warning

After each scan run, compute per-shard severity distribution:
- `high_pct = #(severity: high) / #(total entries in shard)`
- Across all shards in the project: compute `median_high_pct`, `max_high_pct`, `min_high_pct`.

If `max_high_pct > median_high_pct + 0.20` OR `min_high_pct < median_high_pct - 0.20` → emit warning: severity calibration may be drifting between shards.

Example (acme state on 2026-05-13):
```
  mock:      0% high (0/10)
  scheduler: 15% high (2/13)
  sla:       27% high (3/11)
  median: 15%, max: 27%, min: 0%
  ⚠ max - median = 12% (OK)
  ⚠ median - min = 15% (OK, near threshold)
```

The agent SHOULD note this in `_index.yaml.artifacts.code.calibration_note` so review can decide whether some shards under-flag or others over-flag.

### Modules block — granularity rule

Shard `modules:` block holds entries that have **behavior**. Pure data-model layers and pure delivery-layer entries do NOT belong here — they're already represented by `namespaces:`.

Split modules into two sub-groups for clarity:

```yaml
modules:
  foundation:
    # Cross-cutting infrastructure that other modules depend on.
    # Each entry has behavior (not just data shape) but is not a business module.
    - name: <module-name>
      description: <one-line>
      ...

  business_modules:
    # Modules that implement business behavior. Most concerns hang off these.
    - name: <module-name>
      description: <one-line>
      parent: <foundation-name> | root       # always set; use `root` if top-level
      ...
```

**What does NOT go in `modules:`:**
- `sla-entity-model` (pure data model — already in `namespaces.Mose.Task.Sla.Entities`)
- `api-controllers` (pure delivery — already in `namespaces.<svc>.Controllers`)
- `error-codes`, `infrastructure` (cross-cutting plumbing — already in namespaces)

**What DOES go in `modules:`:**
- `sla-deadline-calculation` — has the rule evaluation behavior
- `email-to-ticket` — has the IMAP/parse/create pipeline
- `domain-event-tracking` — has the MediatR enrichment behavior

**`parent:` field consistency:** if a shard uses `parent:` at all, every entry in `business_modules:` MUST have a `parent:` (use `parent: root` for top-level). Mixed-presence is forbidden — reader cannot tell "missing parent = top-level" from "missing parent = forgot to set".

### Shard file structure — `scan_metadata:` vs `notes:` separation

Every shard file (`code/domain_index_<service>_*.yaml`) MUST have these two distinct blocks at top level:

```yaml
scan_metadata:
  # Machine-readable. Consumed by downstream skills (do-ticket, verify, drift).
  # Do NOT put domain knowledge here.
  reconciled_at: <iso>
  reverified_at: <iso>      # OPTIONAL — set when a later pass re-reads previously-hunch carry-overs
  legacy_source:
    path: <relative-path>   # null if no legacy folder existed
    scan_date: <iso>        # null if no legacy
  deep_read_files: [<filename>, ...]
  carryover_concerns: [<concern-id>, ...]
  partial_reverify: [<concern-id>, ...]
  recommended_tickets: [<concern-id>, ...]   # high-severity confirmed-intent entries from this shard
  unverified_legacy_findings: <int>          # count of legacy_carryover entries from this shard
  severity_distribution:                     # ADDED 2026-05-13 — agent fills at scan time
    high: <int>
    medium: <int>
    low: <int>
    total: <int>
  test_coverage_gaps:
    - concern_id: <id>
      gap: <one-line description>
  followups:                                 # RENAMED 2026-05-13 from cross_repo_followups
    - concern_id: <id>
      scope: in_repo | cross_repo | external_team
      followup: <one-line>
  tag_inventions: [<tag>, ...]               # log new canonical tag candidates (see agent-docs-layout §Canonical tag vocabulary)

notes:
  # Human-readable. Domain insights about how the service works.
  # Reader opens this when they want to understand the service. Should NOT contain scan metadata.
  - <free-form domain note>
```

**Field rationale:**

- `severity_distribution` (added 2026-05-13): agent computes (high/medium/low/total) at write time. Eliminates the need for downstream skills to recount entries when running cross-shard calibration. Required field, even when total=0.
- `followups` (renamed 2026-05-13 from `cross_repo_followups`): the old name implied cross-repo only. In practice the connector pilot showed agents misclassifying in-repo deferrals (e.g. "didn't grep Startup.cs") as cross-repo. The `scope:` field forces the agent to think — `in_repo` means "I could verify but skipped"; `cross_repo` means "another reconciled-or-stub repo needs check"; `external_team` means "needs human + domain knowledge to resolve".
- `reverified_at` (added 2026-05-13): set when a later pass deep-reads previously-hunch carry-overs. SLA reverify pass 2026-05-13 needed this; spec was implicit until then.

**Why separate metadata from notes:** previously both were mixed in `notes:`. Reader looking for domain understanding had to wade through scan metadata. Downstream skills had no machine-readable handle on `recommended_tickets`. SLA review 2026-05-13 forced this split.

### domain_index.yaml (TOC format — multi-repo)

```yaml
# Auto-generated by scan-init v2.0.0 — code sub-command
# Last updated: <ISO>
# Mode: multi_repo

services:
  shared_lib:  acme-shared-lib
  api_task:    acme-api-task
  api_portal:  acme-api-portal
  identity:    acme-identity
  frontend:    acme-frontend

variability_axes:
  - name: cluster
    confidence: high
    detected_via: "if (cluster === ...) found 47 times across 12 files in api_task, api_portal"
    values: [A, B, telco, enterprise]

shards:
  shared:              domain_index_shared.yaml
  cross_cutting:       domain_index_cross_cutting.yaml
  api_task_task:       domain_index_api_task_task.yaml
  api_task_infra:      domain_index_api_task_infra.yaml
  api_portal_portal:   domain_index_api_portal_portal.yaml
  identity_auth:       domain_index_identity_auth.yaml
  frontend_task:       domain_index_frontend_task.yaml
```

### Re-run rules (skill version mismatch)

```
Version mismatch (CASE E):
  Re-run Phase 1 → compare new detected_layers with old
  Unchanged layers → re-evaluate each domain block, show diff, wait for confirm on changes
  Changed layers   → notify user, wait for full-reset confirmation before re-scan
  Write domain_index.yaml only after user confirms
```

---

## scan-init db

Scans the connected database and produces a schema cache. Independent of `scan-init code`.

**source_globs**: `**/*Migration*.cs`, `**/*_migration.sql` (for stale detection only — not read for content)

**Output**: `public-project-docs/<project>/db/db_index.yaml`

### DB scan steps

```
DB-1  List tables
  SELECT tablename FROM pg_tables WHERE schemaname = 'public';
  → write table list to db_scan_state.json, status: in_progress

DB-2  Per-table schema (loop — write db_index.yaml incrementally)
  columns:  SELECT column_name, data_type FROM information_schema.columns
              WHERE table_schema='public' AND table_name='<table>';
  FK:       SELECT kcu.column_name, ccu.table_name, ccu.column_name
              FROM information_schema.key_column_usage kcu
              JOIN information_schema.referential_constraints rc ON kcu.constraint_name = rc.constraint_name
              JOIN information_schema.constraint_column_usage ccu ON rc.unique_constraint_name = ccu.constraint_name
              WHERE kcu.table_name = '<table>';
  indexes:  SELECT indexname FROM pg_indexes WHERE tablename='<table>';

DB-3  Enums
  SELECT t.typname, e.enumlabel FROM pg_type t
    JOIN pg_enum e ON t.oid = e.enumtypid
    JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'public' ORDER BY t.typname, e.enumsortorder;

DB-4  Views
  SELECT viewname FROM pg_views WHERE schemaname = 'public';
  → infer source_tables from view definition
  → update db_scan_state.json status: done
```

No sample data. No stored procedures. No trigger bodies. Schema only.

### db_index.yaml format

```yaml
# Auto-generated by scan-init v2.0.0 — db sub-command
# Last updated: <ISO>
# Connection: <host>/<db_name>  (no credentials stored)

tables:
  task:
    columns:
      id: uuid
      status: varchar
      cluster_id: int
    fk:
      cluster_id: cluster.id
    indexes: [status, cluster_id]

enums:
  task_status: [open, in_progress, done, cancelled]

views:
  v_task_summary:
    source_tables: [task, user, cluster]
```

### Auto-stale warning

Any skill reading `db_index.yaml` must check: if any migration file has mtime newer than `db_index.yaml.last_updated` → emit: "`db_index.yaml` may be stale — new migration detected. Run `scan-init db`."

---

## scan-init domain

Scaffolds entity-level domain knowledge files from C# entity classes and EF DbContext. Tier 2 — agent proposes, user confirms each entity before write.

**source_globs**: `**/*Entity.cs`, `**/*DbContext.cs`, `**/*Model.cs` (C# projects)

**Output**: `public-project-docs/<project>/domain/`

```
domain/
  _index.yaml          ← entity registry + maturity summary
  _glossary.yaml       ← term → definition (cross-entity)
  _maturity.yaml       ← invariant maturity tiers
  <EntityName>.yaml    ← one per entity (e.g. TaskEntity.yaml)
```

### Extraction steps

```
D-1  Discover entities
  Glob source_globs → collect class names + file paths
  For each entity class: read fields, constructor, state transitions (if any)

D-2  Scaffold per-entity file (Tier 2 — propose before writing)
  Show user: entity name, field list, detected state machine (if any), detected invariants
  Wait for user: "ok" → write; "skip" → skip; "edit X" → apply edit then write

D-3  Build _glossary.yaml from entity field names + domain-specific terms
  Auto-detect terms: fields appearing in >3 entity files
  Propose glossary entries → user confirms batch

D-4  Scaffold _maturity.yaml
  Tier 1 (auto-enforced in code): invariants with a validation attribute or explicit check in constructor
  Tier 2 (convention only): comments or naming patterns
  Tier 3 (implicit): inferred from usage, no enforcement found

D-5  Write _index.yaml with entity list + maturity summary
```

### Entity YAML format

```yaml
# Auto-generated by scan-init v2.0.0 — domain sub-command
entity: TaskEntity
source: Modules/Task/Models/TaskEntity.cs
last_updated: <ISO>

fields:
  id: uuid
  status: task_status (enum)
  cluster_id: int (FK → cluster)

state_machine:
  states: [Open, InProgress, Done, Cancelled, Denied]
  transitions:
    - from: Open
      to: [InProgress, Cancelled]
      trigger: AcceptTask / CancelTask
  notes: ""

invariants:
  - id: INV-001
    description: "Task cannot transition from Done to any state"
    maturity: tier1
    enforced_at: TaskEntity constructor line 42

lifecycle:
  created_by: TaskService.CreateAsync
  deleted_by: soft-delete only (IsDeleted flag)
```

---

## scan-init build

Extracts build, run, and test configuration from project files. Fully automatic.

**source_globs**: `**/*.csproj`, `**/package.json`, `**/launchSettings.json`, `**/docker-compose*.yml`, `**/appsettings*.json`

**Output**: `public-project-docs/<project>/build/`

```
build/
  build.yaml       ← per-repo build command + output dir
  run.yaml         ← services, ports, dependencies
  test.yaml        ← test projects, run commands, base classes
  build_scan_state.json
```

### Multi-repo grouping

Read `projects.yaml → repos` map to resolve which repo each file belongs to. Match each discovered file's path against the repo directory name to assign its `service_key`. Fall back to directory heuristics if `repos` map is absent.

Group `build.yaml` entries by `service_key`. Group `test.yaml` entries by `service_key`. Consolidate `run.yaml` services from all repos into a single `services:` block (docker-compose at `repos_root` level takes priority; per-repo `launchSettings.json` fills gaps).

### Extraction logic

**build.yaml** — from `*.csproj` / `package.json` (grouped by repo):
```yaml
repos:
  acme-api-task:
    stack: dotnet
    build_cmd: "dotnet build src/TaskApi.csproj"
    output_dir: bin/Release/net8.0/
    target_framework: net8.0
  acme-frontend:
    stack: angular
    build_cmd: "npm run build --project=acme-client"
    output_dir: dist/acme-client/
```

**run.yaml** — from `launchSettings.json` + `docker-compose.yml`:
```yaml
services:
  task-api:
    port: 5001
    profile: "TaskApi"
    depends_on: [postgres, redis]
  identity-provider:
    port: 5002
    profile: "IdentityProvider"
    depends_on: [postgres]
```

**test.yaml** — from `*.Tests.csproj` + test class base class detection (flat list, `repo` field for attribution):
```yaml
test_projects:
  - project: TaskApi.Tests
    repo: acme-api-task
    run_cmd: "dotnet test src/TaskApi.Tests/TaskApi.Tests.csproj"
    base_class: RunTestWithPostgres
    uses_real_db: true
    test_count_approx: 47
  - project: PortalApi.Tests
    repo: acme-api-portal
    run_cmd: "dotnet test src/PortalApi.Tests/PortalApi.Tests.csproj"
    base_class: RunTestWithPostgres
    uses_real_db: true
    test_count_approx: 23
```

---

## scan-init conventions

Extracts git, CI, and security conventions. Fully automatic.

**source_globs**: `.git/config`, `.github/workflows/*.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `**/.editorconfig`

**Output**: `public-project-docs/<project>/conventions/`

```
conventions/
  git.yaml            ← branch prefix, commit format, hotfix prefix
  ci.yaml             ← CI provider, workflow paths, PR template location
  security.yaml       ← secret regex patterns, auth endpoint patterns
  conventions_scan_state.json
```

### Extraction logic

**git.yaml** — from `.git/config` + branch name heuristics:
```yaml
branch:
  feature_prefix: ""          # acme uses bare ticket IDs, no prefix
  hotfix_prefix: "hotfix/"
  main_branch: master
  protected_branches: [master, main]
commit:
  format: "conventional"      # detected from recent git log
  scope_required: false
```

**ci.yaml** — from `.github/workflows/` (check each repo directory; consolidate):
```yaml
provider: github-actions
repos:
  acme-api-task:
    workflows:
      - name: build-and-test
        path: acme-api-task/.github/workflows/build.yml
        triggers: [push, pull_request]
        runs_on: ubuntu-latest
  acme-frontend:
    workflows:
      - name: ng-build
        path: acme-frontend/.github/workflows/ng-build.yml
        triggers: [push, pull_request]
        runs_on: ubuntu-latest
pr_template: .github/PULL_REQUEST_TEMPLATE.md    # from any repo that has it
version_bump_strategy: "feat/* branch → minor; PROJ-* → patch"
```

If all repos share the same workflow file (monorepo-style): collapse into a single `workflows:` block without per-repo grouping.

**security.yaml** — regex scan across source files (names only, not content):
```yaml
secret_patterns:
  - regex: "(password|secret|apikey|token)\\s*=\\s*['\"][^'\"]{8,}"
    description: "Hardcoded credential pattern"
auth_endpoints:
  - pattern: "/api/auth/*"
  - pattern: "/connect/token"
```

---

## scan-init incidents

Auto-mines resolved Jira bug/hotfix tickets into a structured incident library. Agent reads this **before** forming hypotheses on any bug-class ticket.

**Source**: Jira via MCP (`searchJiraIssuesUsingJql` + `getJiraIssue`). NOT file-based.

**Output**:
```
public-project-docs/<project>/incidents/
  incidents.yaml                  ← master list (tier 1 + tier 2 merged)
  _concerns.yaml                  ← agent observations during mining
  incidents_scan_state.json
```

### Sub-command signature

```
scan-init incidents [--tier1-only | --include-deep-archive] [--force]
```

- Default: tier 1 (last 12 months) FULL extraction
- `--include-deep-archive`: also mine tier 2 (12-24 months) with SHALLOW extraction
- `--tier1-only`: explicit opt-out of tier 2 (same as default; flag exists for clarity)
- `--force`: skip stale check

**Note**: tier 2 implementation is staged — initial release ships tier 1 only. Pass `--include-deep-archive` after tier 2 support lands. Sections marked `[TIER 2 — not yet implemented]` below are spec-only.

### Required config (read from `_config/projects.yaml`)

```yaml
projects:
  <name>:
    jira:
      cloud_id: <site>.atlassian.net           # required
      project_key: <KEY>                       # required
      incident_components: [...]               # optional — empty = all components
      valid_resolutions: [Done, Fixed]         # optional, default shown
      incident_issue_types: [Bug, Hotfix, Incident]  # optional, default shown
```

If `jira:` block is missing → emit error "scan-init incidents requires `jira:` block in projects.yaml" and exit. Do not fall back to mining without auth.

### JQL queries

**Tier 1 (12 months, FULL extraction)**:
```
project = "<project_key>"
AND issuetype in (<incident_issue_types>)
AND status in (Done, Closed, Resolved)
AND resolution in (<valid_resolutions>)
AND resolved >= -365d
ORDER BY resolved DESC
```

If `incident_components` is non-empty, append: `AND component in (<list>)`.

**Tier 2 (12-24 months, SHALLOW extraction) — [TIER 2 — not yet implemented]**:
```
project = "<project_key>"
AND issuetype in (<incident_issue_types>)
AND resolved >= -730d AND resolved < -365d
AND (priority in (High, Critical, Blocker) OR labels = "recurring" OR labels = "hotfix")
ORDER BY resolved DESC
```

### Extraction algorithm

```
I-1  Read projects.yaml → jira config. If missing → error and exit.

I-2  STALE CHECK (skipped when --force)
     Read _index.yaml → artifacts.incidents.fingerprint + last_updated
     Compute current fingerprint (see "Fingerprint" below)
     If matches AND last_updated < 14 days → emit "FRESH, skip" and exit

I-3  RESUME CHECK
     Read incidents/incidents_scan_state.json (if exists)
     If status == in_progress → resume from last_processed_key
     Else fresh start.

I-4  TIER 1 EXTRACTION (paginated, 50/page)
     Page through JQL results using searchJiraIssuesUsingJql.
     For each ticket key in page:
       I-4.1  If key in incidents.yaml AND ticket.updated matches stored → skip (already extracted)
       I-4.2  Fetch full ticket via getJiraIssue(responseContentFormat: markdown)
       I-4.3  Combine description + all comment bodies → context
       I-4.4  If len(context) < 200 chars:
                Append to scan_state.skipped_thin: [key]
                Append _concerns.yaml entry of type=knowledge-gap (see template)
                Continue to next ticket
       I-4.5  Run LLM extraction with prompt in §"Extraction prompt" below
       I-4.6  Append extracted entry to incidents.yaml (tier: 1)
       I-4.7  Update scan_state.json: last_processed_key, status: in_progress
       I-4.8  Every 10 tickets → flush incidents.yaml to disk (no buffering)

I-5  TIER 2 EXTRACTION (only if --include-deep-archive)
     [TIER 2 — not yet implemented]
     When implemented: same loop, but use shallow-extraction prompt and write tier: 2 entries.

I-6  BUILD INDEXES (run after all extraction)
     Read full incidents.yaml back.
     Compute three index blocks:
       indexes.by_component:     map component → [ticket_id, ...]
       indexes.by_keyword:       union of similar_pattern_keywords across tier-1 entries
       indexes.by_fix_layer:     map {code, infra, external, hybrid} → [ticket_id, ...]
       indexes.high_recurrence_risk: [ticket_id, ...]  where recurrence_risk == high
     Rewrite incidents.yaml with indexes block appended.

I-7  PATTERN DETECTION → concerns
     For each keyword appearing in ≥3 tier-1 entries:
       Append _concerns.yaml entry of type=concern:
         "Pattern '<kw>' appears in N tickets — consider heuristics/<area>.md write-up"
     For each fix_layer == infra count >= 3:
       Append _concerns.yaml entry: "Infra-layer fixes recurring — topology.yaml may help locate root cause"

I-8  WRITE _index.yaml UPDATE
     artifacts.incidents: { path, last_updated: now, fingerprint, status: fresh,
                            tier1_count: N, tier2_count: M, jira_project: KEY,
                            required_by: [], optional_for: [5, 6, 7, 9] }
     Recompute phase_readiness.

I-9  LIVE-SYNC
     Call: doc-manager live-sync incidents/incidents.yaml edit|create
     Call: doc-manager live-sync incidents/_concerns.yaml edit|create

I-10 MARK DONE
     scan_state.json.status = done
```

### Extraction prompt (tier 1)

Used in step I-4.5. The agent runs this prompt over each ticket's context.

```
You are extracting structured incident knowledge from a resolved Jira ticket.

INPUT:
  Ticket: <key>
  Title: <summary>
  Resolution: <resolution>
  Components: <components>
  Priority: <priority>
  Description: <description>
  Comments (chronological): <comments>

TASK: extract the following fields. Output VALID YAML matching the schema below.
If a field cannot be determined from the ticket text, write `null` (do NOT fabricate).

FIELDS:
  symptom_1line: One sentence describing what users/system observed. NOT the cause.
  root_cause: 2-4 sentences explaining the underlying mechanism. If the ticket
              never explains the root cause, write "Not stated in ticket".
  root_cause_1line: One sentence summary of root_cause.
  fix_layer: Where the fix lived — one of:
    - code: app source code change
    - infra: config, IaC, k8s manifest, broker/DB settings, deploy yaml
    - external: vendor / 3rd-party API / customer-side change
    - hybrid: code change PLUS one of the above
  fix_summary: 2-3 sentences describing what changed. null if unclear.
  fix_commit: SHA or PR link if explicitly mentioned in comments/description.
  fix_repos: List of repo names mentioned in the ticket text. Empty list if none.
  recurrence_risk: One of:
    - high: root cause is structural/architectural (will re-occur unless redesigned)
    - medium: config drift could re-introduce
    - low: one-off (typo, bad data, specific user error)
  related_tickets: List of ticket keys referenced in ticket text (e.g. "see PROJ-9701").
  similar_pattern_keywords: 3-8 LOWERCASE keywords future agents could grep.
    Prefer domain terms (rabbitmq, ack, deadlock, prefetch) over generic (bug, error).
  lessons: 1-3 bullets, each in form "<noun phrase> — <what's surprising/non-obvious>".
    Skip entirely (empty list) if no genuine lesson; do not pad.
  confidence: One of:
    - confirmed: root cause clearly stated + fix clearly identified
    - likely: inferred from comments but text supports it
    - hunch: extraction is best guess; ticket was ambiguous

CONSTRAINTS:
  - Better to set confidence=hunch and write null than to fabricate.
  - If the ticket was reopened/discussed extensively in comments, the FINAL comment's
    explanation usually has the real root cause — weight it more than the description.
  - similar_pattern_keywords must be valuable for grep — skip generic words.

OUTPUT FORMAT (YAML, no other text):
  symptom_1line: <...>
  root_cause: <...>
  root_cause_1line: <...>
  fix_layer: <code | infra | external | hybrid>
  fix_summary: <...>
  fix_commit: <... or null>
  fix_repos: [<...>]
  recurrence_risk: <high | medium | low>
  related_tickets: [<...>]
  similar_pattern_keywords: [<...>]
  lessons:
    - <...>
  confidence: <confirmed | likely | hunch>
```

### incidents.yaml schema

```yaml
# Auto-generated by scan-init v2.x.x — incidents sub-command
# Last updated: <ISO>
# Project: <project_key>
# Tier 1 window: -365d
# Tier 2 window: -730d to -365d   (only if --include-deep-archive ran)
# Total entries: <N>  (tier1: <n1>, tier2: <n2>)

incidents:
  - id: <PROJECT>-<num>
    tier: 1                         # 1 = full extraction, 2 = shallow (deep archive)
    resolved_at: <YYYY-MM-DD>
    components: [<...>]
    labels: [<...>]
    priority: <Normal | High | Critical | Blocker>
    issuetype: <Bug | Hotfix | Incident>
    jira_updated: <ISO>              # used for re-scan dedupe (skip if unchanged)

    summary: <ticket title>
    symptom_1line: <...>
    root_cause: |
      <multi-line root cause>
    root_cause_1line: <...>

    fix_layer: <code | infra | external | hybrid>
    fix_summary: <...>
    fix_commit: <sha or PR url or null>
    fix_repos: [<...>]

    recurrence_risk: <high | medium | low>
    related_tickets: [<...>]
    similar_pattern_keywords: [<lowercase, ...>]
    lessons:
      - <noun phrase — what's non-obvious>

    confidence: <confirmed | likely | hunch>

# ───── INDEXES (rebuilt at end of every scan run) ─────
indexes:
  by_component:
    <Component>: [<ticket_id>, ...]

  by_keyword:
    <keyword>: [<ticket_id>, ...]

  by_fix_layer:
    code:     [<...>]
    infra:    [<...>]
    external: [<...>]
    hybrid:   [<...>]

  high_recurrence_risk: [<ticket_id>, ...]
```

### Fingerprint

```
1. Run lightweight JQL count query for tier 1 window:
     project = "<key>" AND issuetype in (...) AND status in (Done, Closed, Resolved)
     AND resolution in (<valid_resolutions>) AND resolved >= -365d
   → get list of (key, updated) tuples
2. fingerprint = sha256(sorted("<key>:<updated>" for each tuple))
```

Stale = new ticket resolved OR existing ticket re-updated since last scan.

### _concerns.yaml entries (specific to incidents)

Use the same schema as other folders (see `_shared/agent-docs-layout.md`). Dominant types for this folder:

**Template — thin ticket**:
```yaml
- id: c-<n>
  type: knowledge-gap
  location: jira:<PROJECT>-<num>
  description: "Ticket body + comments under 200 chars — could not extract structured incident"
  severity: low
  confidence: confirmed
  status: open
```

**Template — recurring pattern (built in step I-7)**:
```yaml
- id: c-<n>
  type: concern
  location: incidents.yaml
  description: "Keyword '<kw>' appears in <N> tier-1 incidents — consider authoring heuristics/<area>.md"
  severity: medium
  confidence: likely
  status: open
  related_tickets: [<ids>]
```

**Template — infra-layer recurrence**:
```yaml
- id: c-<n>
  type: concern
  location: incidents.yaml
  description: "<N> tier-1 fixes were infra-layer. Topology mapping may surface root causes earlier."
  severity: medium
  confidence: likely
  status: open
```

### scan_state.json structure

```json
{
  "status": "in_progress",
  "started_at": "<ISO>",
  "tier1": {
    "jql_total": 137,
    "processed_count": 42,
    "last_processed_key": "PROJ-9876",
    "skipped_thin": ["PROJ-9810", "PROJ-9722"],
    "extraction_errors": []
  },
  "tier2": {
    "enabled": false
  }
}
```

### Edge cases & decisions

| Case | Handling |
|---|---|
| `jira:` block missing in projects.yaml | Error + exit (no silent fallback) |
| Ticket fetched but description + comments < 200 chars | Skip, append knowledge-gap concern |
| Ticket resolved as Duplicate / Won't Fix / Cannot Reproduce / Incomplete | Filtered at JQL level (won't be fetched) |
| MCP tool rate-limit / 429 | Backoff 30s, retry up to 3x. On final failure → set status: in_progress, save progress, exit with message "Resume with `scan-init incidents` to continue" |
| Same ticket already in incidents.yaml with same `jira_updated` | Skip (incremental scan) |
| Same ticket already in incidents.yaml but `jira_updated` differs | Re-extract, overwrite entry |
| Multiple tickets with same root cause (linked cluster) | Each gets own entry; relationship captured via `related_tickets` |
| Ticket text mentions Slack/Confluence link as "real" context | Extract what's in ticket; mark `confidence: hunch`; note in `lessons` that context is external |
| `priority` field null | Treat as Normal; tier-2 filter won't pick it up anyway |
| `components` list null/empty | Set components: []; entry still valid, won't appear in by_component index |

### What scan-init incidents must NEVER do

- Write to incidents.yaml without LLM extraction (no shortcut paths)
- Skip the confidence field — extraction quality is critical for downstream usage
- Re-fetch already-extracted tickets unless `jira_updated` differs (waste)
- Fabricate root_cause when the ticket doesn't explain — write "Not stated in ticket" or null
- Run without `jira:` block in projects.yaml (silently degrading is misleading)

---

## scan-init topology

Builds a cross-repo messaging map: queues, publishers, consumers, queue infrastructure config (when available), dashboards. Closes the "messaging bug needs to look at 4 repos at once" blind spot.

**Source**: app code repos (always) + infra repos (optional — Helm, Terraform, k8s, Grafana). Cross-references `incidents.yaml` for queue↔incident links.

**Output**:
```
public-project-docs/<project>/topology/
  topology.yaml                  ← unified map: queues × {publishers, consumers, declared_in, dashboards, health_flags, cross_links}
  _concerns.yaml                 ← agent observations during scan
  topology_scan_state.json
```

### Sub-command signature

```
scan-init topology [--app-only] [--force]
```

- Default: scan app code + infra repos (if configured)
- `--app-only`: skip infra repos even if configured (faster, less complete)
- `--force`: skip stale check

### Required config (read from `_config/projects.yaml`)

```yaml
projects:
  <name>:
    repos:                  # required — app code repos
      <alias>: <repo-folder-name>
      ...
    infra_repos:            # optional — if all entries null, runs in app-only mode
      helm: <entry>
      terraform: <entry>
      k8s: <entry>
      dashboards: <entry>
    messaging:              # required for app-side scan
      brokers: [rabbitmq, kafka, sqs, servicebus]
      client_libs: [MassTransit, EasyNetQ, RawRabbitMQ.Client, ...]
      extra_attribute_patterns: []   # optional — custom regex
```

Each `<entry>` in `infra_repos` accepts THREE forms:
1. **null / omitted** → not configured, skipped silently
2. **String** (`"folder-name"`) → relative to `paths.repos_root` (`<repos_root>/<folder-name>`)
3. **Map** (`{ path: "<abs>", scan_subdir: "<rel>" }`) → absolute path, optionally restrict scan to a subdirectory (e.g. multi-env deploy repos where `uat/` is the test slice)

**Resolution logic per entry**:
```
if entry is null → skip
if entry is string → resolved_path = repos_root + "/" + entry
                     scan_root = resolved_path
if entry is map  → resolved_path = entry.path  (treated as absolute if it contains / or starts with drive letter)
                   scan_root = resolved_path + "/" + entry.scan_subdir (if scan_subdir set)
                              else resolved_path
```

**The same repo path MAY appear under multiple keys** — common pattern for monorepo deploys that bundle k8s manifests + helm values together. Set both `k8s` and `helm` to the same path; topology dedupes file lists before grep.

If `messaging:` block is missing → emit error "scan-init topology requires `messaging:` block in projects.yaml" and exit.

If `infra_repos:` is missing OR all 4 entries are null → log warning "infra_coverage: none — topology will not capture queue config" and proceed in app-only mode.

**Path validation per entry (Phase 2 start)**:
- If `resolved_path` does not exist on disk → log to `extraction_errors[]`, skip that entry, continue
- If `scan_subdir` set but `<resolved_path>/<scan_subdir>` does not exist → same — error + skip
- If two keys point to same resolved scan_root → scan once, attribute findings to both keys in output

### Extraction algorithm

```
T-1  Read projects.yaml. Validate messaging: block. Detect infra mode:
       infra_mode = "full"  if at least 1 infra_repo has non-null value
                    "none"  if all null or block absent

T-2  STALE CHECK (skipped when --force)
     Compute current fingerprint (see "Fingerprint" below)
     If matches AND last_updated < 10 days → emit "FRESH, skip" and exit

T-3  RESUME CHECK
     Read topology/topology_scan_state.json (if exists)
     If status == in_progress → resume from last_phase
     Else fresh start.

T-4  PHASE 1 — App-side scan (per repo in projects.yaml.repos)
     For each repo in repos:
       Determine repo_root = paths.repos_root + "/" + <repo-folder-name>
       For each *.cs file under repo_root (exclude bin/, obj/, **/Tests/, **/*Tests.cs):
         Grep for client_lib-specific patterns (see "Client lib grep patterns" below)
         For each match:
           Extract queue_name (from string literal, [Queue(...)] attribute, or
             const QueueName binding — see "Queue name extraction" below)
           Classify as publisher or consumer based on call site
           Capture surrounding attributes:
             - Publisher: confirm_mode, mandatory flag, batch size
             - Consumer: ack_mode, prefetch, concurrency, retry policy
             - Queue declaration (if [Queue] attribute on class or in startup)
       Append findings to internal map: queues[<name>].published_by[] / consumed_by[]

     If queue_name cannot be resolved statically (e.g. interpolated string) → add to
       scan_state.dynamic_queue_names with file:line + reason

T-5  PHASE 2 — Infra-side scan (skipped if --app-only or infra_mode == "none")
     Resolve each non-null infra_repos entry per "Resolution logic per entry" above.
     Validate path exists; log to extraction_errors and skip if missing.
     Build a deduplicated set of (key, scan_root) pairs — if helm and k8s point
     to the same scan_root, mark as multi-key but scan files once.

     For each unique scan_root:
       Walk all *.yaml, *.yml, *.json files under it (exclude .git/, node_modules/).
       For each file, run multiple greps in parallel (don't pre-classify by entry key
       — same file may contain helm values AND k8s deployment in one bundled repo):

       Helm-style patterns (helm chart values.yaml, templates/*.yaml, *-helm-values.yaml):
         Grep for: kind: Queue, rabbitmq.queues.<name>:, rabbitmq.config.queues,
                   queues:\n  - name: <name>, queue_definitions
         Extract: durability, ttl, dlx, max_length, x-message-ttl, auto_delete
         Locate file:line for each declaration

       Terraform patterns (*.tf only):
         Grep for: resource "rabbitmq_queue", resource "aws_sqs_queue",
                   resource "google_pubsub_topic", resource "aws_sns_topic"
         Extract config fields per resource type

       k8s patterns (all *.yaml under scan_root):
         Grep for: kind: ConfigMap with RabbitMQ-related keys
         Grep for: kind: Secret with broker URLs (RABBITMQ_URI, AMQP_URL, etc.)
         Grep for: kind: Deployment env vars referencing queue name patterns
                   (UPPER_SNAKE_CASE tokens matching queue names from Phase 1)
         Grep for: kind: ServiceMonitor / PrometheusRule referencing queues
         Grep for: kind: CronJob with broker-related env vars

       Grafana dashboards (*.json):
         Read JSON, extract targets[].expr for Prometheus queries
         Grep for queue names within metric labels (e.g. rabbitmq_queue="...")
         Map dashboard file → queue names it references

     For each declaration found:
       Match queue_name against queues map from Phase 1
       Add to queues[<name>].declared_in[] with:
         - extracted config
         - source_entry_keys: list of infra_repos keys whose scan_root contains this file
           (e.g. ["helm", "k8s"] when same repo declared under both)
       Or queues[<name>].related_dashboards[] for Grafana entries

T-6  PHASE 3 — Cross-link analysis
     For each queue in queues map:
       If has publishers AND consumers AND declared_in → status: complete
       If publishers only, no consumers → orphans.declared_no_consumer
       If consumers only, no publishers → orphans.declared_no_publisher
       If app-side queue but no infra declaration AND infra_mode != "none"
         → orphans.code_no_infra

T-7  PHASE 4 — Health flag generation (per queue)
     Apply rules from "Health flag rules" table below.
     Append each flagged issue to queue's health_flags[] list AND mirror
     high-severity flags to topology/_concerns.yaml as type=risk entries.

T-8  PHASE 5 — Incidents cross-link (skipped if incidents.yaml missing)
     Read public-project-docs/<project>/incidents/incidents.yaml
     For each queue in queues map:
       Search incidents[].similar_pattern_keywords for queue_name lowercased
       Search incidents[].root_cause + symptom_1line for queue_name (case-insensitive substring)
       Collect matching ticket IDs → queues[<name>].cross_links.incidents[]
     For each queue with ≥1 incident cross-link AND a high-severity health_flag:
       Bump that health_flag's severity to high if currently medium
       (real-world history of incidents validates the architectural concern)

T-9  WRITE topology.yaml
     Top-level header comment includes: project, infra_mode, generated_at, total_queues
     Sections:
       queues:              (per-queue full record)
       publishers_index:    (class → queues map for fast lookup)
       consumers_index:     (class → queues map for fast lookup)
       orphans:             (declared_no_publisher / declared_no_consumer / code_no_infra)
       dynamic_queue_names: (unresolved dynamic queue names from scan_state)

T-10 WRITE/UPDATE _index.yaml
     artifacts.topology: { path, last_updated, fingerprint, status: fresh,
                           queue_count: N, high_severity_flags: M, infra_coverage: <mode>,
                           required_by: [], optional_for: [5, 6, 7, 9] }
     Recompute phase_readiness.

T-11 LIVE-SYNC
     Call: doc-manager live-sync topology/topology.yaml edit|create
     Call: doc-manager live-sync topology/_concerns.yaml edit|create

T-12 MARK DONE
     scan_state.json.status = done
```

### Client lib grep patterns

| Library | Publisher patterns | Consumer patterns | Queue name source |
|---|---|---|---|
| MassTransit | `IPublishEndpoint\.Publish<\w+>` <br> `await.*Publish<\w+>\(` <br> `ConsumerDefinition<\w+>` | `class \w+ : IConsumer<\w+>` <br> `IConsumer<\w+>\.Consume` | Endpoint config: `endpoint\.ConfigureConsumer<\w+>` <br> Type name as fallback |
| EasyNetQ | `IBus\.PubSub\.Publish` <br> `bus\.PubSub\.PublishAsync` | `IBus\.PubSub\.Subscribe<\w+>` <br> `bus\.PubSub\.SubscribeAsync` | First string-literal arg, OR `subscriptionId` parameter |
| RawRabbitMQ.Client | `IModel\.BasicPublish\(` <br> `channel\.BasicPublish\(` | `IModel\.BasicConsume\(` <br> `channel\.BasicConsume\(` | First string-literal arg, OR `[Queue\("<name>"\)]` attribute on class |
| Generic (any) | — | — | `const string QueueName = "<name>"` <br> `RabbitMqOptions\.QueueName = "<name>"` |

Plus patterns from `messaging.extra_attribute_patterns` in projects.yaml.

### Queue name extraction (per match)

```
Order of preference (first hit wins):
  1. String literal in call: BasicPublish("SYNC_AC_INFO_JOB", ...)
  2. [Queue("...")] attribute on the class containing the call
  3. const string QueueName = "..." in same class
  4. RabbitMqOptions binding in startup (Configure<RabbitMqOptions>(...))
  5. Variable reference — TRACE back one level (single-file scope only)
  6. Cannot resolve → log to dynamic_queue_names with file:line + reason
```

Do NOT attempt cross-file variable tracing — it's high-risk and slow. Log dynamic names instead.

### Consumer attribute extraction (when found)

```
ack_mode:
  - [Consumer(AckMode = AckMode.Manual)] → "manual"
  - [Consumer(AckMode = AckMode.Auto)] → "auto"
  - services.Configure<RabbitMqOptions>(o => o.AutoAck = true) → "auto"
  - No marker → "default-by-lib" (MassTransit defaults to manual; EasyNetQ defaults to auto)

prefetch:
  - PrefetchCount = <N> → N (int)
  - services.Configure(o => o.PrefetchCount = <N>) → N
  - No marker → "default-by-lib" (annotate with lib's default in comment)

concurrent:
  - ConcurrentConsumers = <N>, .Concurrency(<N>) → N

retry_policy:
  - Polly Policy.Handle<X>().Retry(N) near consumer → "retry N times"
  - Polly Policy.Handle<X>().WaitAndRetry(...) → "wait and retry with backoff"
  - try/catch + manual re-publish on serialization error → "manual republish on <type>, no backoff"
  - No marker → null
```

### topology.yaml schema

```yaml
# Auto-generated by scan-init v2.x.x — topology sub-command
# Last updated: <ISO>
# Project: <name>
# Infra mode: full | partial | none
# Brokers: [<from messaging.brokers>]
# Total queues: <int>
# Total high-severity health_flags: <int>

queues:
  SYNC_AC_INFO_JOB:
    broker: rabbitmq

    published_by:
      - repo: acme-api-task
        class: SyncAcPassiveEndpointJob
        location: src/Jobs/SyncAcPassiveEndpointJob.cs:42
        publish_method: BatchPublishAsync
        attributes:
          confirm_mode: not_set         # not_set | required | optional
          mandatory: false

    consumed_by:
      - repo: acme-api-task
        class: SyncAcInfoJobQueueFlow
        location: src/Consumers/SyncAcInfoJobQueueFlow.cs:18
        attributes:
          ack_mode: auto                # manual | auto | default-by-lib
          prefetch: 50                  # int or "default-by-lib"
          concurrent: 4                 # int or null
          retry_policy: "retry on 40001, no backoff"

    declared_in:                        # populated only if infra_mode != "none"
      - repo: acme-infra-helm
        path: charts/rabbitmq/values.yaml
        line: 47
        durability: false
        ttl: null
        dlx: not_configured
        max_length: null
        x_message_ttl: null
        auto_delete: false

    related_dashboards:                 # populated only if dashboards repo set
      - repo: acme-grafana
        path: dashboards/rabbitmq-overview.json
        panels_referencing: ["SYNC_AC_INFO_JOB depth", "consumer ack rate"]

    cross_links:                        # populated only if incidents.yaml exists
      incidents: [PROJ-10909, PROJ-9876]   # tickets mentioning this queue
      heuristics: []                          # populated when heuristics/ files land later

    health_flags:
      - id: hf-001
        severity: high
        type: queue_not_durable
        detail: "durability=false in Helm; messages lost on broker restart"
        linked_concern: c-101            # mirrored in topology/_concerns.yaml
      - id: hf-002
        severity: medium
        type: ack_mode_auto
        detail: "consumer in auto-ack; combined with prefetch=50 this is fragile"
        linked_concern: c-102

publishers_index:                       # class name → queues list (fast lookup)
  SyncAcPassiveEndpointJob: [SYNC_AC_INFO_JOB]
  TaskCreatedEventPublisher: [TASK_CREATED, ...]

consumers_index:                        # class name → queues list (fast lookup)
  SyncAcInfoJobQueueFlow: [SYNC_AC_INFO_JOB]

orphans:
  declared_no_publisher: [LEGACY_QUEUE_NAME, ...]   # in infra but no code publisher
  declared_no_consumer: [...]                       # in infra but no code consumer
  code_no_infra:                                    # code publishes but not declared
    - class: FooPublisher
      queue: BAR_QUEUE
      location: <repo>/<file>:<line>

dynamic_queue_names:                    # could not statically resolve queue name
  - file: src/Workers/DynamicWorker.cs
    line: 47
    expression: "$\"sync_{type}\""
    reason: "interpolated string with runtime variable"
```

### Health flag rules

Apply per queue after Phase 3. Flag structure: `{ id, severity, type, detail, linked_concern? }`.

| Rule | Condition | Default severity | Bump rule |
|---|---|---|---|
| `queue_not_durable` | `declared_in.durability == false` | high | — |
| `ack_mode_auto_high_prefetch` | `ack_mode == auto AND prefetch > 10` | high | — |
| `ack_mode_auto` | `ack_mode == auto AND prefetch <= 10` | medium | — |
| `no_dlx` | `dlx == not_configured` | low | bump to medium if `recurrence_risk: high` incident cross-linked |
| `retry_no_backoff` | `retry_policy` text contains "retry" but not "backoff/exponential/wait" | medium | — |
| `confirm_mode_not_set` | publisher `confirm_mode == not_set` | medium | — |
| `orphan_queue_no_consumer` | queue in orphans.declared_no_consumer | medium | — |
| `orphan_queue_no_publisher` | queue in orphans.declared_no_publisher | medium | — |
| `code_no_infra` | queue in orphans.code_no_infra AND infra_mode != "none" | high | — (suggests deploy/declaration is missing) |
| `dynamic_queue_name` | queue name in dynamic_queue_names | medium | — |
| `incident_validated` | queue has ≥1 incident cross-link in cross_links.incidents | (modifier — bumps other flags) | bumps medium → high on the same queue's other flags |

### Cross-link bump rule (incidents → topology)

If queue has ≥1 incident in `cross_links.incidents` AND that incident has `recurrence_risk: high`:
- Bump any `medium` health_flag on the same queue → `high`
- Add a `linked_concern` entry of type=risk in topology/_concerns.yaml that mentions the incident IDs

This is how incidents.yaml feeds back into topology severity.

### Fingerprint

```
fingerprint = sha256(
  sorted(<rel-path>:<mtime> for *.cs files in repos>)
  + sorted(<rel-path>:<mtime> for files in infra_repos if non-null>)
  + (incidents.yaml.fingerprint if exists else "")
)
```

Format: `sha256:<64-hex>`. The trailing dependency on incidents fingerprint is intentional — when incidents update, topology cross_links should recompute.

### topology/_concerns.yaml entries

Use the standard schema (`_shared/agent-docs-layout.md`). For each `high`-severity health_flag, create a mirrored `type: risk` concern with `linked_health_flag: <id>` back-reference. Pattern concerns (≥3 queues share the same flag type) also go here as `type: concern`.

**Template — high-severity health flag mirror**:
```yaml
- id: c-<n>
  type: risk
  location: topology.yaml#queues.<name>
  description: "<flag.detail>"
  severity: high
  confidence: confirmed
  status: open
  linked_health_flag: hf-<id>
  related_incidents: [<from cross_links.incidents>]
```

**Template — pattern concern (e.g. ≥3 queues with auto-ack)**:
```yaml
- id: c-<n>
  type: concern
  location: topology.yaml
  description: "<N> queues use auto-ack; project lacks consistent ack-mode policy"
  severity: medium
  confidence: likely
  status: open
  related_queues: [<names>]
```

### scan_state.json structure

```json
{
  "status": "in_progress",
  "started_at": "<ISO>",
  "infra_mode": "full | partial | none",
  "last_phase": "phase_1_app | phase_2_infra | phase_3_crosslink | phase_4_health | phase_5_incidents | done",
  "repos_completed": ["api_task", "api_portal"],
  "repos_pending": ["frontend"],
  "queue_count": 0,
  "dynamic_queue_names": [],
  "extraction_errors": []
}
```

### Edge cases & decisions

| Case | Handling |
|---|---|
| `messaging:` block missing | Error + exit (no silent fallback) |
| `messaging.brokers` is empty | Error + exit ("which broker to scan for?") |
| All `infra_repos` null OR block missing | Run in app-only mode; log warning; mark `infra_coverage: none` |
| One of 4 `infra_repos` set (e.g. helm only) | `infra_coverage: partial`; run helm scan, skip rest |
| Repo folder doesn't exist on disk | Log to `extraction_errors`; skip; continue with other repos |
| Queue name uses string interpolation | Log to `dynamic_queue_names`; flag with `dynamic_queue_name` health flag |
| Multiple consumers of same queue (load-balanced) | List all under `consumed_by[]` — this is fine |
| MassTransit auto-generated queue names (endpointNameFormatter) | Log convention to `naming_conventions:` section in topology.yaml; mark explicit naming as out-of-scope |
| Helm chart uses heavy templating | Read raw values.yaml; log uncertainty in `declared_in.notes` if values appear placeholder-like |
| Cross-broker bridge (RabbitMQ→Kafka) | Out of scope v1; log to `unsupported_patterns:` section |
| `incidents.yaml` exists but is empty | Skip Phase 5 silently — no cross-links possible |
| Queue declared in 2 different infra repos with conflicting config | List both `declared_in` entries; emit `conflicting_declaration` health flag with severity=high |

### What scan-init topology must NEVER do

- Run without `messaging:` block (would produce empty output silently)
- Try cross-file variable tracing for queue names (high error rate; log as dynamic instead)
- Modify code or infra files (read-only scan)
- Skip Phase 5 if incidents.yaml exists — the cross-links are the highest-value output
- Default to "infra_coverage: full" when infra_repos has nulls — accuracy matters for downstream skills

---

## scan-init flows

Builds a flow-centric registry of business flows for the project — the unit of business value developers actually think in. Answers: *"What flows exist? Each flow has which triggers? Reaches which effects? Has which past incidents? Where are the known gates?"*

**Purpose:** consumed by `do-ticket` Phase 6c (flow-gate) to detect tickets that touch business flows with `health != ok` OR `known_gates[]` and proactively route them to `domain-problem-solver` for a deep `flow-trace` BEFORE plan. Replaces the "wait for FM-3X-SAME-ROOT during implement" recovery pattern.

**Why flow-centric** (vs the earlier field-centric lifecycle approach, deprecated 2026-05-14):
- Developers describe tickets in flow terms ("rerouting doesn't fire", "indication missed"), not field terms
- A flow has ~3-5 triggers + 1 expected effect — small graph, easy to reason about
- Most field-level cascade info is already in code/domain_index + topology + incidents — don't duplicate
- Flow registry is small (~10-30 entries per project) and stable; lifecycle would have been 100s of fields

**Source**:
- `{project_docs}/code/domain_index.yaml` (services + controllers + dispatchers)
- `{project_docs}/domain/_index.yaml` + `_relationships.yaml` (entity relationships → flow boundaries)
- `{project_docs}/topology/topology.yaml` (RabbitMQ pubsub edges → async flow boundaries)
- `{project_docs}/incidents/incidents.yaml` (past bugs grouped by flow keyword → past_incidents per flow)
- App code repos for entry handler verification

**Output**:
```
public-project-docs/<project>/flows/
  flow_index.yaml                  ← per-flow registry: triggers × effects × anchors × health × known_gates
  _concerns.yaml                   ← agent observations during scan
  flow_scan_state.json
```

### Sub-command signature

```
scan-init flows [--flow=<id>] [--force]
```

- Default: scan-and-update all flows; new flows propose-and-confirm with user (Tier 2)
- `--flow=<id>`: scan a single flow only (faster — useful when one flow gained a new trigger channel)
- `--force`: skip stale check

### Required preconditions

| Precondition | Action if missing |
|---|---|
| `{project_docs}/code/domain_index.yaml` status == fresh | Error + exit: "scan-init flows requires fresh code artifact. Run `scan-init code` first." |
| `{project_docs}/domain/_index.yaml` exists | Error + exit: "scan-init flows requires domain artifact. Run `scan-init domain` first." |
| `{project_docs}/topology/topology.yaml` | OPTIONAL — if present, used to derive async flow boundaries (RabbitMQ publishers → consumers) |
| `{project_docs}/incidents/incidents.yaml` | OPTIONAL — if present, used to attach `past_incidents[]` per flow |

### Discovery strategy

This is **NOT a full code scan** — flows are inherently business-level. Mix three sources to propose flows, then user confirms:

1. **Topology edges** (async flows): every RabbitMQ queue with stable publishers + consumers AND a recognizable business name (e.g. `Dw*`, `Sync*`, `Indication*`, `SendIn*`) → candidate flow.
2. **Domain relationships**: `domain/_relationships.yaml` chains (e.g. `CHAIN-INC-1`, `CHAIN-SVC-1`) → candidate flow.
3. **Past incidents grouped by keyword**: incidents with shared `similar_pattern_keywords` (≥3 incidents) → candidate flow.
4. **Code clusters**: controllers with naming pattern `*FlowController` → confirmed flows.

For each candidate, propose to user with one-line description + detected anchors. User confirms / edits name / skips. Then deep-fill the entry by querying domain + code + topology + incidents for the confirmed flow.

### Extraction algorithm

```
FL-1  STALE CHECK (skipped when --force)
      Read _index.yaml → artifacts.flows.fingerprint + last_updated
      If matches AND last_updated < 30 days → emit "FRESH, skip" and exit

FL-2  PRECONDITION CHECK
      Verify code + domain artifacts. Fail per "Required preconditions" table.

FL-3  CANDIDATE DISCOVERY
      Source 1: glob {project_docs}/topology/queues[] — for each queue with named pubsub pair, derive candidate flow id from queue name (e.g. SYNC_AC_INFO_JOB → ac-info-sync)
      Source 2: read {project_docs}/domain/_relationships.yaml — each chain → candidate flow
      Source 3: scan {project_docs}/incidents/incidents.yaml.indexes.by_keyword for keywords appearing in ≥3 incidents → candidate
      Source 4: grep code shards for "*FlowController" classes → candidate (these are confirmed flows by naming convention)
      
      Deduplicate by candidate id. Compute candidate.source_signals list.

FL-4  USER CONFIRMATION (Tier 2 — required for new flows)
      For each candidate not yet in flow_index.yaml:
        Show: id, one-line description (derived from source signals), source_signals, suggested anchor handlers
        Ask: "Confirm / Rename / Skip / Edit description"
      For each existing flow in flow_index.yaml:
        If source signals changed (new trigger detected, new incident linked, health changed):
          Show diff, ask user to acknowledge/edit

FL-5  PER-FLOW DEEP FILL
      For each confirmed flow F:
        FL-5.1  TRIGGERS: list all entry handlers
          For each entry handler (from code shards + topology consumers + controller scan):
            Capture: id, description, channel (api/gui/rabbitmq/scheduled), entry_handler (class + file:line)
        
        FL-5.2  EFFECTS: list what the flow does (end states)
          Derive from incidents + domain shards + handler analysis:
            - DB changes (status transitions, new rows)
            - Outbound publishes (RabbitMQ queues)
            - Cascading flow calls (related_flows)
        
        FL-5.3  CODE ANCHORS:
          - sync_entry: the synchronous controller/service that performs the flow inline
          - async_entry: the publisher class that hands off to async chain
          - invariant_owner: the file where the core business rule lives (often the executor that respects the rule)
        
        FL-5.4  RELATED entities + flows:
          - related_entities: union of entities touched by triggers + effects
          - related_flows: flows whose effects this flow's triggers depend on, OR flows that consume this flow's effects
        
        FL-5.5  INVARIANTS:
          - From domain/<entity>.yaml#invariants for each related entity → rule_ids
        
        FL-5.6  PAST INCIDENTS:
          - Search incidents.yaml for tickets with similar_pattern_keywords matching the flow id/aliases
          - List ticket IDs
        
        FL-5.7  HEALTH + KNOWN GATES:
          - health: "ok" by default. Set to "degraded" if past_incidents has recurrence_risk=high entry, OR if a known_gate exists.
          - known_gates: walk anchor handlers for these patterns:
            - silent-overwrite: handler reassigns inbound value with stored value (e.g. `form.X = existing.X`)
            - conditional-guard: publish/dispatch gated by an inferred condition (`if (...) publish(...)`)
            - early-return: `if (input == null) return;` before reaching downstream
            - missing-wire: handler defined but never registered in DI / never called
          - If matched, write known_gate with id, description, location, related_ticket (if past incident matches)
        
        FL-5.8  COMPLEXITY:
          - Compute from: number of triggers, number of related_flows, number of repos touched
          - high: ≥4 triggers OR ≥3 related_flows OR ≥3 repos
          - medium: ≥2 triggers OR ≥2 related_flows OR exactly 2 repos
          - low: otherwise
        
        FL-5.9  WRITE flow entry to flow_index.yaml (incremental)

FL-6  REBUILD INDEXES (at end of all flows)
      indexes.by_keyword: map keyword (from flow id + aliases) → [flow_ids]
      indexes.by_entity: map entity → [flow_ids it appears in]
      indexes.by_health: { ok: [...], degraded: [...], broken: [...] }
      indexes.high_complexity: [flow_ids with complexity == high]

FL-7  WRITE _index.yaml update
      artifacts.flows: { path, last_updated: now, fingerprint, status: fresh,
                          flow_count: N, degraded_count: D, broken_count: B,
                          required_by: [], optional_for: [6, 9] }

FL-8  LIVE-SYNC + MARK DONE
      doc-manager live-sync flows/flow_index.yaml edit|create
      doc-manager live-sync flows/_concerns.yaml edit|create
      scan_state.json.status = done

FL-9  REPORT
      Print summary:
        - Flows registered: N (new: M, updated: U, unchanged: K)
        - Health: <ok: A, degraded: B, broken: C>
        - High complexity: H
        - Known gates pre-recorded: G
```

### flow_index.yaml schema

```yaml
# Auto-generated by scan-init v2.x.x — flows sub-command
# Last updated: <ISO>
# Project: <name>
# Total flows: <N>
# Degraded: <D>  •  Broken: <B>

flows:
  rerouting:                              # flow id — kebab-case, business-named
    description: "Cancel active OutTask under party A → create new OutTask under party B"
    business_value: "Allow AO/PO to reassign in-flight work to a different solution party without losing context"
    aliases: [reroute, change-solution-party]   # alternate names used in tickets

    triggers:
      - id: t1
        description: "AO sends solutionParty change via 3rd-party API"
        channel: api                       # api | gui | rabbitmq | scheduled
        entry_handler:
          class: ThirdPartyFormGetter
          location: acme-api-task/.../ThirdPartyFormGetter.cs:105
          repo: acme-api-task
      - id: t2
        description: "Portal user clicks 'Change Solution Party' button"
        channel: gui
        entry_handler:
          class: TasksV2Controller.ChangeSolutionParty
          location: acme-api-portal/.../TasksV2Controller.cs:127
          repo: acme-api-portal
      - id: t3
        description: "Routing Rule admin config change triggers re-evaluation"
        channel: scheduled
        entry_handler:
          class: TBD                       # known gap — anchor not yet identified
          location: TBD

    effects:
      - "Active OutTask under old party transitions to TO_BE_CANCELLED (revision++)"
      - "New OutTask created under new party in RECEIVED state"
      - "RabbitMQ publish: SendInTaskToAO + SendOutTasksToContractor"

    code_anchors:
      sync_entry:
        class: FlowController
        location: acme-api-task/.../FlowController.cs:30
      async_entry:
        class: AssigneeSetter
        location: acme-api-task/.../AssigneeSetter.cs:107
        publishes_to: DwRoutingModel (queue)
      invariant_owner:
        class: TaskCreateExecutor
        location: acme-api-task/.../TaskCreateExecutor.cs:51
        rule_enforced: "task_solution_parties row present = AO-explicit, bypass routing"

    related_entities: [ServiceTask, InTask, OutTask, OutTaskset]
    related_flows:
      - solution-party-assignment        # parent: just sets the field; rerouting is one of the effects
      - dynamic-workflow                  # async pipeline that invokes rerouting via CreateChildTask
      - contractor-routing                # downstream: new OutTask gets routed to contractor

    invariants_respected:
      - rule_id: IT-CREATE-1              # in_task.yaml
        description: "task_solution_party row present = AO-explicit; row absent = re-route fresh"
      - rule_id: OT-UNIQ-1                # out_task.yaml
        description: "at_most_one_non_terminal_per_address_within_category"

    past_incidents:
      - id: PROJ-10869a
        kind: revert
        lesson: "Did not respect re-routing invariant → full revert"
      - id: PROJ-10867
        kind: lock-in
        lesson: "Solution-party reassignment via 3rd-party API explicitly disabled at MapDataAsync — must carve out for explicit-field signal"

    health: degraded                     # ok | degraded | broken
    health_reason: "2 known gates block trigger t1 (3rd-party API) from reaching effect"

    known_gates:
      - id: kg-1
        description: "MapDataAsync silently overwrites inbound SolutionPartyId with stored value (PROJ-10867 lock-in)"
        mechanism: silent-overwrite
        location: acme-api-task/.../ThirdPartyApiRouter.cs:315-356
        blocks_trigger: t1
        related_ticket: PROJ-10867
        confidence: confirmed
      - id: kg-2
        description: "AssigneeSetter publish gated on isExistOutTask || shouldGenerateOuttask"
        mechanism: conditional-guard
        location: acme-api-task/.../AssigneeSetter.cs:107-119
        blocks_trigger: t1
        related_ticket: PROJ-10869
        confidence: confirmed

    complexity: high
    complexity_reason: "3 triggers × 2 entry repos × 3 related_flows × async + sync paths"

  indication_send_ao:
    description: "..."
    ...

  three_way_sync:
    description: "..."
    ...

# ───── INDEXES (rebuilt at end of every scan run) ─────
indexes:
  by_keyword:
    rerouting: [rerouting]
    reroute: [rerouting]
    indication: [indication-send-ao, indication-send-co]
    sync: [three-way-sync, ac-info-sync]

  by_entity:
    ServiceTask: [rerouting, contractor-assignment, dynamic-workflow]
    InTask: [rerouting, indication-send-ao]
    OutTask: [rerouting, contractor-assignment]

  by_health:
    ok: [contractor-assignment, dynamic-workflow]
    degraded: [rerouting]
    broken: []

  high_complexity: [rerouting, three-way-sync, dynamic-workflow]

# ───── SUMMARY (rebuilt at end of every scan run) ─────
summary:
  flows_registered: <N>
  new_this_run: <M>
  updated_this_run: <U>
  health_distribution: { ok: A, degraded: B, broken: C }
  complexity_distribution: { high: H, medium: M2, low: L }
  total_known_gates: <G>
```

### Fingerprint

```
fingerprint = sha256(
    {project_docs}/code/domain_index.yaml.fingerprint
  + {project_docs}/domain/_index.yaml.fingerprint
  + (topology.yaml.fingerprint if exists else "")
  + (incidents.yaml.fingerprint if exists else "")
)
```

Stale = upstream code, domain, topology, or incidents artifacts changed.

### scan_state.json structure

```json
{
  "status": "in_progress",
  "started_at": "<ISO>",
  "candidates_discovered": 18,
  "user_confirmed": 12,
  "user_skipped": 4,
  "user_pending": 2,
  "flows_done": ["rerouting", "indication-send-ao"],
  "flows_pending": [...],
  "extraction_errors": []
}
```

### _concerns.yaml entries (specific to flows)

Standard schema. Dominant types:

**Template — flow anchor unverified**:
```yaml
- id: c-<n>
  type: knowledge-gap
  location: flows/flow_index.yaml#flows.<id>
  description: "Flow <id> has trigger t<n> with entry_handler: TBD — DPS flow-trace will need to identify it at ticket time"
  severity: low
  confidence: confirmed
  status: open
```

**Template — flow degraded by known gate**:
```yaml
- id: c-<n>
  type: concern
  location: flows/flow_index.yaml#flows.<id>.known_gates
  description: "Flow <id> has known gate <kg-id> blocking trigger <t-id>. Any ticket that touches this trigger MUST address the gate (otherwise repeats PROJ-XXXXX pattern)."
  severity: high
  confidence: confirmed
  status: open
  related_tickets: [<from past_incidents>]
```

**Template — pattern across flows (≥3 share same gate mechanism)**:
```yaml
- id: c-<n>
  type: concern
  location: flows/flow_index.yaml
  description: "<N> flows share mechanism 'silent-overwrite at inbound router' — likely a single architectural fix would resolve all"
  severity: medium
  confidence: likely
  status: open
  related_flows: [<list>]
```

### Edge cases & decisions

| Case | Handling |
|---|---|
| domain artifact missing | Error + exit. Flow scan needs entity registry. |
| topology missing | Run anyway; topology source becomes empty; rely on other 3 sources |
| incidents missing | Run anyway; past_incidents stay empty; health defaults to ok unless other signals say otherwise |
| User skips a candidate | Don't write to flow_index. Log to scan_state.user_skipped. Next run will re-propose. |
| Flow has trigger with anchor=TBD | Allowed (degraded knowledge). Write a knowledge-gap concern. DPS will derive at ticket time. |
| Two candidates dedupe to same id by accident | List both source_signals; user picks the canonical name. |
| Flow with health=broken (currently doesn't work at all) | Allowed — useful for ticket-time gating to warn user up front. |

### What scan-init flows must NEVER do

- Auto-write a new flow without user confirmation (Tier 2 — flows are business-level, name matters)
- Trace cascades deeper than 1 level around an anchor (that's DPS flow-trace's job)
- Invent triggers — if anchor not found, write TBD + knowledge-gap concern
- Modify code or domain files (read-only scan)
- Default to "complexity: high" — compute from observable signals

---

## scan-init verify

Validates that the existing artifacts truly reflect the current source code — coverage check + schema validation + legacy detection. Does NOT modify any artifact; emits a report and updates `phase_readiness`. Optional `--establish-baseline` flag writes the `baseline:` block when verify passes 100%.

**Why this exists:** `artifacts.<x>.last_updated` proves the artifact was rewritten on that date. It does NOT prove every source file is reflected in the artifact. `verify` answers the second question.

**Output**: `public-project-docs/<project>/verify-report.md` (overwritten each run)

### Verify steps

```
V-1  Real fingerprint check (per artifact group)
  For each artifact in [code, db, domain, build, conventions]:
    Glob source files per source_globs
    Compute sha256(sorted(relpath + mtime + size for each file))
    Compare with artifacts.<x>.fingerprint in _index.yaml
    If artifact fingerprint is a placeholder string (not sha256:<64-hex>) → flag as "fingerprint never computed"
    If computed != stored → flag as "fingerprint drift"

V-2  Coverage diff (code artifact only)

  V-2.1  Detect shard format per file
    For each code/domain_index_*.yaml:
      If has top-level `entities:` map OR per-entity blocks → format: entity_based
      Else if has top-level `namespaces:` map → format: namespace_based
      Else → format: unknown (warn, skip this shard's coverage contribution)

  V-2.2  Extract "covered identifiers" set per shard
    entity_based shards → covered_entities[] = top-level entity names
    namespace_based shards:
      For each namespace block:
        covered_namespaces.add(namespace path)
        For each path under key_subdirs → covered_subdirs.add(path)
        For each name under key_services → covered_services.add(name)
        For each name under key_enums → covered_enums.add(name)
    Merge across all shards in the repo → covered_set

  V-2.3  Orphan check (each covered identifier exists in source?)
    For each item in covered_set, grep per kind:
      namespace → "namespace <path>" in *.cs (or "@NgModule({" + module name for Angular)
      subdir    → directory exists at the expected relative path
      service   → "class <name>" or "interface <name>" in *.cs (or "@Injectable" + name for Angular)
      enum      → "enum <name>" in *.cs (or "export enum <name>" for TS)
      entity    → "class <name>" in *.cs (or TS class)
    If not found → orphan_identifiers[] (formerly orphan_entities[])

  V-2.4  Uncovered source files
    For each source file under source_globs:
      Determine the file's namespace (.cs: read `namespace ...` line; TS: derive from path)
      If file's namespace IS in covered_namespaces OR file's directory IS under any covered_subdir → covered
      Else → uncovered_files[]
    Exclude generated files (matched per Phase 1.5 "technical" rules) from total count.

  V-2.5  Compute
    coverage_pct = (total_source_files - len(uncovered_files)) / total_source_files

V-3  Legacy layout detector
  Glob public-project-docs/<project>/agent-index/**
  If any file exists → flag as "legacy_layout_present" with file count
  Same check for any folder outside the canonical layout in agent-docs-layout.md

V-4  Schema validator (domain artifact)
  For each file matching domain/<Entity>.yaml:
    Required fields: entity, source, fields, lifecycle
    Optional: state_machine, invariants, glossary refs
    Missing required → add to schema_violations[]
  If domain.status == present_unverified AND no violations → flip status to fresh

V-4b Per-folder _concerns.yaml presence + integrity check
  For each folder in [code, db, domain, build, conventions]:
    If <folder>/_concerns.yaml MISSING → add to concerns_missing_folders[]
    Else load _concerns.yaml:
      Validate schema (folder, last_updated, concerns[])
      For each open concern:
        Check location validity:
          - file:line form → verify file exists and line within bounds
          - table.column form → verify table+column exist in db_index.yaml
        If location stale → add to concerns_stale[] with concern.id
      Count open concerns by business_or_technical → concerns_summary

V-4c Surface-layer checks (see `surface-layers.md` for full spec)
  S1: every business shard has `features_summary:` covering ≥ 80% of `business_modules`
  S2: `code/overloaded_terms.yaml` exists; every detected overload term is registered
  S3: entities meeting subtypes-detection signal have `subtypes:` block (warn only)
  S4: paired-section heuristic — section verb in {create, terminate, cancel, deliver, route, update, link, unlink} has a `See also:` block (warn only)
  S5: ≥ 2-variant signal fires (same field name in ≥ 2 entries within one file, or ≥ 2 documented operations on the same entity with different roles/tokens/flows) but no side-by-side comparison artifact / cross-link found (warn)
  S6: `domain/acronyms.yaml` exists; every short token appearing ≥ 2 times across shards is registered; same short MUST NOT have ≥ 2 distinct expansions across files (partial if it does)
  S7: every `orphan_queue_no_consumer` / `orphan_queue_no_publisher` flag in `topology/topology.yaml` MUST have a `consumer_resolved:` / `publisher_resolved:` OR `consumer_unknown:` / `publisher_unknown:` companion block (fail if missing)
  S8: every critical entity (signal: invariant documented in knowledge_*.md, OR appears in _relationships.yaml propagation, OR has ≥ 1 incident, OR has ≥ 1 RESOLVED DPS session targeting its lifecycle) MUST have a corresponding `domain/lifecycle_traces/<entity>.yaml` (warn if missing); FAIL if a RESOLVED DPS session targeting the entity exists but no lifecycle_trace has been promoted
  C1: gateway shard (api-portal or equivalent) emits `gateway_contract:` block (warn if missing)
  C2: every `code/domain_index_<service>.yaml` with ≥ 1 BackgroundService class has a top-level `background_workers:` section (warn if missing)
  C3: `code/feature_flags_catalog.yaml` exists when ≥ 1 flag matching ^(Enable|Use|Disable|Feature)\w+$ is detected in any appsettings.json (partial if missing)
  C4: every failure-mode section in knowledge_*.md has the 5 template fields (code/trigger/symptom/fix/by-design) (warn if missing)
  Emit each S1/S2/S7 failure AND S8-resolved-dps-not-promoted failure into `surface_layer_violations[]`; S3/S4/S5/S6/S8-warn/C1/C2/C3/C4 into `surface_layer_warnings[]`.
  Same-short-different-expansion under S6 emits to violations[] with severity `partial`.

V-5  Phase readiness recompute
  Same logic as scan-init sub-commands — recompute phase_readiness for all phases.

V-6  Write verify-report.md
  Sections: summary, fingerprint_diff, coverage_diff, legacy, schema_violations,
            concerns_missing_folders, concerns_stale, concerns_summary,
            phase_readiness_changes
```

### Verify result classification

| Result | Condition |
|---|---|
| `pass` | No fingerprint drift, coverage_pct ≥ 0.95, no legacy, no schema violations, every folder has `_concerns.yaml`, no stale concern locations, no surface-layer violations (S1/S2/S7/S8-resolved-dps in surface-layers.md), no S6 same-short-different-expansion |
| `partial` | coverage_pct ≥ 0.80 OR only `low`-impact issues OR `_concerns.yaml` missing in ≤1 folder OR surface-layer warnings only (S3-S6, S8-warn, C1-C4) OR C3 catalog missing |
| `fail` | coverage_pct < 0.80 OR legacy present OR schema violations exist OR `_concerns.yaml` missing in ≥2 folders OR surface-layer violations exist (S1/S2/S7/S8-resolved-dps) |

Open entries in `_concerns.yaml` DO NOT cause `fail` on their own — they are expected output of a healthy scan. Stale `location` (pointing to deleted file or out-of-range line) DOES count toward `fail` (signals the scan is out of date).

Severity × confidence of open entries is reported in `verify-report.md` for triage but does NOT change the result classification.

Only `pass` permits `--establish-baseline`.

### `--establish-baseline` flag

```
1. Run verify steps V-1 through V-5
2. If result != pass → emit error, do NOT write baseline. Print actionable list.
3. If pass:
   - For each repo in projects.yaml.repos:
       Read git HEAD commit + branch
       Count files under source_globs
   - Compute fingerprints (already done in V-1)
   - Write baseline: block to _index.yaml per agent-docs-layout.md schema
   - Set baseline.status: verified
   - Reset drift_since_baseline: [] (the list is now empty by definition)
   - Emit: "Baseline established at <iso>. From now on, drift will be tracked."
```

### verify-report.md format

```markdown
# scan-init verify report

Date: <iso>
Project: <name>
Result: pass | partial | fail

## Summary
- Fingerprint drift: <n> artifacts
- Coverage: <pct>% (uncovered: <n>, orphan: <n>)
- Legacy layout: <found-or-clear>
- Schema violations: <n>

## Fingerprint drift
| Artifact | Stored | Computed | Status |
|---|---|---|---|
| code | <stored> | <computed> | drift |

## Coverage diff (code)
- Shard format detected: namespace_based | entity_based | mixed
- Orphan identifiers (in index, not in source), grouped by kind:
    namespace: <list>
    service:   <list>
    enum:      <list>
    entity:    <list>
- Uncovered files (in source, not in index): <list>

## Legacy layout
- agent-index/: <n> files → recommend migrate or delete

## Schema violations
- domain/TaskEntity.yaml: missing field `lifecycle`

## Concerns
- Missing `_concerns.yaml`: code/, db/, domain/, build/, conventions/  (5 folders)
- Stale entry locations: <n>
- Open entries by folder × type:
    code: 17  (concern: 4, smell: 8, risk: 3, knowledge-gap: 1, decision-log: 1)
    db:    3  (concern: 1, risk: 2)
    domain: 5 (concern: 3, smell: 1, decision-log: 1)
    build: 0
    conventions: 2 (smell: 2)
- Severity × confidence (across all folders):
                hunch   likely   confirmed
       high       1        2         3       ← top of triage queue
       medium     4        6         5
       low        2        3         1

## Phase readiness changes
| Phase | Before | After |
|---|---|---|
| 7 | ready | not-ready (domain schema violation) |
```

---

## scan-drift check

Detects all drift events since `baseline.established_at` and appends them to `drift_since_baseline` in `_index.yaml`. Idempotent — running twice without new changes produces no new entries.

**Precondition:** `baseline:` block must exist. If missing → emit "No baseline established. Run `scan-init verify --establish-baseline` first." and exit.

### Drift detection steps

```
D-1  Read baseline block from _index.yaml
     If missing → exit with message above.

D-2  Source change detection (per repo)
  For each repo in baseline.repos:
    Current commit = git -C <repo-path> rev-parse HEAD
    If current_commit != baseline.repos.<repo>.commit:
      files_changed = git -C <repo-path> diff --name-only <baseline-commit>..HEAD | wc -l
      commits_ahead = git -C <repo-path> rev-list <baseline-commit>..HEAD --count
      contains_migration = git -C <repo-path> diff --name-only <baseline-commit>..HEAD | grep -E "Migration|_migration\.sql"
      severity: per agent-docs-layout.md severity rules
      proposed_action:
        if severity=high AND contains_migration → "scan-init db --force && scan-init code --force"
        else if severity=high → "scan-init code --force"
        else → "scan-update code --repo <repo>"
      Append drift entry (skip if same repo+commits_ahead already exists with status=open)

D-3  Skill version detection
  Current scan-init version = read from scan-init/SKILL.md header
  If current != baseline.scan_init_version:
    Compare semver: major bump → high, minor with breaking → medium, minor without → low
    breaking_changes = grep release notes / CHANGELOG (best-effort; agent may add manually)
    proposed_action:
      if severity=high → "scan-init all --force && scan-init verify --establish-baseline"
      else → "scan-init <affected-subcmd> --force"
    Append drift entry (skip if same from→to already exists)

D-4  Schema-source drift (artifact fingerprint vs source fingerprint)
  Reuse logic from `scan-init verify V-1` but without writing verify-report.
  If any artifact has fingerprint drift NOT explained by an existing source_change entry:
    type: schema_change
    severity: high (schema-level drift is always high)
    proposed_action: "scan-init <artifact-name> --force"
    Append drift entry

D-5  Recompute baseline.status
  If any open drift entry has severity=high → baseline.status: pending_reverify
  Else if any open drift entry has severity=medium → baseline.status: partial
  Else → baseline.status: verified

D-6  Print summary
```

### Output

```
scan-drift check — baseline 2026-05-13T15:00:00 (8 days ago)

  drift-001  source_change  repo=acme-api-task  12 files  medium
             → scan-update code --repo acme-api-task

  drift-002  skill_change   scan-init 2.0.0 → 2.1.0  high
             → scan-init all --force && scan-init verify --establish-baseline

Baseline status: pending_reverify (1 high-severity drift open)
Run: scan-drift resolve <drift-id>  to address each entry.
```

If no new drift → "No new drift since last check. Baseline status: verified."

---

## scan-drift resolve

Runs the `proposed_action` of a single drift entry. On success, marks the entry `status: processed`.

```
R-1  Read drift entry from _index.yaml.drift_since_baseline by id
     If not found → error.
     If status != open → emit warning and exit (no-op).

R-2  Print proposed_action and ask user to confirm (single y/n).
     (User has approved this drift's plan once; do not re-prompt sub-commands.)

R-3  Execute proposed_action as a shell command.
     If multi-step (chained with &&) → fail-fast on first failure.

R-4  On success:
       Set drift_entry.status: processed
       Set drift_entry.processed_at: <iso>
       Set drift_entry.processed_by: <proposed_action>
     On failure:
       Leave status: open
       Append note to drift_entry.notes with failure summary

R-5  Recompute baseline.status (per D-5 logic).
```

User can also manually mark `status: dismissed` if a drift is intentionally ignored — `scan-drift refresh-baseline` accepts both `processed` and `dismissed` as "closed".

---

## scan-drift refresh-baseline

Bumps `baseline.established_at` to now, after all drift entries are closed. Re-runs `scan-init verify` to confirm the new baseline still passes 100%.

```
F-1  Read drift_since_baseline.
     If any entry has status=open → block. Emit list of open entries. Exit.

F-2  Run `scan-init verify` (without --establish-baseline).
     If result != pass → block. Emit verify-report path. Exit.

F-3  Update baseline block:
       established_at: <iso>
       established_by: "scan-drift refresh-baseline (run #<n>)"
       status: verified
       scan_init_version: <current>
       repos: <snapshot current HEAD commits + file counts>
       artifacts_locked: <snapshot current fingerprints>
       notes: "Refreshed after processing <n> drift entries (<n-source>, <n-skill>, <n-schema>)"

F-4  Archive processed drift entries:
     Move drift_since_baseline[] where status in (processed, dismissed)
       → _audits/drift-archive-<baseline-date>.yaml
     Reset drift_since_baseline: [] in _index.yaml

F-5  Emit summary.
```

The archived file preserves the full audit trail of what changed between baselines.

---

## scan-init all

Runs all sub-commands sequentially. Intended for first-time project onboarding.

**Resume support:** before running, read `all_scan_state.json` (sibling of `_index.yaml`):
- If exists with `status: in_progress` → skip sub-commands already in `completed[]`, resume from `next_pending`
- Write `all_scan_state.json` after each sub-command completes (not at end)

```json
{
  "status": "in_progress",
  "started_at": "<ISO>",
  "completed": ["code", "db"],
  "next_pending": "domain",
  "failed": []
}
```

```
Order: code → db → domain → build → conventions → incidents → topology

For each sub-command:
  1. Run stale check
  2. If FRESH → skip with "already fresh" message
  3. If STALE/MISSING → run sub-command
  4. If sub-command FAILS → log to all_scan_state.failed[], emit warning, continue
     Special case: if code FAILED → before running domain, warn: "code scan failed — domain entity detection may be incomplete. Proceed? (y/n)"
  5. Update all_scan_state.json (mark completed or failed)
  6. Print summary table at end
```

**Summary table format:**
```
scan-init all — complete
  code:         fresh (skipped)
  db:           ✓ 47 tables, 12 enums, 3 views
  domain:       ✓ 8 entities scaffolded, 3 skipped by user
  build:        ✓ 4 repos, 6 services, 3 test projects
  conventions:  ✓ git + ci + security written
  incidents:    ✓ 137 tier-1 incidents extracted (12 skipped thin, 4 keyword patterns flagged)
  topology:     ✓ 23 queues mapped (infra_coverage: full, 5 high-severity health_flags, 8 incident cross-links)
_index.yaml updated. phase_readiness recomputed.
```

---

## Master _index.yaml — Update Protocol

After each sub-command completes, update `public-project-docs/<project>/_index.yaml`:

```yaml
artifacts:
  code:
    path: code/domain_index.yaml
    last_updated: <ISO>
    status: fresh
    fingerprint: <sha-of-source-aggregate>
    required_by: [6, 9, 10]      # phase_readiness gates only on required_by
    optional_for: [11]            # useful context but does not block the phase
  db:
    path: db/db_index.yaml
    last_updated: <ISO>
    status: fresh
    fingerprint: <sha-of-migration-mtimes>
    required_by: []               # no phase hard-requires the DB artifact
    optional_for: [6, 9]          # useful for analyze + plan but not blocking
  domain:
    path: domain/_index.yaml
    last_updated: <ISO>
    status: fresh | stale | missing
    fingerprint: <sha>
    required_by: [7, 19]
    optional_for: [9]
  build:
    path: build/build.yaml
    last_updated: <ISO>
    status: fresh
    fingerprint: <sha>
    required_by: [9, 10, 14]
    optional_for: [12]
  conventions:
    path: conventions/git.yaml
    last_updated: <ISO>
    status: fresh
    fingerprint: <sha>
    required_by: [17, 18, 21]
    optional_for: []
  patterns:
    path: patterns/_index.yaml
    last_updated: <ISO>
    status: fresh | stale | missing
    fingerprint: <sha>
    required_by: []               # optional everywhere — auto-induction is the fallback
    optional_for: [9]
  incidents:
    path: incidents/incidents.yaml
    last_updated: <ISO>
    status: fresh | stale | missing
    fingerprint: <sha>
    tier1_count: <n>
    tier2_count: <n>              # 0 until tier 2 implementation lands
    jira_project: <KEY>
    required_by: []               # never blocks — agent should read if present
    optional_for: [5, 6, 7, 9]    # analyze + plan + implement benefit
  topology:
    path: topology/topology.yaml
    last_updated: <ISO>
    status: fresh | stale | missing
    fingerprint: <sha>
    queue_count: <n>
    high_severity_flags: <n>      # surfaced in scan freshness check
    infra_coverage: full | partial | none
    required_by: []               # never blocks
    optional_for: [5, 6, 7, 9]    # higher leverage than incidents for messaging tickets
  api:
    path: api/gateway_api_docs.yaml
    last_updated: <ISO>
    status: fresh | stale | missing
    fingerprint: <sha>
    required_by: []
    optional_for: [15]            # produced by scan-api-docs, not scan-init

phase_readiness:
  6:  { ready: true,  missing: [] }
  7:  { ready: false, missing: ["domain/_index.yaml — not yet scanned"] }
  9:  { ready: true,  missing: [] }
  10: { ready: true,  missing: [] }
  12: { ready: true,  missing: [] }
  14: { ready: true,  missing: [] }
  17: { ready: true,  missing: [] }
  18: { ready: true,  missing: [] }
  19: { ready: false, missing: ["domain/_index.yaml — not yet scanned"] }
  21: { ready: true,  missing: [] }
```

`phase_readiness[N].ready = true` when **all artifacts with N in `required_by`** are `status: fresh`.
Artifacts in `optional_for` do NOT affect readiness — they are loaded if fresh, silently skipped if missing/stale.

---

## scan-gap-signals.yaml — downstream feedback

**Location:** `{project_docs}/scan-gap-signals.yaml`

Written by downstream skills (do-ticket, DPS) when a scan artifact proves insufficient at runtime. Read by `/learn` and `scan-update` to propose targeted re-scans.

```yaml
# scan-gap-signals.yaml — accumulated signals from downstream skill failures
# Written by: do-ticket (FM-FINGERPRINT-STALE), DPS (DPS-FM-NO-DOMAIN-MATCH, DPS-FM-CROSS-PROJECT-MISSING-INDEX)
# Read by: /learn, scan-update

signals:
  - id: sg-001
    source_skill: domain-problem-solver
    source_session: terminate-603-bug-2026-05-02
    fired_at: 2026-05-02T11:00:00
    artifact: code/domain_index.yaml
    sub_command: code
    gap_type: missing_entity     # missing_entity | stale_artifact | wrong_layer | missing_index
    detail: "ServiceTask.OnHoldReason not found in any shard"
    entity: ServiceTask.OnHoldReason   # set for missing_entity only
    proposed_action: "scan-update code"
    status: open                 # open | addressed | dismissed
```

**`gap_type` values:**
- `missing_entity` — entity referenced in problem/analysis not in domain index
- `stale_artifact` — fingerprint mismatch at phase gate
- `wrong_layer` — shard assignment was wrong (entity found in wrong domain)
- `missing_index` — entire artifact group not yet scanned

**append-only:** each signal is a new entry. Never overwrite existing entries — mark `status: addressed` when re-scan covers the gap.

**`/learn` consumption:** group by `sub_command + gap_type`. If same sub_command has ≥3 `open` signals → propose `scan-init <sub_command> --force`. If same `entity` appears in ≥2 missing_entity signals → propose adding it to domain index manually via `scan-update domain`.

---

## What the Agent Must Never Do

- Skip Phase 1 even if the project looks simple
- Assign a layer to any domain before Phase 1 is complete
- Force-fit an unclear complexity pattern — use `UNKNOWN`
- Read entire file contents when only class/function names are needed
- Delete any domain block without asking the user
- Skip writing state file after each directory (`code` sub-command)
- Re-scan a directory already in `scanned_dirs` (except on version mismatch)
- Write to `D:/agent-index/` — output is always `public-project-docs/<project>/`
- Prompt user for every op in `build` or `conventions` — these are fully automatic
- Write `domain` entity files without user confirmation per entity (Tier 2)
- Write or modify the `baseline:` block from any sub-command other than `scan-init verify --establish-baseline` or `scan-drift refresh-baseline`
- Delete entries from `drift_since_baseline` — append-only. Change `status` to `processed`/`dismissed` instead. Archival happens only in `scan-drift refresh-baseline` step F-4.
- Use placeholder strings (e.g. `sha256:multi-repo-2026-05-13-delta`) as fingerprints. Real fingerprints must be `sha256:<64-hex>` computed from sorted source file (relpath + mtime + size).
