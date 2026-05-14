---
name: clarification-protocol
description: Reusable iterative clarification loop. Consumed by analyze-requirements, domain-problem-solver, and implement-when-stuck. Defines question-batching, exit conditions, contradiction handling, and assumption logging.
---

# Clarification Protocol

## Purpose

When user input is incomplete, ambiguous, or contradicts itself, ask targeted questions until you can produce confident output. This protocol replaces ad-hoc Q&A with a disciplined loop.

## Algorithm

```
state = { context: input, rounds: 0, assumptions: [], contradictions: [] }

while not exit_condition_met(state):
    state.rounds += 1
    missing = assess_missing_dimensions(state.context)
    if missing is empty:
        break  # safety
    questions = pick_top_3(missing)
    answer = ask_user(questions)        # max 3 questions per round
    if contradicts_existing(answer, state.context):
        flag_contradiction(answer)
        clarify_resolution()
    merge_into_context(answer, state.context)

return state
```

## Dimensions to assess (default checklist)

| Dimension | What you're looking for |
|-----------|------------------------|
| **Scope** | Which part of the system / module / feature is in question? |
| **Trigger** | What action or event surfaces the issue / drives the requirement? |
| **Expected vs Actual** | Specifically what should happen and what is happening? |
| **Environment** | Local / DEV / staging / production? Which version? |
| **Affected parties** | Which user role, customer type, or service is impacted? |
| **Frequency** | One-off / intermittent / always reproducible? |
| **Recent changes** | What changed recently that might have introduced this? |

Skills can extend or override this list (e.g., for refactor analysis, replace "Trigger" with "Behaviors to preserve").

## Question rules

- **Max 3 per round.** Batch related questions, don't drip them.
- **High-level first.** "Which part of the task flow is affected?" not "Which Java class handles this?"
- **Closed-ended when possible.** "Is the bug in creation, update, or termination?" beats "Tell me about the bug."
- **Never ask for code-level details** — that's `implement-plan` / source code's job.
- **Ground in the domain.** Reference entities, statuses, flows by name from `domain_index.yaml` when known.

## Exit conditions (any one suffices)

1. Enough context for **one confident answer** (analysis, plan, hypothesis).
2. Enough context for **2-3 plausible hypotheses** the next phase can disambiguate.
3. User explicitly says **"just proceed"** or **"stop asking"** → proceed with all assumptions logged.
4. User says **"I don't know"** twice in a row → log as open question, proceed with what's known.
5. Remaining unknowns require **system access / source code / specialist** → escalate per host skill's escalation block.
6. **Round cap reached** (default 7; skill can override). Log remaining gaps as assumptions.

## Contradiction handler

If a later answer contradicts an earlier answer:

1. **Pause** — do not silently overwrite.
2. **Surface** — *"This conflicts with what you said earlier about `<X>`: `<earlier value>` vs `<new value>`. Which is correct?"*
3. **Resolve** — wait for user choice.
4. **Log** — record the resolution in the session/conversation log so future readers see the correction.

## Assumption logging

Anything the loop concluded without explicit user confirmation is an **assumption**, not a fact. Tag every assumption:

```
**Assumption (not user-confirmed):** Termination only applies to status=ACTIVE tasks.
*Source: domain_index.yaml entity:ServiceTask*
```

Output stage MUST list assumptions visibly so user can correct them.

## Override hooks for consuming skills

When invoking this protocol, a skill can set:

| Hook | Default | Example |
|------|---------|---------|
| `max_rounds` | 7 | analyze-requirements: 5; quick-mode: 1 |
| `dimensions` | full checklist | refactor: replace Trigger with Behaviors-to-preserve |
| `exit_when` | any of above | implement-FM-3X: exit on hypothesis count ≥ 3 |
| `min_rounds` | 0 | none currently |
| `escalate_to` | host skill's gate | DPS: Phase 5d Escalation block; analyze-req: G1 |

## Failure-mode references

If the loop is going nowhere after `max_rounds`, or contradictions can't be resolved, fall through to host skill's failure handling. Common patterns:
- DPS-FM-CLARIFY-LOOP-STUCK
- analyze-requirements: G1 open-questions block

## Anti-patterns (do NOT do)

- ❌ Asking 1 question, then immediately producing output. (Either ask all needed, or ask 3 batched.)
- ❌ Producing output with silent assumptions buried in the analysis.
- ❌ Looping forever — round cap is mandatory.
- ❌ Asking the same question twice with different wording.
- ❌ Demanding precise technical details when domain-level info would do.
