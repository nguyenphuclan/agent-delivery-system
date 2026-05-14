---
name: run-telemetry-schema
description: Schema for run-telemetry.yaml — per-ticket signal capture used by /learn to detect recurring failure patterns, strategy effectiveness, and emerging bottlenecks across tickets.
---

# run-telemetry.yaml — schema and protocol

## Why this exists

Without telemetry, the only learning loop is manual: human notices a recurring pain → adds an RW-XX line → hopes future runs catch it. With telemetry, every run produces signal; `/learn` reads across tickets and proposes catalog updates automatically.

## Location

```
{output}/tickets/<TICKET_ID>/run-telemetry.yaml
```

One file per ticket. Append-only during the run. Closed when phase=done.

## Schema

```yaml
ticket_id: PROJECT-1234
ticket_type: crud-feature
risk_profile: medium
schema_version: 1
started_at: 2026-04-12T08:00:00
ended_at: 2026-04-12T15:30:00
duration_seconds: 27000

# Phase-by-phase outcomes
phases:
  - name: branch
    started: 2026-04-12T08:00:00
    ended: 2026-04-12T08:01:00
    duration_seconds: 60
    strategy: null
    outcome: success         # success | blocked | skipped | aborted
    blocked_reason: null
    iterations: 1
  - name: classify
    outcome: success
    auto_classified_as: crud-feature
    user_overrode: false
  - name: requirements
    outcome: success
    duration_seconds: 180
    artifact_size_kb: 3.2
  - name: analyze
    strategy: full-domain-mapping
    outcome: blocked
    blocked_reason: "open question: which user role can cancel?"
    iterations: 2          # blocked once, resolved, ran again
  # ... etc

# Strategy outcomes (for selection_rules learning)
strategies_used:
  analyze: full-domain-mapping
  test-cases: exhaustive
  plan: first
  implement: tdd-strict
  learn-crud: full-learn-then-use

strategy_outcomes:
  - phase: implement
    strategy: tdd-strict
    result: success
    notes: "All RED → GREEN cleanly. No pivot needed."
  - phase: implement
    strategy: tdd-strict
    result: pivoted
    pivoted_to: prototype-then-harden
    pivot_reason: "FM-3X-SAME-ROOT after 3 attempts on EF Core query"

# Failure modes hit
failure_modes_hit:
  - id: FM-DLL-LOCKED
    fired_at_phase: unit-tests
    fired_at: 2026-04-12T09:15:00
    pivot_used: ask-user-close-vs
    resolved: true
    resolution_seconds: 240
  - id: FM-3X-SAME-ROOT
    fired_at_phase: implement
    fired_at: 2026-04-12T11:30:00
    pivot_used: switch-strategy
    resolved: true
    resolution_seconds: 1800

# Human gates triggered
gates_triggered:
  - id: G1
    fired_at_phase: analyze
    reason: "open question: cancel role"
    user_choice: "task-owner only"
    duration_seconds: 600
  - id: G3
    fired_at_phase: implement
    reason: "DB migration required"
    user_choice: "applied locally"
    duration_seconds: 120

# Unknown failure patterns (candidates for new FM-XX entries)
unknown_failures:
  - phase: implement
    error_signature: "InvalidOperationException: The instance of entity type 'X' cannot be tracked"
    occurrences: 3
    resolution: "Detached existing entity before Update()"
    not_in_registry: true       # if true, /learn proposes new FM-XX

# Promotions / type changes mid-flow
type_promotions:
  - from: bugfix-small
    to: bugfix-investigated
    at_phase: implement
    reason: "FM-3X-SAME-ROOT — root cause needed investigation"

# Update cycles
update_cycles:
  count: 0
  triggers: []  # ["pr-review-feedback", "qc-found-bug", "requirements-changed"]

# PR review rounds
review_rounds:
  count: 0
  must_fix_count: 0
  split_requests: 0

# Post-ticket quality debrief (collected at Phase 23)
# Written by user, prompted by 3 specific questions.
# Empty = debrief was skipped.
quality_signals:
  noise: []
  # Each entry: phase that asked for something it should have known
  # Format: { phase: "analyze", description: "Asked for base_branch it already had" }

  wrong_output: []
  # Each entry: output the user had to manually correct
  # Format: { artifact: "plan.md", description: "Wrong service layer — should be Application not Domain" }

  missing: []
  # Each entry: thing that was absent from a phase output but should have been there
  # Format: { phase: "test-cases", description: "No negative test for duplicate cluster" }
```

## Writer responsibilities

| Field | Written by |
|-------|-----------|
| `ticket_id`, `started_at`, `ticket_type` | do-ticket phase 1 (`branch`) / phase 2 (`classify`) |
| `phases[]` | do-ticket after each phase |
| `strategies_used` | do-ticket when strategy is picked |
| `strategy_outcomes` | do-ticket when phase ends |
| `failure_modes_hit[]` | do-ticket when FM-XX matches |
| `gates_triggered[]` | do-ticket when gate fires |
| `unknown_failures[]` | implement / learn-crud / others when an unrecognized error pattern recurs ≥3 times |
| `type_promotions[]` | do-ticket on promotion |
| `ended_at`, `duration_seconds` | do-ticket at phase=done |
| `quality_signals` | User — prompted by Phase 23 debrief (3 questions) |

## How /learn consumes telemetry

`/learn` reads telemetry across **all** tickets in `{output}/tickets/*/run-telemetry.yaml` and produces:

### 1. New FM-XX proposals
- Group `unknown_failures[]` by `error_signature`
- If signature appears in ≥3 different tickets → propose new entry to `do-ticket/failure-modes.yaml`
- Include: detect signal, suggested pivot (from observed resolutions), severity inference

### 2. Strategy default tuning
- For each phase, compute success rate of each strategy
- If strategy A has <50% success rate for ticket_type X but strategy B has >80% → propose updating `selection_rules` in `<skill>/strategies.yaml`

### 3. Gate analytics
- Average duration per gate ID
- Most-fired gate → candidate for proactive auto-pivot
- Gate that always resolves the same way → candidate for default behavior

### 4. Phase bottleneck detection
- Phase with high `duration_seconds` median → suggest investigation
- Phase with many `iterations` → suggest more upfront validation

### 5. Pattern registry promotions
- If implement frequently flags pattern violations → suggest priority upgrade in `public-project-docs/<project>/patterns/_index.yaml`

### 6. Quality signal analysis
- `noise[]` grouped by phase: if same phase appears ≥2 tickets → phase is asking for something it should already have → propose pre-loading that data in the phase's pre-phase step
- `wrong_output[]` grouped by artifact: if same artifact wrong ≥2 tickets → that phase's output criteria is under-specified → propose sharpening the phase contract or strategy
- `missing[]` grouped by phase: if same kind of missing thing appears ≥2 tickets → propose adding it to the phase contract's output checklist
- Any entry with ≥2 occurrences → surface to user as concrete SKILL.md improvement proposal (not just an observation)

## Privacy / cleanup

- run-telemetry.yaml is local-only (under `public-project-docs/`)
- Contains no secrets — only phase names, error signatures, durations
- Cleanup: do-ticket `done` retains the file. `/doc-manager CLEAN-TICKETS` archives old telemetry alongside ticket files.
