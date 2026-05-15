---
name: investigation-telemetry-schema
description: Schema for investigation-telemetry.yaml — per-DPS-session signal capture used by /learn to detect recurring failure patterns, strategy effectiveness, and clarification-loop bottlenecks across investigations.
---

# investigation-telemetry.yaml — schema

## Why this exists

Same purpose as do-ticket's `run-telemetry.yaml` — turn every DPS run into signal that improves future runs. Without telemetry, lessons get lost. With it, /learn proposes new DPS-FM-XX entries, strategy default tunings, and shared protocol updates automatically.

## Location

```
{output}/domain-problem-solver/open/<topic>-<YYYY-MM-DD>/investigation-telemetry.yaml
```

When session moves to `closed/`, telemetry moves with it.

## Schema

```yaml
session_id: terminate-603-bug-2026-05-02
schema_version: 1
problem_type: bug                    # bug | requirement | question | vague
strategy: bug-trace                  # see strategies.yaml
started_at: 2026-05-02T10:00:00
ended_at: 2026-05-02T11:30:00
duration_seconds: 5400
final_status: RESOLVED               # RESOLVED | BLOCKED | RECLASSIFIED | CLOSED-NO-RESOLUTION

# Workspace
workspace:
  primary: <project>-api
  secondary: []                      # cross-project investigations

# Strategy outcomes
strategy_changes:
  - from: bug-trace
    to: contract-violation
    at_round: 4
    reason: "Cross-project signal detected — error originates in callback from <project>-party-service"

# Clarification loop
clarification:
  rounds_total: 5
  rounds_to_first_hypothesis: 3
  exit_condition: "sufficient context for 1 confident hypothesis"
  contradictions_flagged: 0
  user_dont_know_count: 0

# Hypothesis loop
hypotheses:
  generated_count: 4
  surfaced_to_user: 3
  falsified: 2
  confirmed: 1
  backlog_promoted: 1                # times we revisited backlog after top-3 falsified

# Domain mapping
domain_mapping:
  tier1_quickref_hits: 2             # _quickref.yaml hits
  tier2_grep_hits: 1
  tier3_entity_shard_loads: 1
  tier4_relationships_loads: 0
  tier5_source_reads: 0              # should be rare
  cited_rule_ids: ["ST-LIFECYCLE-3"]
  domain_gaps_flagged:
    - entity: ServiceTask.OnHoldReason
      tier_searched: [1, 2, 3]
      result: not_in_index

# Failure modes hit
failure_modes_hit:
  - id: DPS-FM-NO-DOMAIN-MATCH
    fired_at_round: 2
    pivot_used: flag-gap-continue
    resolved: true
    resolution: "Continued with assumption tagged"

# Unknown patterns (candidates for new DPS-FM-XX)
unknown_failures:
  - signature: "user kept changing the expected behavior every round"
    occurrences: 1
    not_in_registry: true

# Context Expansion (Phase 5a')
# Captured when 5a' runs. All-null block if skipped (Question, Requirement, quick, both artifacts missing).
context_expansion:
  ran_at: null                       # ISO timestamp or null if skipped
  skipped_reason: null               # "problem_type_question" | "problem_type_requirement" | "strategy_quick" | "both_artifacts_missing" | "user_declined_stale_refresh" | null
  incidents_available: null          # bool — true if incidents.yaml present + fresh at run time
  topology_available: null           # bool — true if topology.yaml present + fresh at run time
  incidents_matched: []              # list of incident IDs scoring above threshold
  topology_queues_matched: []        # list of queue names matched on scope
  high_risk_overlap: []              # incident IDs with recurrence_risk=high AND keyword/component overlap
  hypothesis_seeds_count: 0          # how many distinct root_cause_1line strings became seeds
  seeds_promoted_to_hypotheses: 0    # of those seeds, how many made it to top-3 hypothesis list in 5b
  seeds_falsified: 0                 # of those, how many got falsified in 5b loop
  file: null                         # "context-expansion.md" if produced, else null

# Reclassifications
reclassifications:
  - from: question
    to: bug
    at_round: 2
    reason: "User's question turned out to describe an actual error"

# Output
output:
  type: ranked-hypothesis-list       # ranked-hypothesis-list | structured-requirement | answer
  led_to_handoff: true
  handoff_target: do-ticket
  handoff_envelope: dps__to__do-ticket__terminate-603-bug__20260502-113000.md

# Resume / re-open events
resume_events:
  - paused_at: 2026-05-02T10:30:00
    resumed_at: 2026-05-02T11:00:00
    reason: "user got coffee"

# Post-session quality debrief (collected at Mode C close)
# Written by user, prompted by 3 questions. Empty = debrief skipped.
quality_signals:
  wrong_strategy: []
  # Strategy used vs what would have been better
  # Format: { used: "bug-trace", would_have_been: "cascading-investigation",
  #            reason: "problem was too vague — should have decomposed first" }

  missed_hypothesis: []
  # Hypotheses the user knew but agent didn't generate
  # Format: { description: "Could be a timing issue with the scheduler lock",
  #            why_missed: "agent focused on state machine, ignored scheduler context" }

  unnecessary_rounds: []
  # Clarification rounds that asked for already-provided info
  # Format: { round: 3, asked_for: "affected user role",
  #            already_stated_in: "round 1 — user said 'happens for all roles'" }
```

## Writer responsibilities

| Field | Written by |
|-------|-----------|
| Top-level metadata, started_at, problem_type, strategy | DPS Phase 1-3 |
| `clarification.*` | DPS Phase 4 (each round + exit) |
| `hypotheses.*` | DPS Phase 5b (per generation, falsification) |
| `domain_mapping.*` | shared/domain-mapping-protocol consumers (every tier hit) |
| `failure_modes_hit[]` | DPS when a DPS-FM-XX matches |
| `unknown_failures[]` | DPS when a failure pattern doesn't match registry |
| `strategy_changes[]` | DPS on strategy promotion |
| `reclassifications[]` | DPS Phase 5b reclassification event |
| `context_expansion.*` | DPS Phase 5a' (incidents/topology priming) — updated again at 5b end with `seeds_promoted_to_hypotheses` + `seeds_falsified` counts |
| `output.*`, `final_status`, `ended_at`, `duration_seconds` | DPS Phase 6 / close |
| `resume_events[]` | DPS Mode B Resume |
| `quality_signals` | User — prompted by Mode C close debrief (3 questions) |

## How /learn consumes investigation telemetry

`/learn` reads telemetry across **all** DPS sessions in `{output}/domain-problem-solver/{open,closed}/*/investigation-telemetry.yaml` and produces:

### 1. New DPS-FM-XX proposals
Group `unknown_failures[]` by `signature`. ≥3 occurrences across sessions → propose new entry to `domain-problem-solver/failure-modes.yaml`.

### 2. Strategy tuning
For each `problem_type`, compute success rate of each strategy. If strategy A < 50% success but B > 80% → propose updating selection_rules in `strategies.yaml`.

### 3. Clarification loop bottleneck detection
- Median `rounds_to_first_hypothesis` per strategy
- Sessions exceeding `max_rounds` → strategy needs better clarification dimensions
- Frequent `contradictions_flagged` → user is unclear; suggest different clarification approach

### 4. Domain index gap promotion
`domain_mapping.domain_gaps_flagged[]` accumulated across sessions:
- Same entity/aspect missing in ≥3 sessions → propose `/scan-update` task to add it
- Surface to user as "kho domain knowledge cần bổ sung"

### 5. Reclassification patterns
- `question → bug` reclassifications frequent → suggest tighter input classification heuristics
- Many `bug → requirement` shifts → users describe missing features as bugs; could improve input templates

### 6. Quality signal analysis
- `wrong_strategy[]` ≥2 sessions same `used` strategy → demote that strategy's `selection_rules` priority for that problem type
- `missed_hypothesis[]` ≥2 sessions same `why_missed` pattern → propose adding that signal to Phase 2b complex case detection or hypothesis generation prompts
- `unnecessary_rounds[]` same `asked_for` topic repeated ≥2 sessions → that dimension should be extracted from earlier context, not asked; propose adding to fast-extractors list

### 7. Handoff effectiveness
- DPS sessions with `led_to_handoff=true` followed by do-ticket → cross-reference with do-ticket telemetry
- Handoffs that are `rejected` by receiving skill → DPS confirmed_facts wasn't actionable

### 8. Context expansion effectiveness (Phase 5a' signal)
- `context_expansion.seeds_promoted_to_hypotheses / hypothesis_seeds_count` aggregated across sessions:
  - Ratio > 0.5 → seeds usefully prime hypothesis generation; expansion is paying off
  - Ratio < 0.2 across ≥5 sessions → seeds rarely usable; tune scoring algorithm in 5a' EXP-2 (raise threshold, change weights) or consider problem_type filter
- `context_expansion.seeds_falsified / seeds_promoted_to_hypotheses` per session:
  - Ratio > 0.7 across ≥3 sessions in same problem_type → DPS-FM-RECURRENCE-NO-MATCH pattern; incidents corpus may be stale for this domain → propose scan-init incidents refresh
- `context_expansion.skipped_reason = both_artifacts_missing` ≥5 sessions → high-leverage opportunity; surface to user as "no incidents/topology — run scan-init for X% confidence boost"
- Sessions where 5a' produced 0 incident matches AND 0 topology matches BUT verdict ended `code change needed` → investigation was in untouched territory; this case is itself valuable data (proves scope was outside historical corpus)

## Privacy / cleanup

- Local-only under `public-project-docs/`
- No secrets — only failure signatures, durations, hypothesis labels, rule_ids
- Cleanup: telemetry follows session — `closed/` archive triggers archive of telemetry too
