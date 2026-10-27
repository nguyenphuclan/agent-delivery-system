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

## ⚠ REQUIRED MINIMUM — write this much or the file does not exist

Audited 2026-08-03: **zero** `run-telemetry.yaml` files existed across every ticket, despite this schema,
two `phase-contracts.yaml` output declarations, a `failure-modes.yaml` reference, and a whole `/learn`
analysis reading it. So every analysis below — new FM proposals, strategy tuning, gate analytics,
bottleneck detection — had never run once.

The cause was not disagreement; it was **cost**. The full schema below asks for ~30 fields appended after
every phase, and nothing was gated on it, so it silently never happened. A perfect schema nobody fills is
worth less than a small one that always gets written.

**The required subset is small enough to write in one pass at the end of a run:**

```yaml
ticket_id: <ID>
ticket_type: <type>
schema_version: 1
started_at: <ISO>          # approximate is fine — the date is what matters
ended_at: <ISO>
phases:                     # one line per phase that RAN; timings optional
  - {name: <phase>, outcome: success|blocked|skipped|aborted, iterations: <n>}
failure_modes_hit: []       # [] is a real, useful value — say it, don't omit it
gates_triggered: []
unknown_failures: []        # THE highest-value field: feeds new FM-XX proposals
```

Everything else in this document (per-phase timestamps, `strategy_outcomes`, `quality_signals`, …) is
**optional enrichment**. Add it when the run genuinely produced the signal; never block the file on it.

**Empty lists must be written explicitly.** `failure_modes_hit: []` means "this run hit none" — an omitted
key is indistinguishable from "nobody recorded it", which is exactly the ambiguity that made the whole
dataset useless (`_shared/measurement-integrity-protocol.md`, I1).

**Enforcement:** the `commit` phase has a HARD PRE-CHECK on this file — see `do-ticket/phases/verify.md`
(Phase 16). A declared artifact that no phase is gated on is an artifact that will not exist.

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
  api-test: full-learn-then-use      # strategy id from your live-API test skill

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
  triggers: []
  # Format: { at: 2026-10-12, trigger: qc-found-bug, after_merge: true }
  # trigger: requirements-changed | qc-found-bug (do-ticket-update.md step 2). Older runs hold bare strings.
  # qc-found-bug + after_merge: true = a bug that passed every gate — the number any cost is weighed against.

# PR review rounds
review_rounds:
  count: 0
  must_fix_count: 0
  split_requests: 0

# Session boundaries (SKILL.md § Sessions) — optional, one entry per boundary reached.
# action: ended = the session stopped there; continued = the user chose to go on in the same session.
session_boundaries: []
  # Format: { id: S1, after_phase: plan, context_k: 380, action: ended }
  # id: S1 | S2 | S3 | SZ (SZ = the size check fired). context_k = context size in thousands of
  # tokens, omitted if unknown.

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
| `unknown_failures[]` | implement / api-test / others when an unrecognized error pattern recurs ≥3 times |
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
