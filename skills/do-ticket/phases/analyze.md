# do-ticket — analyze part

Phase procedure for phases 5 `requirements`, 5.5 `enrich`, 6 `analyze` (6a context expansion, 6b analyze, 6c flow gate). The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`ticket-types.md`, `do-ticket-update.md`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 5 — `requirements`
**DPS handoff mode (`dps_session_id` set):** skip Jira fetch entirely. Generate `requirements.md` directly from `investigation-findings.md`:
```markdown
# Requirements: <title from findings>

## Source
Investigation findings from DPS session <session_id> — <created_at>

## Bug repro
<one-line summary> + <confirmed evidence bullets>

## Acceptance criteria
- [derived from findings + open assumptions flagged as "verify before implement"]

## Out of scope
<copy from findings "Out of scope" section>
```
Save fingerprint. Proceed to Phase 6.

**Jira fail on fresh run (no existing requirements.md):** do not retry. Offer: *"Cannot reach Jira. Choose: (a) enter requirements manually — I'll open an editor stub, (b) abort."* There is no existing file to fall back to, so (b) stops the flow.

**Jira staleness (resume):** if `jira.fetched_at` is older than 24h → *"Requirements were fetched >24h ago. Re-fetch to catch new comments? (y/n)"* Yes → re-fetch and diff vs current; show delta before proceeding. No → proceed with cached version.

On `update_count > 0`: after rewrite, diff vs prior version → confirm delta with user before proceeding.

## Phase 5.5 — `enrich` (PO-proxy)

Runs after `requirements` (5), before `analyze` (6). Turns thin Jira tickets into a detailed product spec the BA can analyze cleanly.

**Skip conditions:**
- `ticket_type ∈ {bugfix-small, bugfix-investigated, bugfix-regression, hotfix, doc-only, refactor, spike, migration-only}` — enrichment is a `crud-feature` and `fe-only` concern; smaller types either have an inline repro (bug) or no spec to enrich (refactor/migration/doc).
- `--from-dps` mode — investigation-findings.md already supplies an enriched-equivalent spec; jira-to-requirements derives requirements.md from it directly, no PO-proxy needed.
- `ticket-context.dps_session_id` set on resume — same reason as above.

**Invoke:** `enrich-requirements <TICKET_ID>` per `enrich-requirements/SKILL.md`. Output: `requirements-enriched.md`.

**Always blocks for user review on first run** — even when verdict is `PASS_THROUGH`. The whole point of this phase is a checkpoint where the user (a) confirms the enriched spec matches PO intent, (b) decides whether open questions need to be posted to Jira before BA runs. Resume skips the block if `state.phase >= enrich` AND fingerprint unchanged.

**On Jira escalation:** if user chooses to post open questions back to PO as Jira comments, offer to set `phase: blocked, blocked_reason: "awaiting PO answers on N questions"`. User resumes via `do-ticket <ID>` once PO replies — Phase 5 (requirements) will refresh the ticket and Phase 5.5 will re-enrich the deltas.

**Failure handling:** if enrich-requirements cannot resolve `{project_docs}` → log to telemetry, write a thin `requirements-enriched.md` that's a near-copy of `requirements.md` with verdict `PASS_THROUGH (docs unavailable)`, surface to user with: *"Project docs not available — enriched spec is a passthrough. BA will absorb the gap. Proceed? (y/n)"*. No FM registered yet — this is an unknown_failures candidate.

**Downstream consumers:** analyze-requirements (Phase 6) treats `requirements-enriched.md` as the primary input; if Phase 5.5 was skipped for this ticket type, it falls back to `requirements.md` (same as today).

## Phase 6 — `analyze`

Sub-steps in order: **6a context-expansion → 6b invoke analyze-requirements → 6c flow gate**.

**Step 6a — Context expansion (do-ticket internal, runs BEFORE invoking analyze-requirements)**

Pre-loads `incidents.yaml` and `topology.yaml` filtered to this ticket's scope. Output: `context-expansion.md` in ticket folder. Consumed by analyze-requirements AND plan phases as a pre-context hint — surfaces past incidents and cross-repo connectivity the agent might otherwise miss.

**Skip conditions:**
- Both `{project_docs}/incidents/incidents.yaml` AND `{project_docs}/topology/topology.yaml` missing → skip silently; analyze runs without expansion (log to telemetry: `context_expansion: not_available`)
- `--from-dps` mode → skip (DPS findings already supply richer context)
- `ticket_type == doc-only` → skip (no value)
- `ticket_type == hotfix` → skip step 6a; speed matters more than context completeness for hotfixes

**Algorithm:**

```
EXP-1  Read ticket-context.yaml + requirements.md
       Extract ticket scope:
         - components: from jira.components
         - keywords_from_title: lowercase words ≥4 chars from ticket title (skip stopwords)
         - keywords_from_desc: lowercase words ≥4 chars from requirements.md
         - mentioned_classes: ProperCase identifiers in title+description (e.g. "OrderSyncJob")
         - mentioned_queues: UPPER_SNAKE_CASE tokens (e.g. "ORDER_SYNC_JOB")
         - mentioned_repos: any token matching ctx.resolved.repos values

EXP-2  Read {project_docs}/incidents/incidents.yaml (if status=fresh in _index.yaml)
       Score each incident:
         score = 0
         + 3 if any ticket.components overlap with incident.components
         + 2 per match between ticket keywords and incident.similar_pattern_keywords
         + 1 per match between ticket title/desc tokens and incident.root_cause_1line tokens
         + 2 if incident.recurrence_risk == "high" AND score > 0
         + 1 if incident.confidence == "confirmed"
       Output: top 10 by score, OR all with score ≥ 4, whichever is smaller
       Also collect:
         - high_risk_overlap: incidents where recurrence_risk=high AND any keyword match
         - keyword_hits_summary: which incident keywords matched, counts

EXP-3  Read {project_docs}/topology/topology.yaml (if status=fresh in _index.yaml)
       For each queue in queues:
         match_signals = []
         if queue.name in mentioned_queues → match_signals += ["queue-name"]
         if any published_by[].class in mentioned_classes → match_signals += ["publisher-class"]
         if any consumed_by[].class in mentioned_classes → match_signals += ["consumer-class"]
         if any published_by[].repo or consumed_by[].repo in mentioned_repos → match_signals += ["repo"]
       If match_signals non-empty → include this queue in output with full record (publishers, consumers, declared_in, health_flags, cross_links)
       Also flag: queues with high-severity health_flags + cross_links.incidents overlapping with EXP-2 results

EXP-4  Write {ticket_dir}/context-expansion.md (see schema below)

EXP-5  Update ticket-context.yaml:
         context_expansion:
           incidents_available: <bool>
           topology_available: <bool>
           incidents_matched: [<ids>]              # from EXP-2
           topology_queues_matched: [<names>]      # from EXP-3
           high_risk_overlap: [<incident_ids>]
           file: context-expansion.md
         fingerprints.context_expansion_sha: <sha256 of file>

EXP-6  If incidents_matched is empty AND topology_queues_matched is empty AND incidents_available
       AND topology_available → log to telemetry: `context_expansion: no_matches`
       (Not a failure — just signal that this ticket may be in untouched territory.)
```

**context-expansion.md format:**

```markdown
# Context Expansion — <TICKET_ID>

Generated by do-ticket Phase 6a. Read this BEFORE forming hypotheses.

## Past incidents matching this ticket's scope

<For each matched incident, ranked by score:>

### <ID> — <symptom_1line> (score: N, confidence: confirmed/likely/hunch)
- **Root cause**: <root_cause_1line>
- **Fix layer**: <code/infra/external/hybrid>
- **Recurrence risk**: <high/medium/low>
- **Matched on**: <component overlap, keyword X, keyword Y>
- **Lessons**: <bullets>
- **Full entry**: incidents.yaml#<ID>

<If high_risk_overlap non-empty:>
## ⚠ High-risk pattern overlap

These incidents have recurrence_risk=high AND overlap with this ticket's keywords. Strong signal that the same architectural trap may apply here:
- <id>: <root_cause_1line>

## Relevant topology (cross-repo messaging)

<For each matched queue:>

### Queue: `<QUEUE_NAME>` (broker: <broker>)
- **Publishers**: <repo.class:line>, ...
- **Consumers**: <repo.class:line>, ...
- **Infra config**: <if declared_in non-empty: durability=X, ack_mode=Y, prefetch=Z>
- **Cross-linked incidents**: <ticket ids>
- **Health flags**: <list with severity>
- **Why matched**: <match_signals>

<If a matched queue has high-severity health flags AND cross-linked incidents:>
## ⚠ Architectural concern + history

Queue `<NAME>` has open health flag `<flag_type>` (severity: high) AND prior incidents <ids>. The architectural concern has caused real bugs. Review this queue's config carefully.

## Read these BEFORE writing requirements-analysis.md

The hypothesis you form in analyze should explicitly reference these incidents/queues if relevant. If you decide none apply, note that in requirements-analysis.md so the agent doesn't re-mine the same ground later.
```

**Surface to user (optional G1 block):**
If `high_risk_overlap` is non-empty:
> *"Past incidents with high-recurrence-risk overlap this ticket: [list]. Strong signal that the architectural trap may apply here. Acknowledge before proceeding to analyze? (y/n)"*

If user `n` → do NOT block; just log to telemetry that user dismissed. The point is awareness, not gatekeeping.

If `topology_queues_matched` non-empty AND any matched queue has a high-severity health_flag:
> *"Topology found <N> queue(s) on the bug path with open high-severity flags: [list]. Review before analyze? (y/n)"*

Same — `n` is non-blocking, just logged.

---

**Step 6b — Invoke analyze-requirements (existing flow)**

**DPS handoff mode (`dps_session_id` set AND `dps_final_status: RESOLVED`):** skip analyze entirely. Carry forward from Phase 0 hydration: `domain_entities_in_scope`, `complexity_flags`, `risk_factors` already in ticket-context. Surface `dps_open_assumptions` as a G1 confirmation block:
> *"DPS session confirmed root cause. Open assumptions from investigation that need verification during plan/implement: [list]. Acknowledge and proceed? (y/n)"*
After acknowledgment → proceed to Phase 7 (invariant-scope) or next applicable phase.

**DPS handoff mode, `dps_final_status: PARTIAL`:** do NOT skip analyze — run normally, but seed analyze-requirements with the findings as pre-context (load investigation-findings.md alongside requirements.md).

Pass `context-expansion.md` (if exists) to analyze-requirements as a pre-context hint alongside requirements.md.

Open questions → first settle every one that code, docs or data can answer (decision mode `M1` — run the command, do not ask). The rest → G1 block. Save `phase_before_block: analyze`. Resume re-runs analyze after user resolves.

**Speed-mode activation:** if analyze returns clarity score < 60 and user accepts speed-mode → set `speed_mode: true` in `ticket-context.yaml`. Pass `--speed-mode` flag to all downstream phases (8, 9, 10, 11). If user rejects → G1 block for clarification before proceeding.

---

**Step 6c — Flow gate (proactive DPS routing)**

Runs after 6b succeeds, before Phase 7. Goal: detect tickets that touch business flows with known complexity or recorded gates, and route to DPS for a `flow-trace` BEFORE plan, instead of waiting for FM-3X-SAME-ROOT recovery during implement (which is what burned PROJ-10869a).

**Why flow-gate, not field-gate:** developers think in flows (reassignment, flagging, sync), not in fields. A ticket usually touches ONE flow that may be triggered by N fields, not the other way around. flow_index is the right granularity — ~10-30 flows per project rather than 100s of fields. Field-level cascade is already implicit in code shards + topology; flow_index adds the unit-of-business view that's missing.

**Skip conditions (do not gate, proceed to Phase 7):**
- `--from-dps` mode → DPS already provided full context.
- `--from-briefing` mode → this run was itself spawned by a prior gate; do not re-gate.
- `ticket_type ∈ {doc-only, hotfix, spike}` → not enough surface area for cascade to matter.
- `state.flow_gate_decided == true` → user already decided on a prior run (don't re-prompt on resume).

**Algorithm:**

```
FG-1  LOAD: read {project_docs}/flows/flow_index.yaml (if exists)
      If missing → set ctx.flow_gate = "not_available" → skip to FG-4 (keyword-only fallback)

FG-2  FLOW MATCH: extract candidate tokens from requirements.md + requirements-analysis.md
      Lowercase ≥4-char tokens + UPPER_SNAKE_CASE tokens
      Match against flow_index.indexes.by_keyword AND flow_index.indexes.by_entity (when
      entity names appear).
      Also match flow names directly (e.g. "reassignment" → flow_index.flows.reassignment).

      touched_flows[] = unique set of matched flow ids
      For each touched_flow:
        Pull flow_index.flows.<id> record into scope.

FG-3  RISK ASSESSMENT per touched flow:
       For each touched_flow:
         If flow.health != "ok" (i.e. "degraded" or "broken") → add to risky_flows[] with reason
         If flow.complexity == "high" → add to risky_flows[]
         If flow.known_gates[] non-empty → add to risky_flows[] + carry forward gates for briefing

FG-4  KEYWORD SIGNAL fallback (no flow_index OR no flow match):
        grep requirements.md + requirements-analysis.md for any of:
          [update, trigger, connect, reroute, cascade, also fires, propagate,
           change triggers, flow doesn't trigger, when X changes Y should]
        If hit → set flow_keyword_signal = true (record matched phrases)

FG-5  DECIDE: gate fires IF (risky_flows non-empty) OR
                            (flow_keyword_signal AND ticket_type != bugfix-small AND ctx.flow_gate == "not_available")

      If gate does NOT fire → set ctx.flow_gate_decided = true, ctx.flow_gate = "passthrough"
        → log to telemetry: { gate: passthrough, touched_flows: [...], reason: <none risky> }
        → proceed to Phase 7

      If gate fires → continue to FG-6.

FG-6  SURFACE G10:
      Print:
        ⚠ Flow-gate fires for <TICKET_ID>:
          Touched flows (any): <list of flow names + one-line description each>
          Risky flows: <list with reason — health=degraded / has known_gates / complexity=high>
          Known gates pre-recorded: <list, or "none">
          Keyword signals: <matched phrases, or "none">
          Reason: <one sentence — e.g. "reassignment has 2 known gates blocking the 3rd-party API trigger path">

        Recommended: route to DPS for flow-trace BEFORE plan. DPS will:
          - Anchor on each entry handler of the flow (from flow_index + code shards)
          - Trace each TRIGGER PATH end-to-end (NOT per field)
          - Gap-analyze: which trigger paths silently drop the signal?
          - Recommend implementation options per gap
          do-ticket will then resume at plan with full flow context.

        Choose:
          a) Route to DPS (recommended)
          b) Skip — proceed to Phase 7 with plain context (logged as flow_gate_bypassed)
          c) Block — I want to investigate manually first (set phase: blocked)

FG-7  ON CHOICE a — Route to DPS:
        Write {ticket_dir}/dps-briefing.md per template below.
        Set state:
          phase: awaiting_dps
          phase_before_block: analyze
          dps_briefing_path: <abs path>
          flow_gate_decided: true
          flow_gate: routed_to_dps
        Print the exact invocation command:
          /domain-problem-solver --from-briefing=<abs path>
          (when DPS finishes, resume do-ticket via: do-ticket <TICKET_ID> --from-dps=<session-folder>)
        Halt.

FG-8  ON CHOICE b — Skip:
        Set ctx.flow_gate = "bypassed"
        Set ctx.flow_gate_decided = true
        Inject risky_flows + known_gates + keyword_signals as a WARNING block into plan context
          (saved to ctx.plan_warnings[] — implement-plan will surface them)
        Log to run-telemetry: { gate: bypassed, risky_flows: [...], reason: <user choice> }
        Proceed to Phase 7.

FG-9  ON CHOICE c — Block:
        Set state.phase: blocked, blocked_reason: "user requested manual flow investigation"
        Halt.
```

**`dps-briefing.md` template** (written at FG-7):

```markdown
# DPS Briefing — <TICKET_ID>

Generated by do-ticket Phase 6c flow-gate at <ISO>.

## Source ticket
<TICKET_ID> — <ticket title from requirements.md>
Source repos in scope: <from ticket-context.resolved.repos>

## Ticket summary
<first 5 lines of requirements.md>

## Flows in scope
<For each flow in risky_flows + touched_flows:>
### <flow_name> — <flow.description>
- Health: <ok | degraded | broken>
- Complexity: <low | medium | high>
- Triggers (from flow_index):
  - <trigger.id>: <description> (channel: <api|gui|rabbitmq|scheduled>, entry: <handler at file:line>)
  - ...
- Expected effects:
  - <effect 1>
  - <effect 2>
- Anchor handlers:
  - sync_entry: <from flow_index>
  - async_entry: <from flow_index>
  - invariant_owner: <from flow_index>
- Related entities: <list>
- Related flows: <list>
- Invariants respected: <list of rule_ids>
- Past incidents: <list of ticket ids>
- Known gates (pre-recorded blockers):
  - <kg.id>: <description> at <location>

## Keyword signals (from requirements text)
<List matched phrases — or "none">

## Past incidents to consider
<Copy from {ticket_dir}/context-expansion.md if present — entities + queues + high-recurrence overlap>

## Investigation goal
For EACH flow in scope, trace EACH TRIGGER PATH end-to-end:
1. From entry handler → cascade → final effect
2. Does each trigger actually REACH the flow's expected effect? Or is there a silent drop?
3. For each drop, what mechanism (silent-overwrite / conditional-guard / early-return / wrong-branch / missing-wire)?
4. Compare against ticket's new requirements — which trigger paths need to be wired/fixed?

## Specific decision questions (from analyze Phase 6b open items + known gates)
<bullets from ticket-context.open_questions + each known_gate.description, if any>

## Return format
Produce `investigation-findings.md` with:
- standard sections (Title, Confirmed, Open assumptions, ...)
- FLOW EXTENSION sections (flow_map per trigger path, Gap Analysis table, Decisions per gap)
- final_status: RESOLVED + suggested_implement_strategy

When DPS finishes, the user resumes this ticket via:
  do-ticket <TICKET_ID> --from-dps=<session-folder>
do-ticket will skip classify/requirements/analyze and enter plan with the full flow map
seeded into plan.md.

## Hard constraints
- Do not write code.
- Do not propose an option that conflicts with a flow invariant (flow_index.flows.<name>.invariants_respected) or a domain invariant in {project_docs}/domain/<Entity>.yaml. DPS-FM-FLOW-INVARIANT-CONFLICT applies.
- Cite each anchor handler with file:line.
- Trace BY TRIGGER PATH, not by field cascade. The question is "does this trigger reach the effect?", not "what does this field do?"
```

**Why 6c is between analyze and Phase 7 (not after plan):** the flow map informs WHAT to plan. After-plan routing means re-doing the plan once DPS returns. Before-plan routing means plan is written ONCE, with full flow context.

**Resume from `phase: awaiting_dps`:** when user invokes `do-ticket <TICKET_ID> --from-dps=<session>`, Phase 0 detects the flag, loads findings (including new flow_map + gaps + decisions), advances state to `phase: analyze` (marked complete), proceeds to Phase 7. The plan phase reads `ctx.flow_findings.*` as primary input alongside `requirements-analysis.md`.
