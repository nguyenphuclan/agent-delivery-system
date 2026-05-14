---
name: domain-problem-solver
description: Multi-step domain investigation skill for open-ended problems with no Jira ticket — bugs, ambiguous requirements, performance issues, cross-service contracts, or "how does X work" questions. Adaptive strategy per problem type (bug-trace, perf-deep-dive, contract-violation, requirement-discovery, question-answer, investigation-driven-by-hypothesis). Iterative clarification + ranked hypotheses + cited domain knowledge. Never writes code. Hands off to do-ticket via investigation-findings.md when implementation is needed. Auto-improves via /learn telemetry.
---

## Pre-flight

**Tier: A** (multi-step investigation, file outputs, possible handoff to do-ticket).

Follow `~/.claude/skills/_shared/pre-flight-protocol.md` BEFORE any other action — runs regardless of how this skill was invoked (direct `/domain-problem-solver`, orchestrator routing, mid-flow from do-ticket FM-3X-SAME-ROOT, mid-flow from learn-crud).

Skill-specific overrides:
- `requires_project_fields`: [active, output] (`repos`/`db` only if cross-project investigation triggered)
- `risk_signals`: none for analysis-only flow; flag g7 if investigation is about prod data / auth surfaces
- `skip_when`: invoked with `resume <session>` AND session folder exists in `open/` (Tier D — resume mode)

User no longer needs `/assistant` prefix — pre-flight is built in.

---

# domain-problem-solver — adaptive investigation orchestrator

## Architecture

Symmetric to do-ticket post-refactor:

- **Spine** (rigid, consistent): every investigation passes through Workspace Resolution → Input Classification → Strategy Pick → Loop → Output → Handoff/Close. Session files always written.
- **Strategies** (plural, adaptive): bug-trace, perf-deep-dive, contract-violation, requirement-discovery, question-answer, investigation-driven-by-hypothesis, cascading-investigation, quick. Picked from `strategies.yaml` selection rules; switchable mid-flow on reclassification.
- **Failure pivots** (registry-driven): DPS-FM-XX entries in `failure-modes.yaml` auto-pivot before falling to Phase 5d Escalation.
- **Shared protocols** (no duplication): clarification, domain-mapping, hypothesis from `~/.claude/skills/_shared/`.
- **Telemetry** (auto-learn): every session writes `investigation-telemetry.yaml` consumed by `/learn`.

### Companion files

| File | Purpose |
|------|---------|
| `strategies.yaml` | Investigation strategies + selection rules |
| `failure-modes.yaml` | DPS-FM-XX registry with auto-pivots |
| `investigation-telemetry-schema.md` | Per-session signal capture for /learn |
| `investigation-findings-schema.md` | Consumable handoff output for do-ticket |
| `~/.claude/skills/_shared/clarification-protocol.md` | Question loop algorithm |
| `~/.claude/skills/_shared/domain-mapping-protocol.md` | Track B knowledge ladder |
| `~/.claude/skills/_shared/hypothesis-protocol.md` | Ranked hypothesis generation |
| `~/.claude/skills/_shared/session-handoff-protocol.md` | Standard envelope to/from other skills |

---

## Triggers

```
/domain-problem-solver                         → smart start (menu OR direct based on input)
/domain-problem-solver <inline problem>        → skip menu, go to Phase 1
/domain-problem-solver --quick <input>         → quick strategy (no clarification, no session files)
/domain-problem-solver resume <filename>       → Mode B
/domain-problem-solver close                   → Mode C
/domain-problem-solver list                    → Mode D
/domain-problem-solver --strategy=<id> <input> → explicit strategy override
```

If no input and no command: show menu, wait for choice.

```
What would you like to do?
1. New Investigation
2. Resume Session
3. Close Session
4. List Sessions
Or describe your problem and I'll start right away.
```

Always respond in **English**, regardless of user language.

---

## Phase 1 — Workspace Resolution

Resolve active workspace by priority:
1. IDE / current directory project name
2. Project explicitly mentioned by user or in a session file
3. Ask: *"Which project are you working in?"*

Once resolved, derive paths from `_config/projects.yaml` → `output_root` field, then read `{project_docs}/_index.yaml` per `_shared/agent-docs-layout.md`. Never hardcode paths.

```
{project_docs}/code/domain_index.yaml
```

If missing or unreadable → DPS-FM-WORKSPACE-AMBIGUOUS / DPS-FM-NO-DOMAIN-MATCH → continue with explicit gap noted.

### Cross-project signals (selective)

Do NOT scan all of `agent-index/` upfront. Detect cross-project signals first:
- Boundary keywords: "sync", "callback", "response from X to Y", "sends to", "receives from"
- Multiple service names mentioned
- Entity not found in primary domain index
- Error on incoming/outgoing API
- Primary index lists a dependency

If a signal is found:
1. List subdirectory names under `agent-index/` (folders only).
2. Match candidates by keyword.
3. **Confirm with user** — *"This seems to involve `<projectB>`. Load its domain index too?"*
4. Load confirmed indexes; reason across them.

Failure → DPS-FM-CROSS-PROJECT-MISSING-INDEX.

---

## Phase 2 — Mode Routing

| Mode | Trigger | Behavior |
|------|---------|----------|
| **A — New Investigation** | Default; inline input or menu choice 1 | Always fresh; never auto-load prior session. If `.md` attachment contains `## Session State` → warn before starting fresh. |
| **B — Resume Session** | `resume <name>` or menu 2 | Load session folder; show resume summary; continue from last round. |
| **C — Close Session** | `close` or menu 3 | Run quality debrief → write `## Resolution Summary` → move folder from `open/` to `closed/`. |
| **D — List Sessions** | `list` or menu 4 | Display open + count of closed. |

**Mode C — Quality debrief (mandatory before closing, skip with "skip"):**

Ask these 3 questions one at a time. Write answers to `investigation-telemetry.yaml.quality_signals`. Empty answers write empty arrays.

> **1. Wrong strategy:** Did the strategy I used fit the problem, or should a different one have been used?
> *(e.g. "should have been cascading-investigation — problem was too vague to trace directly", or "none")*

> **2. Missed hypothesis:** Was there a hypothesis you already suspected but I didn't generate?
> *(e.g. "scheduler timing issue — I mentioned the scheduler but you never explored it", or "none")*

> **3. Unnecessary rounds:** Was there a clarification round where I asked for something you already told me?
> *(e.g. "round 3 asked for affected role but I said 'all roles' in round 1", or "none")*

After collecting answers → write `quality_signals` → write `## Resolution Summary` to `investigation.md` → move session to `closed/`.

Resume summary format:
```
Resuming: <topic>-<date>/investigation.md

Last updated: <date>
Status: <IN_PROGRESS | RESOLVED | BLOCKED>
Strategy: <strategy id>
Context so far:
  Scope: ... | Module: ... | Environment: ...
Current hypotheses:
  1. ...
Open questions:
  - ...
Continuing from: <next step>
```

---

## Phase 2b — Complex case detection

Before classifying, check signals:

**Problem-type-shift risk:** input mixes bug + requirement language. Flag — strategy may reclassify mid-flow (Phase 5b).

**Cascading risk:** vague high-level problem ("performance is bad", "sync doesn't work") with no concrete trigger. Pick `cascading-investigation` strategy — decompose before deep dive.

**Hypothesis-led risk:** input contains "I think it's because…", "is it possible that…". Pick `investigation-driven-by-hypothesis` — test theirs, don't generate new ones.

---

## Phase 3 — Classify input

| Type | Signals |
|------|---------|
| **Bug** | error, fails, wrong, unexpected, broken |
| **Requirement** | should, need to, improve, add, change behavior |
| **Question** | how/why/what about a domain concept |
| **Vague** | unclear intent or missing key details → DPS-FM-INPUT-TOO-VAGUE |

---

## Phase 3b — Pick strategy

Load `strategies.yaml`. Apply `selection_rules` top-down — first match wins. If user passed `--strategy=<id>`, use that.

Save chosen strategy to session telemetry. Strategy can switch later via `strategy_promotions` block.

---

## Phase 4 — Clarification loop

**Follow `~/.claude/skills/_shared/clarification-protocol.md`** with these DPS-specific overrides:

| Override | Value |
|----------|-------|
| `max_rounds` | 7 (quick strategy: 0; question-answer: 2) |
| `dimensions` | Default checklist (Scope, Trigger, Expected/Actual, Environment, Affected parties, Frequency, Recent changes) |
| `exit_when` | First exit condition met (per shared protocol) |
| `escalate_to` | Phase 5d Escalation block |

Failure: max rounds reached → DPS-FM-CLARIFY-LOOP-STUCK.
Contradiction unresolved → DPS-FM-CONTRADICTION-UNRESOLVED.

Per-round update: append `[round-NN]` to `investigation.log.md` and refresh `investigation.md` summary.

### Fast eliminators (ask before generating hypotheses)

These single questions prune entire hypothesis branches. Check applicability before diving into analysis — if relevant, ask them in the first clarification round:

| Signal in input | Fast-eliminator question | Branch pruned if "yes" |
|-----------------|--------------------------|------------------------|
| access / permission / can't see / denied | "Can the affected user access the resource (page, task detail, record) at all?" | Eliminates VIEW permission hypotheses |
| works for A but not B | "Is the failing user in the same role/group/org as the working user — confirmed, not assumed?" | Eliminates config-parity hypotheses |
| started failing recently | "Was there a deployment, data migration, or config change in the last 48 hours?" | Focuses investigation on delta |
| intermittent / sometimes works | "Does the failure reproduce consistently for the same user on the same resource, or is it random?" | Splits into cache vs data vs race |

Do not ask all of them — pick only those that apply given the input. One fast eliminator can save multiple analysis rounds.

---

## Phase 5 — Analysis

### 5a. Domain Mapping

**Follow `~/.claude/skills/_shared/domain-mapping-protocol.md`** with:

| Override | Value |
|----------|-------|
| `tier_cap` | 5 (quick: 2) |
| `must_cite_rule_id` | true for invariant questions |
| `unknown_handling` | flag-and-continue (warn user, don't block) |

Cache resolved entities + cited rule_ids in session log so resume doesn't re-query.

### 5a'. Context Expansion (between domain mapping and hypothesis generation)

Pre-loads `incidents.yaml` + `topology.yaml` filtered to this investigation's scope. Output: `context-expansion.md` in session folder. **Primary input to hypothesis generation in 5b** — surfaces past incidents and cross-repo connectivity that would otherwise require the agent to "guess" the right pattern.

This is where DPS gets its world-model boost: instead of forming hypotheses from clarification answers + domain rules alone, it also draws from real past bugs and real broker topology.

**Skip conditions:**
- Both `{project_docs}/incidents/incidents.yaml` AND `{project_docs}/topology/topology.yaml` missing → skip silently; log to telemetry: `context_expansion: not_available`
- `problem_type == Question` → skip (question-answer doesn't need bug-pattern priming)
- `problem_type == Requirement` → skip (incidents are about past bugs; not applicable for new feature exploration)
- `strategy == quick` → skip (--quick has no session files; speed matters more)
- `strategy == requirement-discovery` → skip (same reason as Requirement)

For `bug-trace`, `perf-deep-dive`, `contract-violation`, `investigation-driven-by-hypothesis`, `cascading-investigation` → ALWAYS run.

**Algorithm (per session — runs ONCE after first clarification round completes):**

```
EXP-1  Build scope vector from clarification answers + user's original problem:
         - components: project-specific component names mentioned (e.g. Service, Fulfillment)
         - keywords_from_problem: lowercase ≥4-char tokens from problem statement
         - keywords_from_clarification: lowercase ≥4-char tokens from all clarification answers
         - mentioned_classes: ProperCase identifiers in problem + answers (e.g. "OrderSyncJobQueueFlow")
         - mentioned_queues: UPPER_SNAKE_CASE tokens (e.g. "ORDER_SYNC_JOB", "Notification")
         - mentioned_entities: from cached_entities in 5a Domain Mapping result
         - mentioned_repos: any token matching {project_docs}/code/domain_index.yaml services map

EXP-2  Read {project_docs}/incidents/incidents.yaml (if status: fresh in _index.yaml).
       Score each incident:
         score = 0
         + 3 if any incident.components matches any scope.components
         + 2 per match between scope.keywords and incident.similar_pattern_keywords
         + 2 per match between scope.mentioned_entities and incident entities (root_cause text + summary)
         + 1 per match between scope.keywords and incident.root_cause_1line tokens
         + 2 if incident.recurrence_risk == "high" AND score > 0
         + 1 if incident.confidence == "confirmed"
       Output: top 10 by score, OR all with score ≥ 4, whichever is smaller

EXP-3  Read {project_docs}/topology/topology.yaml (if status: fresh).
       For each queue in queues:
         match_signals = []
         if queue.name in mentioned_queues → match_signals += ["queue-name"]
         if any published_by[].class in mentioned_classes → match_signals += ["publisher-class"]
         if any consumed_by[].class in mentioned_classes → match_signals += ["consumer-class"]
         if any published_by[].repo or consumed_by[].repo in mentioned_repos → match_signals += ["repo"]
         if any keyword in queue.cross_links.incidents overlaps with incidents from EXP-2 → match_signals += ["incident-overlap"]
       Include queue (full record) if match_signals non-empty.

EXP-4  Special checks (high-value bug-trace signals):
         For each `high`-severity health_flag on matched queues:
           Surface to "Architectural concerns + history" block (will become candidate hypothesis in 5b)
         For each matched queue with cross-linked incidents that have recurrence_risk=high:
           Surface to "Strong recurrence signal" block (top-priority hypothesis seed)

EXP-5  Write {session_folder}/context-expansion.md with:
         - Past incidents matching scope (top 10 ranked by score)
         - Relevant queues + health flags + cross_linked incidents
         - Strong recurrence signals (incident history + matching scope)
         - "Hypothesis seeds" — bullet list of distinct root_cause_1line strings from matched incidents
           (these become inputs to 5b hypothesis generation, NOT direct hypotheses)

EXP-6  Update investigation.log.md:
         [round-NN] Context expansion
         **Sources:**
           incidents.yaml: <N matched, top by score>
           topology.yaml: <M queues matched>
         **High-risk overlap:** [<ids>]
         **Hypothesis seeds:** <count>
         **File:** context-expansion.md

EXP-7  Update investigation-telemetry.yaml:
         context_expansion:
           ran_at: <ISO>
           incidents_available: <bool>
           topology_available: <bool>
           incidents_matched: [<ids>]
           topology_queues_matched: [<names>]
           hypothesis_seeds_count: <int>
           file: context-expansion.md
```

**context-expansion.md format** (DPS variant — emphasis on hypothesis priming):

```markdown
# Context Expansion — <session-topic>

Generated by DPS Phase 5a'. **5b hypothesis generation will draw from this.**

## Strong recurrence signals (high-priority hypothesis seeds)

These past incidents have recurrence_risk=high AND overlap with current scope.
A hypothesis matching one of these patterns should rank near the top in 5b.

### <id> — <root_cause_1line>
- **Past trigger**: <symptom_1line>
- **Past fix layer**: <code/infra/external/hybrid>
- **Why matched**: <component overlap, keyword, queue, etc.>
- **Lessons**: <bullets>
- **Validates these hypothesis types**: <e.g. "auto-ack with high prefetch on pod restart">

## Past incidents matching this scope (ranked)

<For each: id, symptom, root_cause_1line, score, match basis, confidence>

## Topology context

<For each matched queue: publishers, consumers, health_flags with severity, cross-linked incidents>

## Hypothesis seeds (raw)

Bullet list of distinct root_cause_1line strings from matched incidents:
- <seed 1>
- <seed 2>
- ...

5b should consider each seed as a candidate hypothesis. Cite the source incident ID
in the hypothesis's "Why this could be it" field. If a seed is rejected by clarification
context, note rejection rationale in investigation.log.md.
```

**Skip handling in 5b:** if 5a' skipped (problem_type=Question/Requirement or both artifacts missing), 5b proceeds with domain-mapping-only context as before.

### 5b. Hypothesis generation (when problem_type=Bug or unclear)

**Follow `~/.claude/skills/_shared/hypothesis-protocol.md`** with:

| Override | Value |
|----------|-------|
| `min_hypotheses` | 3 (quick: 1) |
| `max_hypotheses` | 5 |
| `falsification_required` | true |
| `surface_to_user` | top 3 |

**Priming from 5a' (when context-expansion.md exists):**
- The "Hypothesis seeds" section of context-expansion.md is the FIRST input. Promote any seed that survives clarification context into a candidate hypothesis.
- "Strong recurrence signals" auto-rank near top of generated list (recurrence is strong prior).
- Each promoted seed-hypothesis MUST cite the source incident ID in its rationale: `<root cause hypothesis> (matches TICKET-XXXXX recurrence pattern)`.
- Health flags from topology with severity=high on matched queues → auto-candidate hypothesis: e.g. "queue Notification has auto-ack + high prefetch (c-101) → consumer pod restart drops in-flight messages".

Surface ranked hypotheses with falsification tests. After user runs a falsification → loop back, narrow.

If all top-3 falsified, backlog empty → DPS-FM-NO-HYPOTHESIS-LEFT.

**Hypothesis-first discipline (strict):** Generate and surface hypotheses BEFORE reading code or querying the DB. The purpose of reading code/DB is to falsify or confirm a specific hypothesis — not to discover one. The flow must be:

```
1. (Phase 5a) Domain Mapping — cite rule_ids + entities
2. (Phase 5a') Context Expansion — load incidents + topology, write hypothesis seeds
3. Form hypotheses from: domain knowledge + clarification answers + 5a' seeds
4. Surface top 3 to user with falsification test per hypothesis
5. Only then read code / query DB to run the falsification test
```

Never start with "let me read the file and see what's there." Start with "here are 3 hypotheses; H1 says X — let me check Y to falsify it." This prevents the sequential file-read loop where each read triggers another read with no prior direction.

### 5b'. Reclassification (when shift detected)

If during analysis the problem type shifts (bug → requirement, question → bug, etc):
1. Announce: *"Based on what we've found, this is actually a `<new type>` rather than a `<old type>`. Reclassifying."*
2. Carry all gathered context forward — discard nothing.
3. Switch strategy per `strategies.yaml.strategy_promotions`.
4. Update `investigation.md` Type field; log to `investigation-telemetry.reclassifications[]`.

### 5c. Impact assessment

- Other modules / flows / parties affected
- Category: data / validation / flow / integration
- Risk level: low / medium / high / critical

### 5d. Escalation — when analysis hits a wall

When the investigation needs source code, system logs, or specialist knowledge beyond the domain index:

```
## Escalation Required

**Reason:** [why domain-level reasoning can't resolve]
**What is needed:** [specific access or info]
**Who can help:** [team / role]
**What we know so far:** [summary of confirmed context + hypotheses]
**Suggested next step:** [concrete action]
```

Mark session `BLOCKED` and save. Investigation stays resumable when info is available.

---

## Output formats (per problem_type)

### Bug
```markdown
## Bug Analysis: <title>

**Observed:** <what happens>
**Expected:** <what should happen>
**Scope:** <module / flow / environment>
**Affected parties:** <who>

### Hypotheses (ranked)
1. **[Most likely]** ... — falsify: ...
2. ...
3. ...

### Recommended Next Steps
- [ ] Investigation action
- [ ] Fix intent (no code)

### Assumptions
- ...

### Open Questions
- ...
```

### Requirement
```markdown
## Requirement: <title>

**Type:** Feature / Improvement / Behavior change
**Scope:** <module>
**Priority:** TBD

### Context
### Problem Statement
### Acceptance Criteria
- [ ] ...

### Implementation Plan (high-level, no code)
1. ...

### Risks & Considerations
```

### Question
Concise, domain-grounded answer with cited rule_ids / entities. No bullet templates needed.

---

## Phase 6 — Resolution verdict + decision

After delivering Phase 5 output, synthesize and present a **Verdict Block** before asking the user what to do.

### Verdict Block (always output this)

```markdown
## Verdict

**Is this an issue?** Yes | No | Inconclusive
**Why:** <1–2 sentence root cause or reason>
**Confidence:** High | Medium | Low — <one-phrase reasoning>
**Recommended next step:** <specific action>
```

Confidence calibration:
- **High**: root cause confirmed via domain rules + evidence; hypothesis trail complete
- **Medium**: likely hypothesis strongly supported but not fully falsified
- **Low**: circumstantial evidence only; key signals missing or contradictory

### Resolution paths

| Verdict | When | Action |
|---------|------|--------|
| Not an issue | Evidence rules out a defect | Explain + status `RESOLVED`. Offer to close. No ticket. |
| Issue, no code needed | Config / data / doc fix | Recommend fix inline. Offer `runbook` if likely to recur. Status `RESOLVED`. |
| Issue, code change needed | Bug or behavior gap confirmed | Generate `ticket-draft.md` + `investigation-findings.md`. Confirm with user. |
| Inconclusive / blocked | Root cause unknown, needs more access | Phase 5d escalation. Status `BLOCKED`. No ticket. |
| Not sure yet | Clarification still needed | Keep `IN_PROGRESS`. Log open questions. |

### When verdict = "code change needed"

**Guard:** if `final_status == BLOCKED` → do NOT generate handoff files. Escalate instead (Phase 5d). Generating findings from a BLOCKED session produces incomplete data that will silently corrupt the do-ticket plan phase.

Generate **two files** before asking user to proceed:

1. **`ticket-draft.md`** — user-facing; ready to paste into Jira. Per `investigation-findings-schema.md → ticket-draft schema`.
2. **`investigation-findings.md`** — machine-facing; consumed by `do-ticket --from-dps`. Per `investigation-findings-schema.md`.

Then confirm — output this exact block:
```
ticket-draft.md and investigation-findings.md written to:
  <full session folder path>

Next steps:
  1. Copy ticket-draft.md into Jira → get TICKET_ID
  2. Run: do-ticket <TICKET_ID> --from-dps=<session-folder-name>
     (folder name only, not full path — e.g. payment-timeout-bug-2025-01-10)

do-ticket will skip classify, requirements, and analyze phases.
It will carry forward: entities, risk, open assumptions, and suggested strategy.
```

If `final_status == PARTIAL` → add warning line: *"Note: `final_status` is PARTIAL (root cause not fully confirmed). do-ticket will NOT skip the analyze phase — it will use findings as seed context only."*

**Never auto-create a Jira ticket or auto-handoff.** Always wait for explicit user confirmation.

---

## Phase 7 — Save session files

Folder per topic:

```
{output}/domain-problem-solver/open/<topic>-<YYYY-MM-DD>/
  investigation.md                       ← user-facing summary (overwritten each round)
  investigation.log.md                   ← agent-facing append-only log
  investigation-telemetry.yaml           ← signal capture
  context-expansion.md                   ← optional; produced by Phase 5a' if incidents/topology available
  investigation-findings.md              ← only when verdict = code change needed
  ticket-draft.md                        ← only when verdict = code change needed (ready-to-paste Jira description)
```

Folder name collision (different investigation, same name+date): append `-2`, `-3`.

This folder is the **session workspace** — other skills (do-ticket, jira-to-requirements) may place related files here.

### File 1 — `investigation.md` (user-facing, refreshed each round)
```markdown
## Investigation: <title>

**Workspace:** <project(s)>
**Type:** Bug | Requirement | Question
**Status:** IN_PROGRESS | RESOLVED | BLOCKED | RECLASSIFIED | CLOSED
**Strategy:** <strategy id>
**Last updated:** <date>

## Context
- Scope / Module / Environment / Trigger / Expected / Actual / Parties

## Current Hypotheses
1. ...

## Latest Output
<most recent answer or plan — replaced each update>

## Open Questions
## Next Step
```

### File 2 — `investigation.log.md` (agent-facing, append-only)
```markdown
## Session Log: <title>

### [round-01] Initial Input
**User:** ...

### [round-02] Clarification
**Agent:** <question>
**User:** <answer>

### [round-03] Contradiction Flagged
**Agent:** "This contradicts round-01 — which is correct?"
**User:** <correction>
**Note:** round-01 answer overridden

### [round-04] Domain Mapping
**Cited:** ST-LIFECYCLE-3 (Tier 1 quickref hit)
**Entities:** ServiceTask

### [round-05] Hypotheses
1. ... [confidence: Likely]
2. ... [confidence: Plausible]

### [round-06] Strategy switch
**Trigger:** cross-project signal — load the relevant cross-project domain index
**From:** bug-trace → **To:** contract-violation
```

### File 3 — `investigation-telemetry.yaml`
Per `investigation-telemetry-schema.md`. Append on every phase transition + at session close.

### File 4 — `investigation-findings.md` (only on handoff)
Per `investigation-findings-schema.md`. Generated at Phase 6 when user accepts handoff.

**On resume:** load all files, rebuild context from log, show resume summary.

**On close:** entire folder moves from `open/` to `closed/`. Telemetry follows.

---

## Strategy quick reference

| Strategy | When | Output |
|----------|------|--------|
| `bug-trace` | clear error / unexpected behavior | ranked hypotheses + falsification tests |
| `perf-deep-dive` | slow/timeout/scale/latency | bottleneck hypotheses + measurement recommendations |
| `contract-violation` | cross-service / API / event | producer/consumer/contract analysis (multi-project) |
| `requirement-discovery` | fuzzy feature request | structured Requirement output |
| `question-answer` | how/why/what about system | concise grounded answer (1 round max) |
| `investigation-driven-by-hypothesis` | user has a theory | test theirs, verdict + evidence |
| `cascading-investigation` | vague high-level | decompose first, then switch to specific strategy |
| `quick` | --quick flag | direct answer, no session files |

Full registry: `strategies.yaml`. Selection rules: `strategies.yaml.selection_rules`.

---

## Failure modes — quick reference

Full registry: `failure-modes.yaml`.

| Trigger | DPS-FM-XX | Pivot |
|---------|-----------|-------|
| Clarification loop reaches max_rounds | DPS-FM-CLARIFY-LOOP-STUCK | drop to question-answer or escalate |
| User contradiction unresolved | DPS-FM-CONTRADICTION-UNRESOLVED | log both, surface to stakeholder |
| Entity not in domain index | DPS-FM-NO-DOMAIN-MATCH | flag gap + continue with assumption |
| All top-3 hypotheses falsified | DPS-FM-NO-HYPOTHESIS-LEFT | Tier 4 cross-relationships → backlog → escalate |
| Cross-project secondary index missing | DPS-FM-CROSS-PROJECT-MISSING-INDEX | continue primary-only, propose /scan-init |
| Workspace ambiguous | DPS-FM-WORKSPACE-AMBIGUOUS | ask once with project list |
| Input < 20 chars / purely emotional | DPS-FM-INPUT-TOO-VAGUE | minimum-viable clarify or cascading strategy |
| Resume file corrupted | DPS-FM-RESUME-FILE-CORRUPTED | rebuild from log if intact, else ask user |
| Handoff with empty confirmed_facts | DPS-FM-HANDOFF-INCOMPLETE | refuse handoff, escalate |
| Context-expansion artifacts stale (fingerprint drift in incidents/topology) | DPS-FM-CTX-EXPANSION-STALE | re-run scan-init incidents and/or topology, then re-enter 5a' |
| All hypothesis seeds from 5a' falsified | DPS-FM-RECURRENCE-NO-MATCH | log "false positive from incidents"; fall back to domain-only hypothesis generation |

Unmatched failure → log to `investigation-telemetry.unknown_failures[]` → /learn proposes new entry after recurrence ≥3.

---

## Constraints

- Never write implementation code.
- Never ask for file names, class names, or low-level technical details.
- Always ground analysis in the domain index — cite rule_ids when claiming an invariant.
- Always output in English (regardless of input language).
- **Session files are a hard gate**: write/update `investigation.md` and `investigation.log.md` BEFORE delivering the analysis response each round — not after. If files cannot be written, say so explicitly before proceeding.
- Flag contradictions immediately — never silently overwrite earlier answers.
- When hitting a wall, escalate (Phase 5d) — never guess beyond available domain knowledge.
- Append-only telemetry; closed at session end.
- Never auto-create Jira tickets or auto-handoff to other skills — explicit user confirmation required.
