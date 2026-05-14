---
name: hypothesis-protocol
description: Reusable ranked-hypothesis generation. Consumed by domain-problem-solver (Phase 5b root cause), implement (FM-3X-SAME-ROOT pivot), analyze-requirements (when requirements are ambiguous). Each hypothesis carries confidence, falsifiability, and a cheap test.
---

# Hypothesis Protocol

## Purpose

When the system is in an unknown state (bug with no obvious cause, ambiguous requirement, repeated test failure), generate **ranked hypotheses** rather than guessing. Each hypothesis must be falsifiable and paired with a low-cost test.

## When to consume this protocol

- Bug with no clear repro path → enumerate root cause candidates
- Implementation failed 3 times with same error → enumerate alternative root causes
- Requirement is ambiguous → enumerate possible interpretations before asking user
- Performance / behavior issue with multiple plausible mechanisms

## Algorithm

```
1. Enumerate (broad first):
   - List 5-10 plausible explanations.
   - Include obvious AND non-obvious. Weighting comes later.
   - Use domain knowledge (via domain-mapping-protocol) to constrain.

2. Score each hypothesis on 3 axes:
   - Plausibility: how well does it explain the observed evidence?  (1-3)
   - Prior probability: how often does this kind of cause occur in this codebase? (1-3)
   - Test cost: how cheap is it to falsify? (1=very cheap, 3=expensive)

3. Rank:
   - Sort by (plausibility + prior - test_cost). Cheap-to-test wins ties.
   - Top 3 surface as primary hypotheses.
   - Rest stay as backlog (revisit if top 3 falsified).

4. For each top hypothesis, define:
   - Falsification test: a specific check that would PROVE it wrong
   - Confirmation evidence: what would PROVE it right (stronger than just "consistent with")
   - Cheapest first action: 1 query, 1 grep, 1 log, 1 reproduction step
```

## Hypothesis card (output format)

```yaml
hypothesis: "ServiceTask state machine rejects TERMINATE from ON_HOLD"
plausibility: 3       # explains the 603 error perfectly
prior: 2              # state machine bugs occur sometimes in this repo
test_cost: 1          # cheap: grep state-transition table
score: 4              # 3+2-1
falsification:
  - "If the state machine table includes ON_HOLD → TERMINATED transition, this is wrong"
  - "Cheapest test: rg 'ON_HOLD.*TERMINATED' src/Domain/StateMachines/"
confirmation:
  - "Find error code 603 emitted from StateMachineGuard with rejected source state ON_HOLD"
  - "Reproduce: PUT /service-tasks/<id>/terminate where state is ON_HOLD"
first_action: "rg 'ON_HOLD' src/Domain/StateMachines/ServiceTaskStateMachine.cs"
```

## Confidence calibration

Avoid stating high confidence without evidence. Use this scale:

| Word | Meaning |
|------|---------|
| **Confirmed** | Direct evidence, cited rule_id or code line |
| **Likely** | Multiple consistent signals, no contradicting evidence |
| **Plausible** | Fits observed behavior, but other hypotheses do too |
| **Speculative** | No evidence yet, just structurally possible |

Never use "definitely / certainly / obviously" without confirmed evidence.

## Anti-patterns (do NOT do)

- ❌ Pick the first hypothesis that comes to mind and run with it.
- ❌ Generate hypotheses without ranking — looks comprehensive but action-blind.
- ❌ Skip the falsification step — "we'll know when we try the fix" is a smell.
- ❌ Pick the most expensive-to-test hypothesis first because it sounds smartest.
- ❌ Conflate "consistent with evidence" with "confirmed" — most hypotheses are consistent until refuted.

## Override hooks for consuming skills

| Hook | Default | Example |
|------|---------|---------|
| `min_hypotheses` | 3 | DPS bug: 3-5; quick-mode: 1-2 |
| `max_hypotheses` | 7 | implement-FM-3X: 4 |
| `falsification_required` | true | always — non-falsifiable hypothesis = guess |
| `domain_grounding` | required | citing rule_id when applicable |
| `surface_to_user` | top 3 | DPS Phase 5b: top 3; implement: top 2 |

## Loop protocol (when first round of hypotheses all falsified)

If top 3 are falsified by their tests:
1. Promote backlog #4-#5 to top.
2. If backlog empty → invoke domain-mapping-protocol Tier 4 (cross-entity invariants) — may surface new candidates.
3. Still empty → escalate (DPS Phase 5d, implement G8, etc).
4. Log the falsification chain — useful for /learn telemetry.

## Output to user

When surfacing hypotheses:

```markdown
### Hypotheses (ranked)

1. **[Most likely]** ServiceTask state machine rejects TERMINATE from ON_HOLD
   - Why: error code 603 + state machine pattern in this repo
   - Falsify: `rg 'ON_HOLD.*TERMINATED' src/Domain/StateMachines/`
   - Confidence: Likely

2. **[Second]** Permission check denies TERMINATE for non-admin role
   - Why: 603 sometimes used for authz failures here
   - Falsify: check controller [Authorize] attribute + JWT role of failing request
   - Confidence: Plausible

3. **[Third]** Background scheduler holds the task in ON_HOLD via lock
   - Why: explains intermittent behavior reports
   - Falsify: query DB for active locks on the task at error time
   - Confidence: Speculative
```

This format is read by humans and machines. The ranking + cheap test makes the next investigation step obvious.
