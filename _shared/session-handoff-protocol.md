---
name: session-handoff-protocol
description: Standard format for handing context from one skill's session to another (DPS → do-ticket, do-ticket → handle-pr-review, etc.). Defines the handoff envelope so the receiving skill can hydrate context without re-asking the user.
---

# Session Handoff Protocol

## Purpose

When skill A finishes investigating / drafting / categorizing and skill B is the natural next step, hand off the **complete relevant context** in a standard envelope. The receiving skill should never re-ask the user something the previous skill already established.

## When to consume this protocol

- domain-problem-solver concludes investigation → hands off to do-ticket (now bugfix-investigated)
- do-ticket finishes pre-push and CI green → hands off to PR review monitoring
- handle-pr-review categorizes comments → hands off to do-ticket update cycle
- learn-crud discovers a bug surface → hands off to domain-problem-solver

## The envelope

A handoff envelope is a single file. Format: markdown for humans, with a YAML frontmatter for machine fields.

### Location

```
{output}/handoffs/<from-skill>__to__<to-skill>__<topic>__<YYYYMMDD-HHMMSS>.md
```

Example:
```
{output}/handoffs/dps__to__do-ticket__terminate-603-bug__20260502-141500.md
```

### Schema

```markdown
---
schema: handoff/1
from_skill: domain-problem-solver
to_skill: do-ticket
created_at: 2026-05-02T14:15:00
source_session: {output}/domain-problem-solver/open/terminate-603-bug-2026-05-02/
suggested_target: ticket_type=bugfix-investigated
topic: "Terminate API returns 603 for ON_HOLD service tasks"
project: <your-project>
status: ready_for_handoff      # ready_for_handoff | accepted | rejected | superseded
---

## Handoff: Terminate 603 bug → bugfix-investigated ticket

### One-line summary
ServiceTask.Terminate returns HTTP 603 when source state is ON_HOLD. State machine missing the ON_HOLD → TERMINATED transition.

### Confirmed facts (cited)
- Error 603 emitted from `StateMachineGuard.Reject(...)` — confirmed via grep
- State machine table at `src/Domain/StateMachines/ServiceTaskStateMachine.cs:42` lists ACTIVE, BLOCKED, COMPLETED transitions but not ON_HOLD
- Affects ~15% of termination requests in production logs (last 7 days)
- Domain rule cited: ST-LIFECYCLE-3 — ON_HOLD is a valid pre-termination state per domain spec

### Open assumptions (need verification before implementing)
- Assumption: ON_HOLD → TERMINATED should produce same audit trail as ACTIVE → TERMINATED. **Verify with PO before plan phase.**

### Hypotheses considered + outcome
1. State machine missing transition → **CONFIRMED** (top hypothesis, evidence above)
2. Permission check 603 → falsified (controller has [Authorize], JWT role ok in failing requests)
3. Lock contention → falsified (no locks at error time)

### What the next skill should do
- Create `bugfix-investigated` ticket (Jira already exists: PROJECT-12345)
- analyze-requirements: skip full mapping; focus on regression risk surface (other state machine transitions)
- test-cases: regression-focused strategy — must include "ON_HOLD → TERMINATED" + adjacent transitions
- implement: surgical-patch strategy — likely 1 line in state machine table + 1 audit-trail check

### Files referenced
- {output}/domain-problem-solver/open/terminate-603-bug-2026-05-02/investigation.md
- {output}/domain-problem-solver/open/terminate-603-bug-2026-05-02/investigation.log.md
- src/Domain/StateMachines/ServiceTaskStateMachine.cs:42

### Telemetry signals (for /learn)
- DPS hypothesis-protocol succeeded in 2 rounds (3 hypotheses, top one confirmed)
- Domain index citation: ST-LIFECYCLE-3 (Track B Tier 1 quickref hit)
- Cross-project investigation: not needed
```

## Receiving skill behavior

When skill B starts and a handoff envelope is present:

1. **Hydrate context** — load `confirmed_facts`, `open_assumptions`, `files_referenced` into the new session's context.
2. **Show the handoff to user** — *"Continuing from <from-skill>'s work on <topic>. Confirmed facts: [list]. Open assumptions to verify: [list]. Proceed?"*
3. **Apply suggested_target** if present — e.g., do-ticket auto-classifies as `bugfix-investigated` instead of running heuristics.
4. **Mark envelope as `accepted`** — set status field. If user rejects the handoff, set `rejected` with reason.
5. **Never re-ask** anything in `confirmed_facts`. The handoff is a contract.

## Initiating skill behavior

When skill A is finishing and a handoff is appropriate:

1. **Detect natural follow-up** — DPS Phase 6 "requires code change", do-ticket pr-ready completed, learn-crud found integration bug.
2. **Always confirm with user** — *"Hand off to do-ticket as bugfix-investigated? (y/n)"*. Never auto-handoff.
3. **Write the envelope** with all required fields populated.
4. **Surface the path** to the user — *"Handoff written to: <path>. Run `do-ticket` to continue, or open the file to review first."*
5. **Don't delete source session** — handoff doesn't close the originating session. DPS still in `open/` until user explicitly closes.

## Status lifecycle

```
ready_for_handoff  →  accepted     # receiving skill picked it up
                  →  rejected     # user declined or context didn't fit
                  →  superseded   # newer handoff replaces this one (rare)
```

`accepted` and `rejected` can be archived after 30 days. `ready_for_handoff` not picked up in 7 days → ping user.

## Anti-patterns (do NOT do)

- ❌ Auto-handoff without user confirmation. Even when "obvious".
- ❌ Skip the envelope, just verbal handoff in chat. Loses durability.
- ❌ Receiving skill re-asks something already in `confirmed_facts`. The handoff IS the answer.
- ❌ Initiating skill writes incomplete envelope ("see the investigation file"). The envelope must stand alone.
- ❌ Multiple handoffs from the same source for the same target without superseding the previous one.

## Anti-cycle protection

If skill A hands off to skill B, and skill B wants to hand back to skill A within the same logical task → use the original session, don't create a new envelope. Handoffs are forward-only by default.

## Common handoff patterns

| From → To | Trigger | Suggested target |
|-----------|---------|------------------|
| domain-problem-solver → do-ticket | Phase 6: "requires code change" + Jira ticket created | `bugfix-investigated` or `crud-feature` |
| do-ticket → handle-pr-review | PR posted, user pastes review comments | (no target — handle-pr-review owns next steps) |
| handle-pr-review → do-ticket | MUST-FIX comments categorized | `update` cycle |
| learn-crud → domain-problem-solver | API returned unexpected error, root cause unknown | DPS new investigation |
| do-ticket → domain-problem-solver | implement FM-3X-SAME-ROOT pivot | DPS investigation, then back via handoff |
