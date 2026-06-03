---
name: code-quality-review
description: Code-quality discipline for do-ticket. Two checkpoints — a thin structural-quality gate injected into Phase 9 (plan), and a full diff-scoped review at Phase 13.5 (post-implement, pre-commit). Modeled on a strict-reviewer QUALITY mandate, adapted for brownfield .NET. Catches what completeness-audit (Phase 13) and invariant-check (Phase 7/19) cannot: is the produced code well-structured, thin, non-duplicative, and clean?
---

# do-ticket — Code-Quality Review

**Created:** 2026-06-01

## Why this exists

do-ticket already proves a change is **domain-correct** (Phase 6/7/19 + flow-gate) and **complete** (Phase 13 completeness-audit). Nothing proved it was **well-built**. That gap is why tickets ship domain-correct code with fat handlers, duplicated logic, leaked layers, and rubber-stamp tests.

This file adds the missing layer — a QUALITY pass with a strict reviewer mandate: **push back with actionable bullets; rubber-stamping is forbidden.** It is the brownfield-appropriate analogue of fail-red architecture tests + a reviewer (a brownfield codebase cannot retrofit fail-red arch tests cheaply, so the lever is a judgment pass, not a mechanical gate).

## Two checkpoints, different scope

The dividing principle: **push a check to plan-time iff it is knowable from the plan; everything that lives at the line-of-code level must wait until the code exists.**

| Checkpoint | When | Catches | Cost to fix |
|---|---|---|---|
| **Structural gate** (this file §A) | Phase 9 `plan`, folded into the existing confidence-gated review | Wrong layer · new-handler-vs-extend-fat-one · improve-vs-mirror decision · duplication of *existing* logic | Cheap — edit words |
| **Full review** (this file §B) | **Phase 13.5 `code-quality-review`**, after implement+regression+completeness-audit, before env-gate | Handler thinness · naming vs glossary · introduced duplication · dead weight · data-access waste · error handling · test meaningfulness · conventions conformance | Expensive — rewrite + re-test |

The post-code review is the **primary** one — the user's complaint ("domain correct, code structure weak") is about properties of written code, invisible in a plan.

---

## §A — Structural gate (Phase 9, plan-time)

do-ticket injects a `structural_quality` decision group into the Phase 9 confidence-gated review (alongside the existing decision cards). It is **not** a separate user prompt unless something fails — it rides the existing plan review gate.

For the proposed change in `plan.md`, the planner answers four questions and records each as a decision card with confidence:

1. **Layer placement** — does each proposed edit sit in the right layer? (business logic → domain/application, not controller; no infra type referenced from domain.) Flag any misplacement as a `low`-confidence card → forces it into the plan review surface.
2. **New vs extend** — for each method/class being grown: is it already carrying ≥3 responsibilities? If extending it adds a 4th, propose a new handler/service instead and note why.
3. **Improve-vs-mirror** (per `feedback_quality_over_mirror`) — for every "follow existing pattern X" decision: state explicitly *"pattern X does A; new code uses B for the same behavior because B is cleaner"* OR *"mirroring X verbatim — its quirk is load-bearing because <reason>"*. A silent "copy pattern X" with no improve/mirror verdict is itself a finding.
4. **Duplication of existing logic** — does the proposed logic re-implement something that already exists and should be called instead? (One targeted grep of the touched area is enough — this is a plan-time smell check, not an exhaustive search.)

**Gate behavior:** these four feed the existing Phase 9 decision tree. If any is `low`-confidence or flags a problem → it appears in the ≤5 CRITICAL items the user reviews. If all clean → auto-proceed (no extra interruption). Record the four verdicts in `plan.md` under a `## Structural quality` heading and in `ticket-context.structural_quality_decisions[]`.

**Skip when:** `ticket_type ∈ {doc-only, spike, hotfix}` (hotfix = surgical-patch, no drive-by improvement by rule). `migration-only` runs only question 1 (layer placement of the migration code, if any).

---

## §B — Full review (Phase 13.5, post-code)

### Scope discipline (read first — non-negotiable)

**Review the DIFF, not the repo.** The unit of review is `git diff <base>...HEAD` — new and changed lines plus their immediate enclosing method/class. Pre-existing debt in untouched code is **out-of-scope by default**: a brownfield codebase has unbounded debt and reviewing it all is scope creep. When pre-existing debt is *adjacent and relevant*, record it as an `out-of-scope` finding (→ optionally a `spawn_task` follow-up) but **do not fix it in this ticket.** This is the discipline that lets the gate have teeth without exploding scope.

### Methodology

1. Get the diff: `git diff` of staged+unstaged changes for this ticket (or `git diff <base_branch>...HEAD` if already committed in an update cycle).
2. For each changed hunk, walk the 10 dimensions below. Cite `file:line`.
3. Assign every finding a **severity** and **disposition** (table after the dimensions).
4. Write `code-quality-review.md` to the ticket folder.
5. Apply the gate: any `must-fix` open → block, loop to implement. Otherwise surface `nice-to-have` for a fix-now/defer decision and proceed.

### The 10 dimensions

| # | Dimension | What a finding looks like |
|---|---|---|
| 1 | **Layering & placement** | Business logic in a controller; domain type importing `Infrastructure.*`; query logic inside a command handler |
| 2 | **Handler/service thinness** | A handler that loads + branches + maps + calls 3 services inline; a method doing >1 job; orchestration tangled with rules |
| 3 | **Naming vs ubiquitous language** | A variable/method/class whose name doesn't match `{project_docs}/domain/_glossary.yaml`; misleading name (`GetX` that mutates) |
| 4 | **Duplication (introduced)** | The same block copy-pasted across the diff; logic the diff re-implements that already exists elsewhere and should be reused |
| 5 | **Dead weight** | Unused param/using/local; commented-out code; an interface added with exactly one implementation and no test seam needing it |
| 6 | **Data access & control flow** | `ToListAsync` then `foreach`+filter instead of `AnyAsync(predicate)`; N+1; two round-trips where one query suffices; deep nesting that a guard clause flattens *(the canonical `feedback_quality_over_mirror` smell)* |
| 7 | **Error handling** | Swallowed exception (`catch {}`); catch-all that hides real failures; a null/edge path no test covers |
| 8 | **Test meaningfulness** | A test that asserts on the mock, not the SUT; `Assert.NotNull` as the only assertion; a negative case that doesn't actually trigger the guard; false-green (passes even if the code is reverted) |
| 9 | **Conventions conformance** | Diff violates a rule in `{project_docs}/conventions.md` / `conventions/*.yaml`. **New recurring pattern with no convention →** propose adding one (note it; do not silently invent) |
| 10 | **Mirror-vs-improve audit** | A "followed pattern X" decision from the plan that propagated debt instead of improving it, with no load-bearing justification (closes the loop on §A question 3) |

### Severity & disposition

| Severity | Definition | Default disposition |
|---|---|---|
| **must-fix** | Introduced (not pre-existing) defect in correctness-adjacent quality: leaked layer, swallowed error, false-green test, duplicated logic that will drift, fat handler that buries a rule | **Blocks commit.** Loop to Phase 11 implement → re-run 12/13/13.5 |
| **nice-to-have** | Real improvement, not blocking: a cleaner data-access call, a better name, a guard clause, a small extraction | User picks `fix-now` / `defer` (→ `ticket-context.deferred_quality_items[]`) |
| **out-of-scope** | Pre-existing debt in code this ticket merely touched | Log only; optionally `spawn_task` a cleanup. **Never fix here.** |

**must-fix ALSO includes** — a **behavior change with no requirements trace AND no test locking it**, regardless of how small or mechanical the diff looks. The highest-signal defect on real brownfield diffs is a silent behavior change camouflaged by an unrelated rename/refactor (e.g. a compaction loop quietly deleted). Catch these even when the surrounding hunk looks trivial. Resolution: confirm it's intended (trace to requirements) + add a test that locks the new behavior — then it downgrades to resolved.

**must-fix EXCLUDES (→ out-of-scope, never a block)** — anything whose only fault is **mirroring a pattern already pervasive in untouched code** (e.g. a new endpoint that sources `clusterId` from query exactly like its 6 siblings). The fix spans code this ticket didn't introduce, so it belongs in a spawned follow-up, not bolted onto this ticket. Marking it must-fix is the canonical scope-creep failure — blocking a small feature on a repo-wide redesign.

### Output: `code-quality-review.md`

```markdown
# Code-Quality Review — <TICKET_ID>

Diff reviewed: <N files, +X/-Y lines>  ·  Generated Phase 13.5 at <ISO>

## Verdict: <CLEAN | MUST-FIX (n) | NICE-TO-HAVE (n)>

## must-fix
- [ ] <dim #> `file:line` — <one-line problem> → <one-line fix>

## nice-to-have
- [ ] <dim #> `file:line` — <problem> → <suggested improvement>   (decision: fix-now/defer)

## out-of-scope (pre-existing, not fixed)
- <dim #> `file:line` — <debt noted> (follow-up: <spawned task / none>)

## Conventions
- New pattern observed with no convention: <describe> → propose adding to conventions.<file>?  (y/n)
```

### Gate (the teeth)

- `must-fix` list non-empty → **do not proceed to env-gate.** Set `phase: code-quality-review` with the open list in `ticket-context.quality_findings[status=open]`. Loop: implement → regression → completeness-audit → code-quality-review. (FM-QUALITY-MUST-FIX.)
- `must-fix` empty, `nice-to-have` present → surface the list once; user chooses per item `fix-now` / `defer`. Defer logs to `ticket-context.deferred_quality_items[]` and surfaces in the Phase 23 done summary + PR description.
- All clean → 1-line summary (`Code-quality: clean (N hunks, 0 must-fix). Proceeding.`) and proceed. Mirror the Phase 9 auto-proceed ethos: don't interrupt when there's nothing worth interrupting for.

### Lite mode

For `bugfix-small` and `refactor`: run dimensions 1, 2, 4, 6, 8 only (the structural+test core); skip glossary/conventions deep-checks. ≤1-screen output.

---

## What this is NOT

- **Not a bug hunter** — correctness bugs are caught by tests + api-test (Phase 15) + invariant-check. This is quality only. (Mirrors the `/code-review` vs `/simplify` split.)
- **Not a repo-wide audit** — diff-scoped, always. Pre-existing debt → out-of-scope.
- **Not a parallel meaning model** — this touches only the code-quality layer; it does not introduce one (the meaning layer is the scan-init artifact suite, not a separate model doc).
