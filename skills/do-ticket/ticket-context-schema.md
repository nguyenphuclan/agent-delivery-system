---
name: ticket-context-schema
description: Schema and protocol for ticket-context.yaml — the resolved-once shared context object passed between do-ticket and its child skills. Read by every child skill at startup; written incrementally as phases produce new resolved knowledge.
---

# ticket-context.yaml — protocol

## Why this exists

Without this file, the same lookup happens 3-5 times per ticket:
- `domain_index.yaml` is read by analyze, plan, write-unit-tests, implement
- `requirements.md` is read by 5 different skills
- `projects.md` paths re-resolved by every skill that writes a file
- pattern matches recomputed on every implement run

`ticket-context.yaml` is the **single resolved snapshot**. Read by all child skills at startup, written incrementally as phases produce knowledge.

## Location

```
{output}/tickets/<TICKET_ID>/ticket-context.yaml
```

Sibling of `ticket-state.yaml`. State = workflow position. Context = resolved facts.

## Lifecycle

Phase numbers below match the canonical enumeration in `do-ticket/SKILL.md`.

| Phase | Writer | Adds |
|-------|--------|------|
| 1 (branch) | do-ticket | `ticket_id`, `resolved.*`, `fingerprints.projects_md` |
| 2 (classify) | do-ticket | `ticket_type`, `risk_profile` |
| 3 (resolve-context) | do-ticket | `fingerprints.*` baseline |
| 5 (requirements) | jira-to-requirements | `fingerprints.requirements_sha`, `jira.fetched_at` |
| 6a (context-expansion) | do-ticket | `context_expansion.*`, `fingerprints.context_expansion_sha` |
| 6b (analyze) | analyze-requirements | `domain_entities_in_scope`, `complexity_flags`, `speed_mode` |
| 7 (invariant-scope) | invariant-check | `invariants_in_scope` |
| 9 (plan) | implement-plan | `pattern_matches`, `resolved.touched_files` |
| 11 (implement) | implement | `strategies_picked.implement` |
| 0 (load-state, --from-dps) | do-ticket | `dps_session_id`, `dps_session_path`, `dps_final_status`, `dps_open_assumptions`, `dps_suggested_strategy` |
| 13 (completeness-audit) | do-ticket | `completeness_gaps` |
| 9 (plan, §A) | implement-plan | `structural_quality_decisions` |
| 9 (plan) | implement-plan | `decisions[]` (work mode per decision — see below) |
| 8.7 (blast-radius) | do-ticket | `blast_radius.*`, `armed_gates[]`, `no_marker` (see `blast-radius.md`) |
| 9.8 (legacy-contract) | do-ticket | `contract_approved_at`, `frozen_baseline` (see `legacy-contract.md`) |
| 10 / 12 (unit-tests / regression) | do-ticket | `red_count`, `green_count`, `tests_run` (see `phase-contracts.yaml`) |
| 12.7 (contract-recheck) | do-ticket | `contract_held`, `counts_moved[]` |
| 13.5 (code-quality-review) | do-ticket | `quality_findings`, `deferred_quality_items` |
| 15 (api-test, ad-hoc) | do-ticket | `adhoc_findings` |
| 22 (pr-review) | do-ticket | `deferred_review_items` |
| Each phase | do-ticket | `phases_run`, `last_updated` |

**Append-only contract:** child skills MUST NOT delete or mutate fields they did not write. Only append new keys or update keys they own.

**Resume safety:** on resume, re-read context first. Never trust state without context.

## Schema

```yaml
ticket_id: PROJECT-1234
schema_version: 1

# Set by phase 2 (classify)
ticket_type: crud-feature           # see do-ticket/ticket-types.md
risk_profile: medium                # low | medium | high | critical
risk_factors: []                    # ["touches-auth", "db-migration", "prod-data"]

# Set by phase 1 (branch + project resolve)
resolved:
  output_root: <project.paths.output_root>
  repos:
    api_task: <project.paths.repos_root>/<project.repos.api_task>
    api_portal: <project.paths.repos_root>/<project.repos.api_portal>
    frontend: <project.paths.repos_root>/<project.repos.frontend>
  base_branch: <project.base_branch>
  branch_name: PROJECT-1234
  test_project_paths: []            # filled by plan
  touched_files: []                 # filled by plan, refined by implement

# Set by phase 6a (context-expansion, do-ticket internal)
# Records what was found by filtering incidents.yaml + topology.yaml against ticket scope.
# Skipped (all null) if both artifacts missing OR ticket_type ∈ {doc-only, hotfix} OR --from-dps mode.
context_expansion:
  incidents_available: null         # bool — true if incidents.yaml exists + fresh
  topology_available: null          # bool — true if topology.yaml exists + fresh
  incidents_matched: []             # list of incident IDs that scored above threshold
  topology_queues_matched: []       # list of queue names matched on ticket scope
  high_risk_overlap: []             # incident IDs with recurrence_risk=high AND keyword/component overlap
  file: null                        # "context-expansion.md" if produced, else null
  skipped_reason: null              # "both_artifacts_missing" | "doc_only_ticket" | "hotfix_ticket" | "dps_handoff" | null

# Set by analyze-requirements
domain_entities_in_scope: []        # ["ServiceTask", "Contractor"]
complexity_flags: []                # ["multi-entity", "cross-service", "state-machine"]

# Set by invariant-check (pre-mode)
invariants_in_scope: []             # ["ST-UNIQ-1", "ST-LIFECYCLE-2"]

# Set by implement-plan
pattern_matches: []
# Format:
#   - file: Application/Commands/CreateTaskHandler.cs
#     pattern_id: PAT-CMD-1
#     priority: mandatory

# Set by phase 6 (analyze) — true if clarity < 60 and user accepted speed-mode
speed_mode: false

# Set by Phase 0 when --from-dps flag passed (null if not a DPS handoff)
dps_session_id: null                  # e.g. "terminate-603-bug-2026-05-02"
dps_session_path: null                # full path to session folder
dps_final_status: null                # RESOLVED | PARTIAL | BLOCKED
dps_open_assumptions: []              # strings from investigation-findings "Open assumptions"
dps_suggested_strategy: null          # e.g. "surgical-patch" — pre-sets strategies_picked.implement

# Set by do-ticket per phase (strategy selection)
strategies_picked:
  analyze: null                     # see <skill>/strategies.yaml for valid IDs
  test-cases: null
  plan: null
  implement: null
  api-test: null                    # strategy id from your live-API test skill, if it has strategies

# Set by phase 13 (completeness-audit) — one entry per gap found
# status: open | resolved | deferred | rejected
completeness_gaps: []
# Format:
#   - id: gap-1
#     description: "Missing input validation on CreateTaskCommand.ClusterId"
#     status: open

# Set by phase 22 (pr-review) — NICE-TO-HAVE comments deferred to follow-up
deferred_review_items: []
# Format:
#   - comment_id: "abc123"
#     description: "Reviewer: extract this into a helper method"
#     status: deferred       # deferred | dismissed

# Set by phase 9 (plan, §A structural gate) — the 4 plan-time quality verdicts
structural_quality_decisions: []
# Format:
#   - question: layer-placement | new-vs-extend | improve-vs-mirror | duplication-of-existing
#     verdict: "new code uses AnyAsync(predicate) instead of mirroring ToList+foreach in TaskService"
#     confidence: high       # low confidence surfaces in Phase 9 CRITICAL review

# Set by phase 9 (plan) — every non-trivial decision carries its WORK MODE.
# The mode is a ROUTER, not a label: it decides what the agent owed on that decision.
#   M1          — settleable from the code or data: one command answers it. Settle it, never ask.
#   M2-open     — a real choice between shapes: owes an `## Options considered` table (≥2 options).
#   M2-absolute — fixed by an outside constraint (contract, regulation, a lead's order): owes its
#                 source and the condition under which it stops holding.
#   M3          — no one knows the answer up front: co-solved with the user in rounds, where each
#                 round must bring a NEW code fact.
decisions: []
# Format:
#   - id: 1
#     text: "pin the flow version in OrderCreator.Create"
#     mode: M3             # M1 | M2-open | M2-absolute | M3
#     settled_by: "grep '\\.Add(order' -> 1 site"   # M1 ONLY — the command that settled it
#     options_count: 3     # M2-open / M3 ONLY — candidates in `## Options considered`
#     rounds: 2            # M3 ONLY — rounds that carried a NEW code fact. Rhetoric does not count
#     source: "customer contract"      # M2-absolute ONLY
#     revisit_when: "the history table moves to the new audit store"   # M2-absolute ONLY — outside orders expire
#
# GATE — checked at Phase 9.8 (G-T0) and at Phase 9 exit. Each is a DEFECT, not a warning:
#   M1 with an open question               -> it was settleable; settle it, do not ask
#   M2-open / M3 with options_count < 2    -> a bare choice handed to the user
#   M2-absolute missing source             -> an outside constraint becomes permanent by accident
#   M3 with rounds == 0                    -> co-solve claimed, never run. This is the PROJ-11350
#                                             failure: the plan's own section said ORM change
#                                             tracking could not do this, then it was built on ORM
#                                             change tracking with 0 rounds recorded.
#
# ANTI-GAMING: never lower a defect count by DOWNGRADING a mode. Relabelling an M3 as M2-open to dodge
# the rounds check is the severest defect here — worse than the missing round. A metric reduced by
# suppressing what it measures is a broken metric.

# Set by phase 13.5 (code-quality-review) — diff-scoped findings
# status: open | resolved | deferred | rejected ; severity: must-fix | nice-to-have | out-of-scope
quality_findings: []
# Format:
#   - id: q-1
#     dimension: 6            # data-access & control-flow
#     location: "TaskService.cs:142"
#     problem: "ToListAsync then foreach to check existence"
#     fix: "AnyAsync(t => t.ClusterId == id)"
#     severity: must-fix
#     status: open

# nice-to-have findings the user chose to defer (surfaced in Phase 23 + PR description)
deferred_quality_items: []

# Hashes for staleness detection
fingerprints:
  projects_md_sha: null
  domain_index_sha: null
  requirements_sha: null
  plan_sha: null
  context_expansion_sha: null       # of context-expansion.md, used to detect stale 6a output on resume

# Jira metadata (set by jira-to-requirements)
jira:
  fetched_at: null
  comment_count: null
  reporter: null
  components: []
  labels: []
  issue_type: null

# Phase audit trail (set by do-ticket after each phase)
phases_run:
  # - phase: branch
  #   completed_at: 2026-04-12T10:00:00
  #   strategy: null
  #   duration_seconds: 12

last_updated: 2026-04-12T10:00:00
```

## How child skills consume context

Every child skill SKILL.md must include this section near the top:

```markdown
## Context

Before any other action, read `{output}/tickets/<TICKET_ID>/ticket-context.yaml`.
Use the resolved fields (paths, entities, patterns, fingerprints) instead of re-resolving.
If the file does not exist → invoke do-ticket phase 1 (`branch`) first, or block with G10.

When this skill produces a new resolved fact (entities, patterns, etc), append to
ticket-context.yaml. Do not mutate fields owned by other phases.
```

## Staleness detection

Before consuming a fingerprinted file, child skills compute its current SHA and compare to `fingerprints.<file>_sha`. If differ → file changed externally → either:
- re-process (analyze, plan), OR
- warn user and offer regen (qa-checklist, pr-description)

## Read-only mode

`do-ticket <TICKET_ID> show-context` prints the current context file rendered as a table. Useful for debugging "why did the agent pick strategy X".

## Migration

Existing tickets without ticket-context.yaml: do-ticket phase 0 (`load-state`) detects absence → reconstructs minimal context from ticket-state.yaml + projects.md + requirements.md (if exists) → saves. No re-do needed for completed tickets.
