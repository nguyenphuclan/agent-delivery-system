---
name: domain-mapping-protocol
description: Reusable Track B knowledge lookup ladder for resolving domain entities, invariants, and relationships. Consumed by analyze-requirements, domain-problem-solver, implement-plan. Replaces ad-hoc full-domain_index.yaml reads.
---

# Domain Mapping Protocol

## Purpose

When a task involves entities, statuses, business rules, or "is this allowed" reasoning, look up the relevant facts via a tiered ladder — fastest first. Never invent invariants from training data; never read full `domain_index.yaml` when a quickref hit suffices.

## When to consume this protocol

- Resolving "what entities are in scope for this requirement"
- Answering "is action X allowed when state is Y"
- Mapping a vague user term ("contractor") to canonical entity (`Contractor`, `Subcontractor`, `Worker`)
- Checking lifecycle / state machine before proposing a change
- Detecting cross-entity invariants (FK, unique constraints, ownership)

## The ladder (try in order, stop at first sufficient hit)

### Tier 1 — `_quickref.yaml` (hot path, ~1 file)

```
public-project-docs/<project>/_quickref.yaml         # narrative facts
public-project-docs/<project>/domain/_quickref.yaml  # business invariants with rule_id
```

Search by keyword. Return `a:` field. Hits ~80% of recurring questions in 1 read.

### Tier 2 — Targeted grep (fast, no full file load)

```
rg "<keyword_or_rule_id>" public-project-docs/<project>/domain/ -l
```

When the question is keyword-shaped:
- A specific rule citation (`ST-UNIQ-1`)
- An entity name, enum value, status string
- An error message or DB constraint name

Skips index reads entirely. Cheaper than tier 3.

### Tier 3 — Entity shard

```
public-project-docs/<project>/domain/_index.yaml      # entity → file map
public-project-docs/<project>/domain/<entity>.yaml    # full state machine + rules for one entity
```

Use when reasoning needs the **full lifecycle** or **all rules for one entity**.

### Tier 4 — Cross-entity relationships

```
public-project-docs/<project>/domain/_relationships.yaml
```

For invariants spanning multiple entities (FK chains, task-on-task, parent-child visibility).

### Tier 5 — Source code

Only when the index is silent or you need implementation-level detail. Even then, prefer reading `domain_index.yaml` references, not blind glob.

## Cross-project escalation

When the question crosses projects (e.g., "task in service A triggers callback in service B"):

1. Detect signals: boundary keywords (sync, callback, response from X to Y), service names mentioned, entity not in primary `domain_index`, error on incoming/outgoing API.
2. List subdirectory names under `public-project-docs/<root>/agent-index/` (folder names only — no deep read).
3. Match candidate projects by keyword.
4. **Confirm with user before loading additional indexes:** *"This problem seems to involve `<projectB>`. Should I load its domain index too?"*
5. Load confirmed indexes; track context per project; reason across them.

## When the index is silent

The lookup found nothing. **Do not invent.** Two valid paths:

- **A: Flag the gap** — output an explicit "domain knowledge gap" note: `<entity>.<aspect>: not in index`. Continue with explicit assumption, log it.
- **B: Escalate** — invoke `domain-problem-solver` (if not already running) to investigate the gap. After resolution, **promote** the finding back to the index via `/scan-update` or `/promote-observations`.

## When an action would violate an invariant

1. **Refuse silently → wrong.** Always cite the `rule_id` so user can verify.
2. **Output:** *"This violates `ST-UNIQ-1`: a ServiceTask cannot have two ACTIVE schedules. Alternative: replace existing schedule first."*
3. Propose a compliant alternative if possible; if none exists, escalate.

## Never do these

- ❌ Read full `domain_index.yaml` when quickref would do.
- ❌ Invent an invariant from training memory ("usually unique constraint exists").
- ❌ Override an invariant silently to make the task work.
- ❌ Load 5 entity shards when 1 cross-relationship file would answer.
- ❌ Scan `agent-index/` directory upfront before checking for cross-project signals.

## Override hooks for consuming skills

| Hook | Default | Example |
|------|---------|---------|
| `tier_cap` | 5 | quick-mode: cap at tier 2 |
| `must_cite_rule_id` | true for invariant queries | analyze-requirements: required; question-mode: optional |
| `cross_project_auto_load` | false (always confirm) | none — never auto-load without confirm |
| `unknown_handling` | flag-and-continue | implement: must escalate, cannot assume |

## Caching

Once a tier-N hit is found in a single skill invocation, **cache** the answer in the consuming skill's working context (e.g., `ticket-context.yaml.domain_entities_in_scope`). Subsequent phases re-use the cache instead of re-querying.
