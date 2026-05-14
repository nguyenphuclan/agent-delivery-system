---
name: do-ticket-patterns
description: Code pattern registry protocol for do-ticket. Defines how implement-plan and implement resolve the "which pattern is correct" question. Project-specific registry overrides model defaults and observed-in-code patterns when priority says so. Child skill — not user-facing.
---

# Code Pattern Registry

## Why this exists

During implementation a model encounters N valid approaches to the same problem. Training data contains all of them. The correct approach for THIS project is the one recorded in this registry — not the model's general default. The registry wins over training default. Existing code in the repo wins over training default. But a documented pattern at `mandatory` or `enforce` wins over existing code.

## Priority ladder (highest → lowest)

| Priority | Meaning | Implement behavior |
|----------|---------|-------------------|
| `enforce` | Project law. Non-compliance is a bug. | Apply pattern in all new/modified code. Flag any non-compliant code in touched files for alignment in the same ticket. |
| `mandatory` | Use for all new code in this ticket. | Apply pattern in new or modified files. Do not chase mismatches in unrelated existing files. |
| `standard` | Documented for reference. | Apply when writing a blank-slate file. If modifying an existing file, match the existing file's style. |
| *(none)* | No registry entry. | Follow the existing code's pattern in the file being modified. Never substitute model training default. |

**Key invariant:** The fallback chain is always `enforce → mandatory → standard → existing-code → nothing`. Model training defaults are not in this chain.

---

## Registry location

```
public-project-docs/<project>/patterns/
  _index.yaml       ← master list (always read first)
  pat_cmd_1.md      ← full spec per pattern
  pat_repo_1.md
  ...
```

---

## `_index.yaml` format

```yaml
patterns:
  - id: PAT-CMD-1
    name: CQRS command handler structure
    priority: mandatory
    applies_to:
      directories: [Application/Commands]
      keywords: [IRequestHandler, Command]
    file: pat_cmd_1.md
    added_by: PROJECT-1234
    added_at: 2026-04-25

  - id: PAT-REPO-1
    name: Repository query via ScopedReadOnlyTaskDbContext
    priority: enforce
    applies_to:
      directories: [Infrastructure/Repositories]
      keywords: [ScopedReadOnlyTaskDbContext, IQueryRepository]
    file: pat_repo_1.md
    added_by: PROJECT-1100
    added_at: 2026-03-10
```

---

## Pattern file format (`pat_cmd_1.md`)

```markdown
# PAT-CMD-1 — CQRS Command Handler Structure

**Priority:** mandatory  
**Applies to:** Classes in Application/Commands/ implementing IRequestHandler

## Canonical form
[code block — the one correct way to write this]

## Anti-patterns (do NOT use)
[what the model or old code might do instead, and why it's wrong]

## Compliance check
[grep or structural rule to verify — e.g., "handler class must not inject DbContext directly"]
```

---

## How implement-plan uses this (phase 9 — `plan`)

After loading requirements-analysis.md, before writing plan.md:

1. Check if `public-project-docs/<project>/patterns/_index.yaml` exists. If not → skip, no patterns registered.
2. Identify which patterns apply: match the ticket's touched entities/directories against each entry's `applies_to.directories` and `applies_to.keywords`.
3. For each matched pattern:
   - `enforce` or `mandatory` → add a constraint block to plan.md:
     ```
     ⚠ Pattern PAT-CMD-1 (mandatory): Apply CQRS handler structure to all new command classes.
     See: public-project-docs/<project>/patterns/pat_cmd_1.md
     ```
   - `enforce` only → also add a secondary plan step: *"Scan existing touched files for PAT-CMD-1 non-compliance. Align in same PR."*
4. `standard` patterns → mention in plan.md as guidance only, no constraint marker.

---

## How implement uses this (phase 11 — `implement`)

When writing or modifying a file:

1. Check plan.md for pattern constraints (already resolved). No re-lookup needed.
2. If plan.md has a `⚠ Pattern` constraint for this file type:
   - Load the pattern file from `public-project-docs/<project>/patterns/`.
   - Write code per the canonical form, NOT per observed code or model default.
   - If existing code in the same file conflicts with the pattern → follow the pattern, note the deviation in `implement-summary.md`.
3. If no constraint in plan.md: follow the existing code's style in the file being modified.
4. Never introduce a model-default pattern that contradicts both the registry and the observed project code.

---

## Adding a new pattern

Patterns are added by the user or promoted from `/learn` retrospectives. Never auto-add without user confirmation.

Steps:
1. User says: *"document this as a [priority] pattern"*
2. Assign next ID (`PAT-XXX-N`).
3. Write `pat_xxx_n.md` with canonical form + anti-patterns + compliance check.
4. Append entry to `_index.yaml`.
5. Confirm: *"Pattern PAT-XXX-N added at [priority]. Active from next ticket."*

---

## Promoting pattern priority

User says: *"upgrade PAT-CMD-1 to enforce"*
1. Update `priority` in `_index.yaml`.
2. Warn: existing non-compliant code in those directories will be flagged on next ticket touching those files.
3. Confirm with user.

---

## Conflict resolution (pattern says X, code says Y)

| Scenario | Resolution |
|----------|-----------|
| `enforce` pattern vs existing code | Follow pattern. Log deviation in implement-summary.md. Fix existing code in same PR. |
| `mandatory` pattern vs existing code | Follow pattern in new code. Leave existing mismatches unless they're in files being modified anyway. |
| `standard` pattern vs existing code | Follow existing code. Pattern is guidance only. |
| Two patterns both apply | Higher priority wins. If same level → G1 block: surface conflict to user. |
| Pattern file referenced but missing | G1 block: *"Pattern PAT-XXX-N is registered but file is missing. Cannot proceed. Locate or recreate the pattern spec."* |

---

## Auto-induction (NEW — when registry doesn't cover a case)

The registry only contains patterns the user has explicitly documented. Most projects have many patterns that are *observable in code* but never written down. AI should detect these and apply them with appropriate confidence — not fall back to training defaults.

### When to run auto-induction

- Before writing a new file in a directory that has 3+ existing files
- Before modifying a file in a directory where the registry has no `applies_to` match
- Whenever `do-ticket-patterns.md` registry returns "no match" but plan needs to write code there

### Auto-induction algorithm

```
1. Identify the target directory (where new code will live).
2. List sibling files of similar nature:
   - same extension (.cs, .ts)
   - filename matches similar pattern (e.g., *Handler.cs for new handler)
   - same parent layer (Application/Commands, Domain/Entities)
3. Sample up to 5 sibling files (most recently modified first, by git log).
4. Read each sibling. Extract observable structures:
   - Class shape: base class, interface, attributes
   - Method signatures: return type, parameter conventions
   - Constructor injection list
   - Error handling style (throw vs Result<T>)
   - Naming conventions
   - Comment / XmlDoc presence
   - Dependency on shared base utilities
5. Identify which structures recur in 3+ samples → "induced pattern"
   2 samples → "weak pattern" (apply but flag)
   1 sample → "isolated example" (don't induce)
6. Score confidence:
   - 5/5 samples consistent → confidence: high
   - 3-4/5 consistent → confidence: medium
   - 2/5 or less → low / no induction
7. Apply induced pattern to new code.
8. Log to plan.md or implement-summary.md as a decision card per `_shared/decision-confidence-protocol.md`.
```

### Output: induced pattern card

```yaml
- decision: "Apply induced pattern: CQRS handler with IRequestHandler<TCmd, Result<T>>"
  confidence: high
  origin: auto-induction
  evidence_for:
    - "5/5 sample handlers in Application/Commands use IRequestHandler<TCmd, Result<T>>"
    - "All have [Authorize] attribute on the handler class"
    - "All inject IUnitOfWork via primary constructor"
  samples_used:
    - "Application/Commands/CreateContractorHandler.cs"
    - "Application/Commands/UpdateContractorHandler.cs"
    - "Application/Commands/DeleteContractorHandler.cs"
    - "Application/Commands/SuspendContractorHandler.cs"
    - "Application/Commands/ReactivateContractorHandler.cs"
  evidence_against: []
  applied_to: "Application/Commands/CreateNetworkHandler.cs"
  alternative: "If wrong, manually adjust shape; consider registering this as PAT-CMD-2"
  user_action_needed: false   # high confidence — auto-applied silently
```

### Confidence → action mapping

| Confidence | Action |
|------------|--------|
| `high` (5/5 or 4/5 consistent) | Apply silently. Log decision card in implement-summary.md. No user gate. |
| `medium` (3/5 consistent) | Apply, but surface in `review-priorities.md` IMPORTANT section. User can verify. |
| `low` (≤2/5 consistent) | Don't auto-apply. Fall through to training default (existing behavior). Log "no clear pattern observed". |
| Conflicting (e.g., 3 use style A, 2 use style B) | G1: surface conflict. Ask user "Which style for new code?" Save user's choice as project preference (offer to register as PAT-XXX-N for future). |

### Promotion to registry

After auto-induction succeeds 3+ times across different tickets for the same pattern:
- `/learn` skill detects via telemetry
- Proposes user: "Pattern X has been auto-induced 3+ times. Promote to PAT-XXX-N at `mandatory` priority? This makes it consistent across all future tickets."
- User confirms → write entry to `_index.yaml` + spec file → next time it's not auto-inducted, it's registry-driven (faster, more confident).

This creates a learning loop: observed patterns → induced → promoted → registry-enforced.

### Anti-patterns (do NOT do)

- ❌ Auto-induce from training defaults. Induction MUST be from observed code in this project.
- ❌ Apply low-confidence induction silently. < 3 samples = don't induce.
- ❌ Skip the decision card. Even silent auto-induction must be auditable in implement-summary.md.
- ❌ Auto-promote to registry. User confirmation required before priority promotion.

### Telemetry

```yaml
auto_induction:
  triggered_for_files: 4
  high_confidence: 3        # silent apply
  medium_confidence: 1      # surfaced
  low_confidence: 0
  conflicts: 0
  user_overrode: 0
```

`/learn` reads across tickets. Same induced pattern hit 3+ times → propose registry promotion.

### Vietnamese summary

Khi user chưa đăng ký pattern (vì project mới hoặc quên), AI tự sample 3-5 file sibling để **suy luận pattern từ code thật**:
- Nếu 4-5/5 file dùng cùng style → confidence cao → apply silent
- Nếu 3/5 → apply nhưng flag trong review-priorities IMPORTANT
- Nếu < 3 → không suy luận, fallback hiện trạng

Sau khi 1 pattern được induce nhiều lần → /learn đề xuất user promote vào registry. **Project mới không cần setup patterns thủ công — patterns tự lộ ra theo thời gian.**
