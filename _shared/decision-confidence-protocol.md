---
name: decision-confidence-protocol
description: Every non-trivial decision an agent makes (mapping, abstraction, naming, algorithm choice, scope boundary) carries a confidence tag. User reviews focus on low-confidence decisions only — high-confidence ones go through silently. Replaces flat output where everything looks equally important.
---

# Decision Confidence Protocol

## Purpose

When AI writes plans or code, it makes dozens of micro-decisions. Most are obvious. A few are genuinely uncertain. Currently, output is flat — user can't tell which 3 decisions out of 50 deserve attention.

This protocol forces every decision to carry a **confidence tag**. Output surfaces only low/medium-confidence decisions for review. High-confidence ones run through silently.

Result: review time goes from "skim 50 items" to "adjudicate 3 uncertain things".

## What counts as a "decision"

Trigger this protocol when AI does any of:
- **Mapping** — fieldA in source ↔ fieldB in target (DTO mapping, schema → entity, request → command)
- **Naming** — choosing a class/method/variable name when project conventions are unclear
- **Abstraction** — introducing a new interface, base class, abstract type
- **Algorithm choice** — picking between two valid implementations (recursive vs iterative, in-memory vs streaming)
- **Scope boundary** — deciding what's IN vs OUT of this ticket
- **Pattern application** — applying a code pattern (CQRS, repository, etc.)
- **Dependency choice** — using lib A vs B, or hand-rolled
- **Error handling strategy** — throw, return Result<T>, log-and-continue
- **State machine transition** — adding/removing/modifying allowed states

Trivial decisions that don't trigger this protocol:
- Following an existing project pattern documented in patterns/_index.yaml at `enforce` level
- Using idiomatic syntax (no real choice involved)
- Renaming to match existing naming convention obviously present

## Confidence levels

| Level | Range | Meaning | Surface to user |
|-------|-------|---------|-----------------|
| **`high`** | >85% | Multiple consistent signals, clear evidence, no contradiction | Silent — log only |
| **`medium`** | 60-85% | Reasonable inference, some ambiguity, plausible alternative exists | Surface as IMPORTANT in review-priorities |
| **`low`** | <60% | Genuine guess; user knowledge needed | Surface as CRITICAL in review-priorities; consider G1 block |

## Decision card format

Every non-trivial decision produces a decision card written to the skill's output (plan.md, implement-summary.md, etc.):

```yaml
- decision: "Map ContractorDto.networkOwnerId → User.organizationId"
  confidence: low
  evidence_for:
    - "Both fields are GUID type"
    - "Both reference owning org per code comments"
    - "Naming pattern in 1 of 5 sample files"
  evidence_against:
    - "User schema has separate `networkOwnerId` field that's NULL in this branch"
    - "OrganizationId is set by org service, not user-driven"
  alternative: "Map to User.networkOwnerId if exists; or split — networkOwner ≠ organization in source"
  decision_made_because: "Branch context suggests legacy migration where networkOwner was repurposed as org link"
  user_action_needed: "Confirm semantic equivalence; if wrong, will cause data integrity issue"
```

Minimum required fields: `decision`, `confidence`, `evidence_for`, `evidence_against` (or note "none found"), `alternative`. The `user_action_needed` is required for low/medium.

## Calibration heuristics

To assign confidence honestly (not optimistically):

**Score `high` (>85%) when:**
- 3+ identical examples in surrounding code
- Explicit project pattern at `enforce`/`mandatory` priority
- Single non-ambiguous interpretation in domain index
- Test exists that locks behavior

**Score `medium` (60-85%) when:**
- 1-2 examples in code (small sample)
- Pattern at `standard` priority (advisory)
- Multiple plausible interpretations but one is clearly dominant
- Refactoring without test coverage on changed lines

**Score `low` (<60%) when:**
- Zero examples in code
- Pattern conflict (file A says X, file B says Y, no rule says which wins)
- Names diverge between source and target (e.g., `networkOwner` ↔ `org`)
- Type coercion (GUID → string, decimal → int, nullable → non-null)
- Cross-service contract change with no spec
- User intent inferred from indirect signals only

**Anti-pattern: NEVER score `high` because the AI feels confident.** Confidence is grounded in evidence in code or domain knowledge, not in the model's certainty.

## How consuming skills use this protocol

### `implement-plan` integration
While writing plan.md, log every decision card. At end of plan:
- Count: `high: 12`, `medium: 3`, `low: 2`
- Top of plan.md: "Confidence summary" + lists of medium/low decisions

### `implement` integration
While writing code, log every implementation-time decision. After implement:
- Update implement-summary.md with full decision card list
- Generate `review-priorities.md` (per `risk-prioritization-protocol.md`) which surfaces medium/low decisions for review

### `analyze-requirements` integration
Same — every interpretation of an ambiguous requirement gets a confidence score. Low-confidence interpretations become G1 open-questions.

### `domain-problem-solver` integration
Already uses `hypothesis-protocol.md` which has its own confidence wording (Confirmed / Likely / Plausible / Speculative). Map hypothesis confidence words to this scale:
- Confirmed → high
- Likely → high (but ground in evidence)
- Plausible → medium
- Speculative → low

## Override hooks for skills

| Hook | Default | Purpose |
|------|---------|---------|
| `auto_proceed_threshold` | 0.85 average + no `low` | Skip user review gate when above threshold |
| `block_on_count_low` | 1 | If ≥ N low-confidence decisions → G1 block |
| `block_on_critical_mapping` | true | Always block if mapping-integrity-protocol flags CRITICAL |
| `surface_max_items` | 5 | Cap review-priorities CRITICAL section at N items |

## Anti-patterns (do NOT do)

- ❌ Tag everything as `high` to avoid friction. Calibrate honestly.
- ❌ Skip the `evidence_against` field. Even high-confidence decisions usually have one weak counter-signal worth noting.
- ❌ Use words like "definitely", "obviously", "clearly" without evidence. Replace with cited evidence.
- ❌ Bury low-confidence decisions in the middle of a long doc. They go in CRITICAL section of review-priorities.
- ❌ Ask user to confirm `high` decisions. That trains them to skim and miss the real ones.

## Telemetry hook

Each skill's telemetry file records:
```yaml
decisions:
  total: 17
  high: 12
  medium: 3
  low: 2
  critical_mappings: 1
  user_overrode: 0           # how often user disagreed with AI's decision
  user_changed_confidence: 1  # how often user moved the dial
```

`/learn` reviews telemetry across runs:
- If user frequently overrides `high` → AI is over-calibrated → propose calibration adjustment
- If user never touches `medium` → maybe everything `medium` should be `high` (under-calibrated)
- If `low` decisions cluster around same pattern → propose adding it to patterns/_index.yaml so it becomes `high`

## Vietnamese summary (for user UX)

Khi user xem output, sẽ thấy:
- **Confidence summary** ở đầu plan/summary
- **Review-priorities.md** với CRITICAL/IMPORTANT sections
- **Decision cards** chi tiết cho mỗi quyết định không hiển nhiên
- AI chỉ block bạn khi có decision đáng phân vân — không phải mọi lần
