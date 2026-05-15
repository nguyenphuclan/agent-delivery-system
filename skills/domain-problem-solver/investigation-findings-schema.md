---
name: investigation-findings-schema
description: Schema for investigation-findings.md — the consumable output of a DPS session that downstream skills (do-ticket as bugfix-investigated, jira-to-requirements as seed) can hydrate from. Defines the contract between DPS and the rest of the ecosystem.
---

# investigation-findings.md — schema

## Why this exists

When a DPS session concludes "this needs code changes", the user shouldn't have to retell the story to do-ticket. `investigation-findings.md` is the **consumable summary** that bridges DPS (analysis) and do-ticket (action), parallel to how `requirements.md` bridges Jira and analyze-requirements.

Two consumers:
1. **`do-ticket` with type=bugfix-investigated**: hydrates `requirements.md` seed + skips analyze when findings are conclusive.
2. **`jira-to-requirements`**: when user wants a Jira ticket created from findings — uses this as the description body.

## Location

Lives inside the DPS session folder:

```
{output}/domain-problem-solver/open/<topic>-<YYYY-MM-DD>/investigation-findings.md
```

When DPS session closes, the file moves to `closed/` with the rest. do-ticket / jira-to-requirements that consumed it have already copied relevant fields into their own state, so the original can archive freely.

## Structure

```markdown
---
schema: investigation-findings/1
session_id: terminate-603-bug-2026-05-02
problem_type: bug
final_status: RESOLVED       # RESOLVED (root cause confirmed) | PARTIAL (likely cause) | BLOCKED (escalation needed)
project: <your-project>
created_at: 2026-05-02T11:30:00
strategy_used: bug-trace
---

## Title
ServiceTask.Terminate returns 603 for ON_HOLD source state

## One-line summary
State machine table is missing the ON_HOLD → TERMINATED transition; service rejects with 603.

## Confirmed (cited evidence)
- 603 is emitted from `StateMachineGuard.Reject(...)` at src/Domain/StateMachines/StateMachineGuard.cs (file reference, not investigated by DPS)
- Domain rule ST-LIFECYCLE-3: "ON_HOLD is a valid pre-termination state" — domain index `_quickref.yaml`
- Production logs (last 7 days): ~15% of TERMINATE calls fail with 603, all having source state ON_HOLD
- Affected role: any user with terminate permission, regardless of role

## Top hypothesis (with falsification trail)
**[CONFIRMED] State machine table missing ON_HOLD → TERMINATED transition**
- Falsification test: `rg "ON_HOLD" src/Domain/StateMachines/ServiceTaskStateMachine.cs` → no match
- Confirmation: code-side scan recommended at implement phase to verify state map

## Hypotheses considered and refuted
- ❌ Permission check denies: controller has `[Authorize]`, JWT role parsed correctly in failing requests
- ❌ Lock contention by scheduler: no locks present at error time per audit table

## Domain knowledge applied
- Cited rules: ST-LIFECYCLE-3
- Entities involved: ServiceTask (primary)
- Cross-project: not needed (single-service issue)

## Open assumptions (verify before / during implement)
- Audit trail: ON_HOLD → TERMINATED should produce same audit record format as ACTIVE → TERMINATED. **PO confirmation needed.**
- No legacy data with phantom ON_HOLD values — DB query recommended at implement phase.

## Recommended path forward
- **Suggested ticket type:** bugfix-investigated
- **Suggested implement strategy:** surgical-patch (1 file, ≤20 LOC change anticipated)
- **Test focus:** regression-focused — must include ON_HOLD → TERMINATED + adjacent state transitions
- **Risk level:** medium (state machine change, narrow blast radius)

## Out of scope (intentionally excluded)
- Refactoring the state machine into a config-driven structure (separate ticket if desired)
- Audit log format harmonization (raised as ST-AUDIT-1 follow-up)

## Files referenced
- src/Domain/StateMachines/ServiceTaskStateMachine.cs (line 42 — state map)
- src/Domain/StateMachines/StateMachineGuard.cs (error 603 emission point)
- public-project-docs/<project>/domain/_quickref.yaml (ST-LIFECYCLE-3)

## Investigation duration
- Rounds of clarification: 5
- Hypotheses generated: 4 (3 surfaced)
- Total time: ~1.5 hours

## Handoff status
**Ready for handoff:** yes
**Suggested target:** do-ticket --type=bugfix-investigated
**Handoff envelope:** dps__to__do-ticket__terminate-603-bug__20260502-113000.md (per session-handoff-protocol)
```

## How do-ticket consumes this

When do-ticket starts with a handoff envelope pointing to this file:

1. **Set ticket_type = bugfix-investigated** (skip auto-classification).
2. **Hydrate ticket-context.yaml** from findings:
   - `domain_entities_in_scope`: from "Entities involved"
   - `risk_factors`: derived from "Risk level"
   - `complexity_flags`: cross-service if mentioned
3. **Seed requirements.md** from findings (skip jira-to-requirements):
   ```markdown
   # Requirements: <title from findings>
   
   ## Source
   Investigation findings from DPS session <session_id> — <created_at>
   
   ## Bug repro
   <One-line summary> + <Confirmed evidence>
   
   ## Acceptance criteria
   - [Derived from findings + open assumptions to verify]
   
   ## Out of scope
   <copy from findings>
   ```
4. **Pre-fill plan.md hint** with "Suggested implement strategy" — pre-set `strategies_picked.implement = surgical-patch`.
5. **Skip analyze phase** — but flag "Open assumptions" as G1 to confirm with user during plan phase.

## ticket-draft.md — schema

Generated alongside `investigation-findings.md` when Phase 6 verdict = "code change needed". User-facing — ready to paste into Jira without further processing.

```markdown
---
schema: ticket-draft/1
session_id: <session_id>
---

## Summary
<concise title, under 70 chars>

## Type
Bug | Task | Improvement

## Description

### Problem
<one-line summary of what's wrong>

### Evidence
- <confirmed fact 1>
- <confirmed fact 2 — max 4 bullets>

### Root Cause
<what's wrong and why — only if confirmed; otherwise omit>

## Acceptance Criteria
- [ ] <concrete, testable condition>
- [ ] <second condition>
- [ ] Regression: adjacent flows not broken

## Open Questions (for PO/BA)
- <assumption that needs confirmation before or during implement>

## Out of Scope
- <explicitly excluded>

## Investigation Reference
DPS session: `<session_id>` — see `investigation-findings.md` in same folder
```

## How jira-to-requirements consumes this

Prefer `ticket-draft.md` over raw findings — it's already formatted for Jira:

1. Use "Summary" as ticket title.
2. Use "Description" block as ticket body.
3. Use "Open Questions" as ticket comments.
4. Tag ticket type per "Type" field.

## Anti-patterns (do NOT do)

- ❌ Generate this file when DPS session is BLOCKED — the recommendation isn't actionable. Better: leave PARTIAL findings in investigation.md, no findings file.
- ❌ Speculate beyond confirmed evidence. Hypotheses must be cited as such, with their falsification status.
- ❌ Skip "Open assumptions" — the receiving skill needs to know what's still uncertain.
- ❌ Reference paths the receiving skill can't access (always full or project-relative paths).
- ❌ Auto-create handoff envelope. User must confirm per session-handoff-protocol.

---

## Flow-trace extension (added when strategy_used = flow-trace)

When DPS runs the `flow-trace` strategy (typically invoked via `--from-briefing` from do-ticket Phase 6c), the standard sections above are produced PLUS these additional sections. Frontmatter must include:

```yaml
strategy_used: flow-trace
dps_invoked_by_ticket: <TICKET_ID>      # source ticket from briefing
briefing_path: <relative path>
flows_in_scope: [<flow ids from briefing>]
```

### Required additional sections

```markdown
## Flow Map — <flow_name>

Produced per target flow. One block per flow. Trace is BY TRIGGER PATH, not by field.

**Flow definition** (from {project_docs}/flows/flow_index.yaml):
- Description: <copied from flow_index.flows.<name>.description>
- Expected effect: <copied from flow_index.flows.<name>.effects>
- Invariant owner: <copied from flow_index.flows.<name>.code_anchors.invariant_owner>

### Trigger path: <trigger.id> — <trigger.description>

**Channel**: api | gui | rabbitmq | scheduled
**Entry handler**: <ClassName>.<Method> at <repo>/<file>:<line>
**Cascade** (1-3 levels, observed call chain):
- Step 1: <call — one-line description>
- Step 2: <call>
- Step 3: <call>

**Reaches expected effect?** YES / PARTIAL / NO

If NO/PARTIAL — where the signal drops:
- Location: <repo>/<file>:<line>
- Mechanism: silent-overwrite / conditional-guard / early-return / wrong-branch / missing-wire
- Evidence: <one-line cite>

### Trigger path: <next trigger>
... (one block per trigger path of this flow)

## Gap Analysis

One row per trigger path that does NOT reach the flow's expected effect.

| Gap ID | Flow | Trigger | Drop location | Drop mechanism | Severity |
|--------|------|---------|---------------|----------------|----------|
| G-1 | rerouting | 3rd-party API update | api-task/ThirdPartyApiRouter.cs:354 | silent-overwrite (PROJ-10867 lock-in) | critical |
| G-2 | rerouting | 3rd-party API update | api-task/AssigneeSetter.cs:107 | conditional-guard (isExistOutTask) | high |

## Decisions

### G-1 — <gap description>
**Options considered:**
- Option A: <approach>
  - Pros: <bullets>
  - Cons: <bullets>
- Option B: <approach>
  - Pros: ...
  - Cons: ...
- Option C: <approach>
  - Pros: ...
  - Cons: ...

**Recommended: <A | B | C>**
Reasoning: <one paragraph — must cite the flow invariant being preserved>
Confidence: high | medium | low
Open assumption (if confidence != high): <what to verify in implement>

### G-2 — <next gap>
... (one block per gap)

## Decision summary (for do-ticket plan phase)

- suggested_implement_strategy: <e.g. surgical-patch with flow-gate carve-out>
- touched_files (predicted): [<repo>/<file>, ...]
- touched_repos: [<list — only repos with code changes>]
- not_touched_repos: [<list of repos previously thought in scope but ruled out>]
- new_dependencies: <e.g. RerouteService injected into ...>
- transactional_boundary: <choice with reason>
- backwards_compat_notes: <e.g. existing AO flows that publish DwRoutingModel still need to fire?>
- test_seeds: <suggested unit/integration test cases>
```

### How do-ticket consumes the flow-trace extension

In addition to the standard hydration (above), when `strategy_used == flow-trace`:

1. Set `ticket_type = bugfix-investigated` (same as standard).
2. Hydrate `ticket-context.yaml`:
   - `flow_findings.flows_in_scope[]` ← from frontmatter
   - `flow_findings.gaps[]` ← from "Gap Analysis" table
   - `flow_findings.decisions[]` ← from "Decisions" section
   - `resolved.touched_files` ← from "Decision summary.touched_files"
   - `resolved.touched_repos` ← from "Decision summary.touched_repos"
   - `resolved.not_touched_repos` ← from "Decision summary.not_touched_repos"
   - `strategies_picked.implement` ← from "suggested_implement_strategy"
3. Seed `plan.md` skeleton with one section per gap, each populated with the recommended option's reasoning.
4. Surface `Open assumption` lines from each decision as G1 confirmation items at plan phase entry. User acknowledges before plan finalizes.
