# Surface Layers — discoverability requirements

**Why this file exists.** Scan-init artifacts are dense. The agent that consumes them (downstream skills, ticket analyst) needs **navigation surfaces**, not just data. A scan can contain the right facts and still fail to answer a general question if the reader cannot find the facts without composing across N sections.

This file defines eight surface layers (S1-S8) plus four content-coverage rules (C1-C4) that every scan-init run MUST emit. They are scan-time obligations, not optional polish.

The contract is justified by the scan-quality test in `public-project-docs/<project>/scan-quality-tests/`. Each gap pattern there maps to exactly one surface layer below.

**Meta-principle (derived empirically from 34-case scan-quality run, 2026-05-14):** _Never let a runner have to **infer** a fact that scan-init could have **stated**._ Inference is where fabrication enters. The 6 partials in the final test all reduced to scan-init silence or scattering — never to runner-capability limits.

---

## S1 — `features_summary:` block at top of every business shard

**Where:** `code/domain_index_<service>_<domain>.yaml`, before `namespaces:` / `modules:` / `complexity_flags:`.

**Shape:**

```yaml
features_summary:
  # One line per business capability. Reader who opens only the top of this
  # shard must see the full feature inventory of this (service, domain).
  # Do NOT list classes here — that is what `modules:` is for.
  - <capability-name>: <one-line — what the capability does, in business terms>
```

**Rule.** The features listed here MUST be a superset of `modules.business_modules[].name` — every business module appears at least once as a feature. A feature MAY span multiple modules (e.g. "Routing rules" covers both `RoutingRule` feature folder and `ContractorRouter` service).

**Why.** Without this block, the reader of a class-level shard sees `NormalTask`, `XwaveTask`, `OutTaskStatusTransitioner`, etc. — and cannot reconstruct that the service handles Dynamic Rules, Routing Rules, Action Permissions, etc. as top-level capabilities. The trees hide the forest.

**Verify rule.** `scan-init verify` MUST fail any business shard missing `features_summary:` or whose features cover < 80% of business modules in the same shard.

---

## S2 — `code/overloaded_terms.yaml` registry

**Where:** `public-project-docs/<project>/code/overloaded_terms.yaml`, emitted as a post-pass after all `scan-init code` shards are written.

**Shape:**

```yaml
schema_version: 1
last_updated: <iso>
# Terms that map to ≥ 2 distinct meanings in the codebase. Reader MUST
# disambiguate before designing or scoping any ticket that uses the term.
terms:
  - term: <UPPER_SNAKE_OR_PASCAL>
    meanings:
      - context: <module-or-shard>
        kind: <category-value | type-value | enum-member | operation-verb | sub-type>
        location: <code-or-shard-reference>
        one_line_disambiguator: <short>
      - context: ...
        kind: ...
        one_line_disambiguator: ...
    disambiguate_question: "Which <term> does the ticket target?"
```

**Detection signals (algorithmic — runnable in code post-pass).** Emit an entry when ANY hold:

1. Identifier appears as a value in `≥ 2 distinct enums` whose names differ. (e.g. `AFTER_CONNECT` exists in `CategoryEnum`, `InTaskTypeEnum`, `OutTaskTypeEnum`, `XwaveTaskTypeEnum`, ...).
2. Same identifier appears as both an `enum value` AND a top-level `class/operation name` (e.g. `Terminate` as a status update operation + `TERMINATE` as a task type).
3. Same identifier appears in `≥ 3 separate shards` with distinct `kind` annotations.

**Verify rule.** `scan-init verify` MUST flag any term meeting a signal above that is absent from `overloaded_terms.yaml`.

**INDEX.md integration.** After writing `overloaded_terms.yaml`, scan-init MUST append an INDEX line: `- code/overloaded_terms.yaml: overloaded, ambiguity, term overload, disambiguate, <each term as keyword>`.

**Why.** Without this registry, an analyst answering "fix X" or "TERMINATE flow" will silently pick one meaning and miss the other. This is the single highest-impact ticket-time defect class observed in scan-quality tests.

---

## S3 — `subtypes:` block per entity with code-level variants

**Where:** `domain/<entity>.yaml`, when the entity has code-level variants detected during `scan-init domain`.

**Detection.** An entity has variants if ANY hold:

- It has `≥ 3` subfolders under its Services/Handlers/Implementations directory.
- An enum exists whose name contains the entity name + `Type` / `SubType` / `Kind`.
- A polymorphic class hierarchy roots at the entity (≥ 3 concrete subclasses sharing a base).

**Shape:**

```yaml
subtypes:
  # Each entry is a variant the reader must consider when scoping a change
  # to the parent entity.
  - name: <SubtypeName>
    code_location: <folder-or-file-glob>
    behavior_delta: <one-line — how it differs from the parent default>
    permission_delta: <one-line — only if perms differ; omit if same>
```

**Verify rule.** If detection signals fire but `subtypes:` is absent → emit warning during `scan-init verify`. Agent SHOULD curate `behavior_delta` lines (cannot be auto-generated reliably) but MUST scaffold the list with names + locations on first scan.

**Why.** Without this, an analyst scoping "change behavior of ServiceTask" sees ServiceTask as a single thing and misses the 9 subtypes (Incident, Problem, PlannedWork, ...). Same pattern for any entity with variant handling.

---

## S4 — `see_also:` cross-link rule for paired sections

**Where:** every section in any `knowledge_*.md`, `flows/flow_*.md`, or `domain/<entity>.yaml` that describes a flow, operation, or invariant.

**Rule.** A section MUST contain a `See also:` line (or `see_also:` yaml key) when any hold:

- The section describes a **creation/start flow** for an entity whose **termination/cancellation flow** lives in a different section → cross-link to the termination section.
- The section describes an **operation** whose **inverse / paired operation** lives elsewhere (create ↔ terminate, route ↔ unroute, link ↔ unlink) → cross-link.
- The section describes an **invariant** that depends on or is depended on by another invariant in a different section → cross-link.
- The section's **headline term** is registered in `overloaded_terms.yaml` → cross-link to the registry entry.

**Shape:**

```markdown
## install_chain

... [body] ...

> See also:
> - `::install_terminate` — cascading TERMINATE behavior for the same chain.
> - `code/overloaded_terms.yaml::TERMINATE` — operation vs task-type disambiguation.
```

**Verify rule.** During `scan-init verify`, scan every section header in `knowledge_*.md` and `flows/*.md`. If the section contains a verb in {create, terminate, cancel, deliver, route, update, link, unlink} but lacks a `See also:` block → emit warning.

**Curation.** This is the only surface layer that MUST be curated (agent cannot reliably detect paired flows from raw code). `learn` and `promote-observations` skills enforce the rule at write-time for any new section.

---

## S5 — Comparison artifacts for ≥ 2-variant concerns

**Where:** any shard, knowledge file, or domain entity that documents **≥ 2 variants of the same concern** (modules, roles, endpoints, status flows, tokens, etc.).

**Rule.** When per-variant entries exist separately, scan-init MUST ALSO emit a **single side-by-side comparison artifact** (table or yaml block) within the same file, OR a dedicated comparison file cross-linked from each variant entry.

**Detection signals (any one fires):**

1. The same field name (e.g. `auth:`, `endpoint:`, `permission:`, `token:`) appears in ≥ 2 entries within one file.
2. Two sections describe operations on the same entity with different roles/tokens/flows.
3. An enum / module / family has ≥ 2 documented members and any one of them has a row of attributes (auth, endpoint, status path, etc.).

**Shape (representative — comparison table example):**

```markdown
## auth_quick_reference

| operation | required_role | concrete_token | scope_bound_to | endpoint |
|---|---|---|---|---|
| Create INSTALL task | AO | ao_klanta | KLANT_A party (id=20) | POST /api/v1/tasks/v2 |
| Create TERMINATE task | AO | ao_klanta | KLANT_A party (id=20) | POST /api/v1/tasks/v2 |
| Create CONNECTION_INCIDENT | PO | odf.tester | ODF party | POST /api/v1/tasks/v2 |
| Operate MAIN_TASK (CONTRACTOR_PLUGIN) | contractor | contractor_bam | BAM party (id=14) | contractor-plugin/... |
```

**Verify rule.** During `scan-init verify`, detect signals above. If a signal fires AND no comparison artifact exists within the same file (or no cross-link to a dedicated comparison file) → emit warning.

**Why.** Q8.1 of the scan-quality test FAILED via this exact mode: INSTALL and TERMINATE auth facts were both individually correct in `terminate_chain` / `install_chain` sections, but with no side-by-side comparison, the runner stitched them and FABRICATED a "cascade-TERMINATE needs contractor_bam" claim that contradicts the docs. Same mode in Q5.2 (HAS bridge details scattered) and Q10.2 (api-task background workers scattered across topology + domain_index_cross_cutting). General principle: scattered facts invite stitching errors; comparison artifacts close the gap.

---

## S6 — `domain/acronyms.yaml` glossary

**Where:** `public-project-docs/<project>/domain/acronyms.yaml`, emitted as part of `scan-init domain`.

**Shape:**

```yaml
schema_version: 1
last_updated: <iso>
# Every acronym / short system name used ≥ 2 times across code or docs.
# Reader uses this as the AUTHORITATIVE expansion. Other shards MUST NOT
# introduce competing expansions.
acronyms:
  - short: AC
    canonical: "Address Component"
    aka: ["AC system", "Address Clarity (legacy)"]
    domain_note: "External address/network data system; in dev replaced by acme-3rd-party-mock AC* controllers"
  - short: AO
    canonical: "Active Operator"      # CHOOSE ONE; record decision
    aka: []
    domain_note: "Role that owns Fulfillment chain creation; concrete example: ao_klanta (KLANT_A AO, party_id=20)"
    deprecated_expansions: ["Account Officer"]   # WAS used in older docs; do not propagate
  - short: BAM
    canonical: "BAM Beheer"
    domain_note: "Contractor party id=14; long-lived token contractor_bam for ContractorPlugin MAIN_TASK ops"
  - short: CDR
    canonical: "Create Damage Report"
    domain_note: "MAIN_TASK subtype under CONTRACTOR_PLUGIN"
```

**Detection signals (algorithmic — any one):**

1. An uppercase 2-5 letter token appears in ≥ 2 separate shards as a standalone identifier (not as part of `SCREAMING_SNAKE_CASE` constant names).
2. An uppercase 2-5 letter token appears in `_glossary.yaml` OR in any `domain/*.yaml` `description:` field.
3. Two shards each parenthetically expand the same short to DIFFERENT full names — high-priority flag for `deprecated_expansions:`.

**Verify rule.** `scan-init verify`:
- WARN if `domain/acronyms.yaml` is absent.
- FAIL if `domain/_glossary.yaml` defines an acronym differently from `domain/acronyms.yaml`.
- WARN per detected acronym appearing ≥ 2 times in shards but absent from registry.

**Cross-check rule (validation in scan-init).** For every shard file, grep for `<short> (<expansion>)` patterns. If the same `<short>` matches ≥ 2 distinct `<expansion>` values across the project → emit `surface_layer_violations[]` entry with severity `partial`.

**Why.** Q6.4, Q7.3 of the scan-quality test had runners expand "AC" as "Active Contractor" / "Active Connector" — both wrong (canonical is "Address Component"). Q8.3 had runner pick "Account Officer" for AO from `_glossary.yaml` while `domain_index_connector.yaml` uses "Active Operator" — a doc-internal inconsistency. Without a single source of truth, every shard that touches an acronym risks divergence. `acronyms.yaml` collapses the class.

---

## S7 — `consumer_resolved:` on topology orphan flags

**Where:** `topology/topology.yaml`, on every queue entry whose `health_flags[]` includes `orphan_queue_no_consumer` (or symmetric `orphan_queue_no_publisher`).

**Rule.** Every `orphan_queue_no_*` flag MUST be paired with one of:

```yaml
consumer_resolved:
  service: <service-name>       # service that consumes, even if outside scanned repos
  shard: <code/domain_index_X.yaml>   # shard documenting that consumer
  confidence: high | medium | low
  reasoning: <one-line — how the resolution was determined>
```

OR, if truly unknown:

```yaml
consumer_unknown:
  searched_in: [<list-of-scanned-repos>]
  candidate_services: [<best-guesses-with-rationale>]
  confidence: low
  ticket_to_resolve: <optional-jira-id-or-todo-marker>
```

**Detection signals.** Trivially: every entry in `orphans.declared_no_consumer:` and `orphans.declared_no_publisher:` must have a corresponding resolution block.

**Shape (representative — fixed for the acme WORKFLOW exchange):**

```yaml
WORKFLOW:
  exchange: WORKFLOW
  routing_keys_published:
    - WfRoutingKey.PrepareSendEmail
    - WfRoutingKey.UpdateOutTaskToDelivered
    - WfRoutingKey.TaskRerouting
  published_by: [...5 entries...]
  consumed_by: []
  health_flags:
    - id: hf-037
      severity: high
      type: orphan_queue_no_consumer
      detail: "5+ publishers in api-task, no consumer in scanned repos"
      consumer_resolved:
        service: acme-workflow-automation
        shard: code/domain_index_automation.yaml
        confidence: high
        reasoning: "domain_index_automation.yaml::AutomationWorkflow is a Temporal worker; the WORKFLOW exchange routes via WfRoutingKey to its activities. Confirmed by Q9.1 scan-quality test."
```

**Verify rule.** `scan-init verify` FAILS if any `orphan_queue_no_consumer` (or `orphan_queue_no_publisher`) flag lacks a `consumer_resolved:` / `publisher_resolved:` OR `consumer_unknown:` / `publisher_unknown:` companion block.

**Why.** Q6.3 and Q10.3 of the scan-quality test had runners misread "no consumer in scanned repos" as "doesn't exist" — leading to wrong answers like "api-task does NOT talk to a workflow engine" (Q6.3) and "WORKFLOW messages are being silently dropped" (Q10.3). The orphan flag was correct at scan time but missing its resolution context. Every orphan flag is a half-formed answer; this layer completes it.

---

## S8 — `domain/lifecycle_traces/<entity>.yaml` per critical entity

**Where:** `public-project-docs/<project>/domain/lifecycle_traces/<entity>.yaml`, populated by promoting findings from completed DPS sessions (via `/promote-observations`) or curated by hand.

**Purpose.** A pre-computed map of every code touchpoint on every lifecycle stage (create / update / clear / propagate / read) for a critical entity — together with the **traps** found along each path. Lets `do-ticket analyze` surface code-level lifecycle gaps without escalating to DPS, when those gaps have already been investigated in prior tickets.

**Detection — entity is "critical" if ANY hold:**

1. Entity has a documented invariant in `knowledge_*.md` (e.g. a `::*_semantics` section).
2. Entity appears as a target in `domain/_relationships.yaml` propagation chains.
3. Entity has ≥ 1 historical incident in `incidents/incidents.yaml` referencing its lifecycle paths.
4. Entity has ≥ 1 RESOLVED DPS session under `domain-problem-solver/open/*` targeting its lifecycle.
5. The same entity name appears in ≥ 3 distinct shards/files with `<entity>.SolutionPartyId`-style field references.

**Shape (representative — `task_solution_party.yaml`):**

```yaml
schema_version: 1
entity: task_solution_party
last_updated: <iso>
source: promoted-from-dps        # or: curated, mixed
source_sessions:                 # if promoted
  - solution-party-rerouting-2026-05-14

invariants:
  - id: SP-INV-1
    statement: "row present + SolutionPartyId != 0 = AO-explicit, bypass routing; row absent = re-route fresh"
    ref: knowledge_task.md::solution_party_semantics
    violation_history: [PROJ-10869a-revert]

lifecycle_stages:
  create:
    paths:
      - name: "Service inbound (3rd-party AO API)"
        entry: acme-api-task/.../InTaskCreateExecutor.cs:CreateInTaskAsTaskSummaryAsync
        flow:
          - file: acme-shared-lib/.../TaskModelMapper.cs
            note: "Maps inbound *.solutionParty → ServiceTaskModel.SolutionPartyId"
          - file: acme-api-task/.../InTaskCreateExecutor.cs
            note: "Inserts task_solution_party row when SolutionPartyId > 0 (NOT gated on task type)"
        traps: []   # none currently known on create path

  update:
    paths:
      - name: "GUI dedicated"
        entry: FlowController.cs
        traps: []
      - name: "3rd-party API patch-update"
        entry: ThirdPartyApiRouter.cs:MapDataAsync
        traps:
          - id: G-1b
            severity: critical
            file: acme-api-task/.../ThirdPartyApiRouter.cs:315-356
            cause: "PROJ-10867 address-unchanged lock silently overwrites AO-sent SolutionPartyId with stored value"
            visible_only_if: "AO sends solutionParty on UPDATE with address unchanged"
            invariant_at_risk: SP-INV-1
            historical_context: PROJ-10867
            fix_pattern: "Explicit-field-provided signal carve-out on both lock branches"

  clear:
    paths:
      - name: "Explicit NULL clear via 3rd-party patch"
        entry: ThirdPartyFormGetter.cs
        traps:
          - id: G-3
            severity: medium
            file: acme-api-task/.../ThirdPartyFormGetter.cs:107
            cause: "Early return when SolutionPartyId is null — silent no-op"
            invariant_at_risk: SP-INV-1
            note: "Invariant 'row absent = re-route fresh' not implemented for explicit clear path"

  rerouting:
    paths:
      - name: "Async rerouting publish on solution-party update"
        entry: AssigneeSetter.cs
        traps:
          - id: G-1a
            severity: high
            file: acme-api-task/.../AssigneeSetter.cs:107-119
            cause: "Rerouting publish gated on isExistOutTask || shouldGenerateOuttask"
            edge_case: "AO update arrives BEFORE first OutTask is materialized → no DwRoutingModel publish → no rerouting"
            invariant_at_risk: "rerouting must fire on every accepted solutionParty change"

  read_projection:
    paths:
      - name: "TaskDetailSearch / BriefSearch"
        entry: ServiceTaskRepository.GetByTaskIdAsync
        flow:
          - "Reads task_solution_parties row; falls back to null SolutionPartyName when no row"
        traps: []

cross_references:
  related_entities: [InTask, OutTask, ServiceOutTask, ServiceTask]
  related_invariants:
    - knowledge_task.md::solution_party_semantics
    - knowledge_task.md::sp_propagation
  related_tickets: [PROJ-10867, PROJ-10869, PROJ-10869a, PROJ-10834, PROJ-9986, PROJ-10714]
```

**Verify rule.** `scan-init verify`:

- WARN per critical entity (detection signal fires) that lacks a `domain/lifecycle_traces/<entity>.yaml`.
- **FAIL** if a DPS session under `domain-problem-solver/open/*` has `dps_final_status: RESOLVED` and `gaps[].location` references a critical entity, but no corresponding `lifecycle_traces/<entity>.yaml` has been promoted — DPS findings going stale in session folders is the failure mode this layer exists to prevent.

**Promotion path.** When a DPS session resolves with gaps, `/promote-observations --from-dps <session-id>` MUST:

1. Identify the affected entity from `gaps[].path` / `domain_entities_in_scope`.
2. Create or update `domain/lifecycle_traces/<entity>.yaml`, appending new traps to the appropriate `lifecycle_stages.<stage>.paths[].traps[]`.
3. Cross-link the DPS session under `source_sessions`.

**Consumer.** `do-ticket analyze` MUST read `domain/lifecycle_traces/<entity>.yaml` for every entity in `domain_entities_in_scope` BEFORE producing the analysis artifact. Traps from these files MUST be surfaced in the analyst output's risk register, even if the ticket text doesn't mention them.

**Why.** This layer was added after the PROJ-10869 do-ticket test (2026-05-14) — analyst caught 80% of the impact map but missed three specific code-lifecycle traps (G-1a, G-1b, G-3) because they lived only in a DPS session folder (`solution-party-rerouting-2026-05-14`), with no surface in scan-init artifacts. The traps had been correctly identified by a previous DPS run; they just weren't durable. This layer makes DPS findings durable and self-served at analyze-time, eliminating the "re-investigate every ticket" tax.

**Anti-pattern to avoid.** Do NOT try to auto-extract lifecycle traces from raw code via static analysis — async cascades, conditional publishes, and silent locks are exactly the kind of traps static analysis misses (that's why DPS exists). Lifecycle_traces are a PROMOTION artifact, not a SCAN artifact. The promotion source is human-validated DPS output.

---

## Content-coverage requirements (long-tail per-domain)

Beyond the structural S1-S7 layers, scan-quality tests identified specific content gaps where a single missing artifact accounts for an entire test failure. These are NOT structural layers; they are content-coverage rules that scan-init MUST enforce per domain.

### C1 — `gateway_contract:` block in API-gateway shards

**Where:** `code/domain_index_<gateway-service>.yaml` (e.g. `domain_index_api_portal.yaml`).

**Required fields:**
- `response_envelope:` — full shape of any wrapper the gateway or downstream returns (e.g. `{success: bool, data: ..., message: ...}`)
- `http_status_vs_success_flag:` — explicit note when HTTP 200 + `success: false` is used in place of error codes
- `pass_through_endpoints:` vs `unwrapped_endpoints:` — which routes preserve the wrapper vs unwrap it
- `port_routing:` — gateway-port vs downstream-port mapping
- `path_prefix:` — gateway prefix (e.g. `/api-portal/`) vs direct path

**Why.** Q6.1 fabricated "snake_case vs PascalCase" body format because scan-init was silent on the actual `{success, data}` envelope shape. Documenting at the gateway shard closes the class.

### C2 — `background_workers:` section per service shard

**Where:** every `code/domain_index_<service>.yaml`, as a top-level section parallel to `namespaces:` and `modules:`.

**Shape:**

```yaml
background_workers:
  # Every BackgroundService + every scheduled-feeling Job class HOSTED IN this service.
  # Cross-reference canonical entries in namespaces:/modules: rather than duplicating.
  - name: SyncAcInfoJobQueueFlow
    kind: rabbitmq-subscriber-flow
    description: "AC sync orchestrator — fans out AC update messages from external systems"
    located_in: Services/Ac/SyncAcInfoJobQueue/
    triggers: ["SYNC_AC_INFO_JOB rabbit exchange"]
  - name: FailedMessageRetryJob
    kind: scheduled-job
    description: "Retries failed WORKFLOW publishes after exponential backoff"
    located_in: Services/Jobs/
  - name: DailyReportStuckTaskProcessor
    kind: scheduled-job
    description: "Daily report of stuck (long-WIP) tasks"
    located_in: Services/
```

**Why.** Q10.2 said "api-task doesn't run scheduled jobs itself" — wrong: there are ≥ 5 such workers, but they're scattered across `topology.yaml` (as publishers) and `domain_index_cross_cutting.yaml` (as classes), never collected per-service. The section closes the discovery gap.

### C3 — `code/feature_flags_catalog.yaml`

**Where:** `public-project-docs/<project>/code/feature_flags_catalog.yaml`, emitted as a post-pass of `scan-init code`.

**Source:** auto-extract from `appsettings.json` (every repo) — flag every key whose name matches `^(Enable|Use|Disable|Feature)\w+$` OR appears under a `Features:` block.

**Shape:**

```yaml
schema_version: 1
last_updated: <iso>
flags:
  - name: EnableRoutingRouteV2
    repo: acme-api-task
    appsettings_path: appsettings.json:225
    default_value: false
    description: "Gates ContractorRouter routing-rule dynamic flow vs legacy AC-administrator fallback"
    read_locations:
      - Features/RoutingRule/ContractorRouter.cs:36
      - Services/Tasks/ServiceTask/ThirdPartyCommunication/ThirdPartyApiRouter.cs:456
    branch_behavior:
      "true": "use routing-rule OrgId → AssigneePartyId (never SolutionPartyId)"
      "false": "fall back to AC administrator lookup"
    cross_links:
      - knowledge_task.md::solution_party_semantics
  - name: EnableWorkCompleteAttachmentValidation
    repo: acme-api-task
    default_value: true
    description: "TODO — fill via /learn"
    read_locations: []
```

**Even stub-with-TODO entries count.** The catalog's value is enumerative completeness, not per-flag depth. Depth grows via `/learn` over time.

**Why.** Q9.2 confirmed agent-docs have zero feature-flag catalog despite ≥ 8 flags in use. Catalog closes the doc-silent fabrication class for this entire domain.

### C4 — Failure-mode template (proven from Cat 7 results)

**Where:** every section in `knowledge_*.md` that describes a known error / DENIED status / hold reason / clean-check rejection.

**Required structure (CLONE this exactly — all 4 PASS in Cat 7 used it):**

```markdown
## <failure_mode_name>

- **Code/name:** <error code OR canonical short name, e.g. HLD-903, "Order is double", DENIED>
- **Trigger / cause:** <one-line — what condition produces this>
- **Symptom shape:** <HTTP status + body shape — e.g. "200 OK, status=DENIED on the returned task row; NOT a 400 error">
- **Fix path:** <one-line, actionable — what the caller must do>
- **By design vs bug:** <by_design | bug-pending-fix | mode-of-operation>

> See also: <cross-links per S4>
```

**Why.** Category 7 of the scan-quality test (DENIED, hold reasons, Order is double, PO visibility) PASSED 4/4 cleanly because every entry followed this exact shape. Category 6 (no template) had 3/4 partials. The template is empirically proven to make the runner's job trivial.

---

## Verify summary

When `scan-init verify` runs:

| Check | Trigger | Severity |
|---|---|---|
| S1 missing `features_summary:` in a business shard | always | fail |
| S1 features cover < 80% of `business_modules` in same shard | always | partial |
| S2 detected overload term absent from registry | always | partial |
| S2 `overloaded_terms.yaml` missing entirely | always | fail |
| S3 subtypes-detection fires but block absent | always | warn |
| S4 paired-section heuristic fires but `See also:` absent | always | warn |
| **S5** ≥ 2-variant signal fires but no comparison artifact / cross-link | always | warn |
| **S6** `domain/acronyms.yaml` absent | always | warn |
| **S6** acronym ≥ 2 occurrences but absent from registry | always | warn |
| **S6** same short has ≥ 2 distinct expansions across shards | always | partial |
| **S7** `orphan_queue_no_*` flag lacks `consumer_resolved:` / `_unknown:` | always | fail |
| **S8** critical entity (signal fires) lacks `domain/lifecycle_traces/<entity>.yaml` | always | warn |
| **S8** RESOLVED DPS session targets entity but no lifecycle_trace promoted | always | **fail** |
| **C1** gateway shard lacks `gateway_contract:` block | always | warn |
| **C2** service shard lacks `background_workers:` section (when service has ≥ 1 BackgroundService class) | always | warn |
| **C3** `code/feature_flags_catalog.yaml` absent (when ≥ 1 flag detected in any appsettings.json) | always | partial |
| **C4** failure-mode section lacks template fields (code/trigger/symptom/fix/by-design) | always | warn |

S1 / S2 / S7 / S8-resolved-dps are **hard requirements** because they directly map to the highest-impact failure modes (silent fabrication, dropped orphan context, lost DPS findings). S3-S6, S8-warn, and C1-C4 are softer (warn or partial) because curation cannot always be auto-generated, but the warnings force a human/agent decision per occurrence.

---

## Migration notes

### 2026-05-14 — Round 1: S1-S4 (Categories 1, 2, 4)

This file was originally added after the acme scan-quality test surfaced 4 recurring gap patterns spanning Categories 1, 2, and 4 of the test plan. Before this date, scan-init had no formal discoverability layer.

### 2026-05-14 — Round 2: S5-S7 + C1-C4 (Categories 5-10 final results)

After running all 34 scan-quality cases (final score 28 pass / 6 partial / 0 fail), three additional hallucination modes were identified — all doc-structure issues, none runner-capability issues:

1. **Scattered-fact stitching** (Q5.2, Q8.1, Q10.2) → added S5 (comparison artifacts).
2. **Acronym mis-expansion** (Q6.4, Q7.3, Q8.3) → added S6 (acronyms.yaml + cross-check validation).
3. **Topology orphan misreading** (Q6.3, Q10.3) → added S7 (`consumer_resolved:` / `consumer_unknown:` required on orphan flags).

Plus four content-coverage rules (C1-C4) for specific high-leverage artifacts identified in long-tail testing:

- C1 — `gateway_contract:` block (Q6.1 envelope fabrication).
- C2 — `background_workers:` per service shard (Q10.2 missed api-task workers).
- C3 — `feature_flags_catalog.yaml` (Q9.2 doc-gap acknowledged).
- C4 — failure-mode template (Cat 7 empirically PASSED 4/4 — replicate the template anywhere similar facts appear).

**Backfill plan.** Existing projects scanned before 2026-05-14 Round 2 will lack S5-S7 + C1-C4 artifacts. Use `scan-init verify` to surface gaps; backfill incrementally per ticket touch-point or run `scan-init code --force` / `scan-init domain --force` to regenerate.

**Validation target.** Re-run the 6 partial cases from the acme scan-quality test against the updated scan-init output. If ≥ 4/6 convert to PASS, the Round 2 fixes are validated.

### 2026-05-14 — Round 3: S8 (lifecycle traces from DPS findings)

Added after the PROJ-10869 do-ticket-analyze test. The test ran `do-ticket analyze` on a real production ticket while forbidding the sub-agent from reading the ticket's own folder, then scored the output against a known 4-SP impact map. Analyst caught 80% of the impact (correctly identified central design risk, surfaced 4 PO open questions, recommended DPS routing), but missed three specific code-lifecycle traps:

- **G-1a** — `AssigneeSetter:107-119` rerouting publish gated on `isExistOutTask` (edge case: first AO update before any OutTask exists).
- **G-1b** — `ThirdPartyApiRouter.MapDataAsync:315-356` silent overwrite via PROJ-10867 address-unchanged lock.
- **G-3** — `ThirdPartyFormGetter.cs:107` NULL solutionParty silent no-op.

All three were correctly identified in a prior DPS session (`domain-problem-solver/open/solution-party-rerouting-2026-05-14/`), but the findings were locked in the session folder with no surface in scan-init artifacts. Analyst had no way to discover them without re-running DPS.

S8 closes this: DPS findings get promoted to `domain/lifecycle_traces/<entity>.yaml` via `/promote-observations --from-dps`. Subsequent `do-ticket analyze` runs on tickets touching the same entity surface the traps automatically. The current chain (analyst → flag invariant → route to DPS → re-investigate) is replaced by (analyst → read lifecycle_trace → surface known traps → only route to DPS for truly novel paths).

**Backfill plan for Round 3.** Run `scan-init verify` — every RESOLVED DPS session under `domain-problem-solver/open/*` should now FAIL verify until its gaps are promoted to a lifecycle_trace. For acme specifically, promote the `solution-party-rerouting-2026-05-14` session into `domain/lifecycle_traces/task_solution_party.yaml` as the canonical first instance.

**Validation target for Round 3.** Re-run the PROJ-10869 do-ticket-analyze test with `task_solution_party.yaml` lifecycle_trace in place. If the new analyst output surfaces G-1a, G-1b, and G-3 by name (without DPS escalation), Round 3 is validated. Target: ≥ 2/3 trap names appear in the requirements-analysis.md risk register.
