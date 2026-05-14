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
  learn-crud: null

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
