# do-ticket — build part

Phase procedure for phases 10 `unit-tests`, 11 `implement`, 12 `regression`, 12.7 `contract-recheck`, 13 `completeness-audit`, 13.5 `code-quality-review`. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`blast-radius.md`, `triage-scoring.md`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 10 — `unit-tests`
- Build must compile. False-green tests resolved before proceed (FM-FALSE-GREEN-TEST).
- DLL lock → FM-DLL-LOCKED.
- FE: also Jest specs + Storybook stories (mandatory for `fe-only`).
- **Record the RED count (mandatory — `red_count_contract`).** Run the new tests and paste the runner's own
  summary line verbatim into `unit-tests-written.md`:
  `RED: 5 failed, 0 passed, 0 skipped — <cmd> exit 1`. Write `red_count` to `ticket-context.yaml`.
  **`0 failed` at RED is a STOP, not a pass** — it means the filter matched nothing, or the tests
  assert nothing. A test that never runs is also never red, and RED is the cheapest place in the
  whole pipeline to catch a mistyped `--filter`. Phase 12 reconciles green against this number.

## Phase 11 — `implement`
- **Entry gate (G-T0):** if `ticket-context.armed_gates` is non-empty and `contract_approved_at` is unset →
  **block**, go back to Phase 9.8. Auto-implement on a legacy surface without an approved contract is the
  exact thing the contract exists to make safe.
- Strategy from `implement/strategies.yaml`. Default `tdd-strict` for crud-feature.
- DB migration → G3 pause for manual migration.
- 3 same-root failures → FM-3X-SAME-ROOT (auto-pivot before G8).
- Re-plan escape: if implement signals "REPLAN NEEDED" → **answer the replan question first**
  (`do-ticket-update.md` → *"The replan question"*): is this a DECISION, or FOLLOWING the existing code?
  *Following* needs the pattern and its file named — no name means it is a DECISION, and a decision owes
  counts, a `## Options considered` table and approval **before** any source edit. Then write
  `update-implement-vN.md` → run `implement-plan update` → `write-unit-tests update` → `implement continue`.
- Domain layer importing infrastructure → FM-LAYER-VIOLATION (warn + ack).
- **Post-implement reminder:** after implement completes, always remind user: *"Restart the service in your IDE before running tests — running process holds the old DLL."* (mandatory — see FM-DLL-LOCKED observation). In a test-fix loop, ask once for the debugger to stay stopped for the whole loop (router § Known Gotchas).

## Phase 12 — `regression`

**Re-run the suite here. Do not accept implement's word for it (`evidence_contract`).** This phase used to
pass by finding the string `Regression check: PASS` inside a markdown file the agent had just written
itself — so a run that matched **zero tests** (mistyped `--filter`, wrong test project, DB-integration
classes cut by the local filter) exited 0, the agent wrote `PASS` truthfully, and phases 13→16 all unlocked
on a measurement that never happened. That is exactly PROJ-11098: local green, CI red, because the
reflection callers and the Postgres integration classes never ran locally.

A count cannot be faked the way a verdict can. `implement-summary.md` must carry the runner's line:

```
Regression: 214 passed, 0 failed, 3 skipped (baseline 214) — dotnet test exit 0
```

Three states, not two — **PASS** (`failed == 0` and `passed > 0`) · **FAIL** (`failed > 0`) ·
**N/A** (`passed + failed == 0` — could not measure). N/A blocks like a failure.

Blocks on:
- Line absent → prose "PASS" is not evidence.
- `tests_run == 0` → the filter matched nothing. Show the raw runner output.
- `passed < baseline` → the suite **shrank**; something stopped being collected. Explain first.
- `passed < red_count` (Phase 10) → the new tests aren't all being collected.
- `build/test.yaml` declares an integration/DB suite the local filter excludes → run it, or record it
  explicitly as `DEFERRED-TO-CI` in the summary. An excluded suite must never read as green.

Then **plan-changeset drift check** (FM-PLAN-CHANGESET-DRIFT): `git diff --name-only` vs files in plan → ack both lists.

**Drift ack is two independent decisions:**
- Unplanned files in diff → show list: *"These files changed but are not in plan. Keep (y) or unstage (n)?"*
- Planned files missing from diff → show list: *"These planned files have no changes. Intentional skip (y) or implement them first (n)?"*
Both must be resolved before phase 12 completes.

**Triage recalibration (when `ticket-triage.md` exists):** a real diff now exists, so the Phase 9.7
estimate gets scored. Run `git diff --shortstat` **per repo** (each with its own `cd` — a bare git command
reuses the previous repo's cwd and succeeds with the wrong answer), then append the `## Reality check`
block per `triage-scoring.md`. **Downgrade one mode band** and print the reason
if `actual_files / predicted_files ≥ 2` or `≤ 0.4`, or a repo in the diff was not listed by triage, or a
VETO condition became true during implement (a guard removed, a migration added). Keep the original score
visible — a silently corrected estimate is an estimate that drifts. Write both numbers to telemetry.

**Do not commit yet** — commit happens at phase 16, after env-gate (14) and api-test (15).

## Phase 12.7 — `contract-recheck` (T1)

**Skipped when `armed_gates` is empty.** Runs after `regression` (12), before `completeness-audit` (13).

Re-runs **the same command** recorded at T0 and compares against **the same printed baseline** — verbatim,
never re-derived. Four checks:

| Check | Pass condition |
|---|---|
| frozen tests | pass count ≥ T0 baseline, **and the failure set is unchanged** (no new name) |
| preconditions | identical to T0 (e.g. `docker_running`). A changed precondition **invalidates the comparison** |
| reach-old-path test | green — or `no_marker: true` was recorded at T0, in which case say so out loud |
| counts | `blast-radius.md` numbers re-run to the same values; a moved count means the change reached further than the contract said |

**All four green → this is the payoff: no second review.** Print one line with the scope
(`✅ contract held — 147→170 passed, same 3 known failures, 0 counts moved`) and continue.

**Any red → loop back to `implement` (11).** A count that moved is not a small thing: it means the blast
radius grew after the user approved it, so the approval no longer covers the change. Re-approve at T0.

**Never soften this by re-deriving the baseline.** *Baseline verbatim* — a threshold adjusted after seeing
the result is not a threshold.

## Phase 13 — `completeness-audit`

After `regression` (12) PASS, before `env-gate` (14). Senior-engineer review pass per `implement/completeness-checklist.md`.

For each change-type detected in this ticket (new_endpoint, new_field_on_entity, schema_migration, refactor, bugfix, etc.), AI runs the per-type checklist:
- ✅ Confirmed (with code reference)
- ⚠️ Skipped (with reason)
- ❌ Gap (must decide: add / defer / reject)

**State the scope measured, always.** The header of `completeness-audit.md` and every verdict line
must say what was actually examined — `<N> change-types detected across <F> files`. If zero
change-types are detected, that is **N/A, not clean**: re-check the diff resolution before
proceeding. A checklist run over an empty file set produces the same ✅ as one run over forty.

Output: `completeness-audit.md`. Gaps block phase 16 (`commit`) until user decides each.

**Gap tracking:** write each unresolved gap to `ticket-context.completeness_gaps[]` as `{id: "gap-N", description: "...", status: open}`. As user decides each → update status to `resolved | deferred | rejected`. Phase 16 step 16a checks that no entry has `status: open` before proceeding.

**Skipped for:** `doc-only`, `spike`, `refactor` (refactor uses characterization-tests checklist instead). Smoke version (5 items) for `bugfix-small`, `hotfix`. Full version for `crud-feature`, `bugfix-investigated`, `migration-only`, `fe-only`.

**Generate `review-priorities.md`** here too (per `_shared/risk-prioritization-protocol.md`):
- Walk decision cards from plan + implement
- Walk mappings from `mapping-integrity-protocol.md`
- Classify CRITICAL / IMPORTANT / ROUTINE per rules
- Cap CRITICAL at 5; if >5, scope likely too big → suggest split

User reviews `review-priorities.md` (5-min read), not 40-file diff.

## Phase 13.5 — `code-quality-review`

Runs after `completeness-audit` (13), before `env-gate` (14). The QUALITY pass do-ticket was missing — completeness-audit asks "did you cover the change-types", invariant-check asks "is it domain-correct"; this asks **"is the code well-built"**. Full spec, dimensions and output template in `code-quality-review.md` §B.

**Mandate:** strict-reviewer discipline — push back with actionable bullets; rubber-stamping is forbidden.

**Scope discipline (non-negotiable):** review the **DIFF only** (`git diff` of this ticket's changes + immediate enclosing method), never the whole repo. Pre-existing debt in touched-but-unchanged code = `out-of-scope` finding (log, optionally `spawn_task`); **never fixed here.** This is what keeps the gate sharp without scope creep in a brownfield codebase.

**Dimensions (29, in 11 groups).** Judges CODEBASE HEALTH only — never business correctness (that is `completeness-audit`) and never domain correctness (that is `invariant-check`). Five groups are always on: shape & placement · reuse & waste · language-level hazards (null, time/culture, equality, error handling) · convention & language · design judgement. Six are **gated on what the diff contains**, not on what the ticket is about: .NET runtime (async, cancellation, disposal, enumeration) · data & persistence (EF, transactions, unbounded results, migration safety) · concurrency & shared state · operability (logging, config) · security surface · tests. Full table + trigger rules in `code-quality-review.md`. **The output must name the groups skipped and their trigger** — a silently absent group reads the same as one that found nothing.

**Gate (the teeth):**
- Each finding → `must-fix` / `nice-to-have` / `out-of-scope`.
- Any `must-fix` open → **do not proceed.** Write open items to `ticket-context.quality_findings[status=open]`, set `phase: code-quality-review`, loop back to `implement` (11) → `regression` (12) → `completeness-audit` (13) → here again. (FM-QUALITY-MUST-FIX.)
- `must-fix` empty + `nice-to-have` present → surface once; per item `fix-now` / `defer` (defer → `ticket-context.deferred_quality_items[]`, surfaces in Phase 23 summary + PR description).
- All clean → 1-line summary, proceed (don't interrupt when nothing's worth interrupting for).
- **The 1-line summary must carry the scope**, never a bare "clean":
  `✅ Quality review clean — 14 files, 380 added lines reviewed (base: origin/master)`.
  A review of an empty diff yields the identical ✅ to a review of forty files, and an empty diff is
  easy to produce by accident: wrong `<base>` after a rebase, renamed base branch, or git running in
  the wrong repo dir on a multi-repo ticket.
  **0 files or 0 added lines → N/A, not clean** — re-resolve the base and confirm the repo dir; on a
  multi-repo ticket, check every repo.

**Output:** `code-quality-review.md` in the ticket folder.

**Skipped for:** `doc-only`, `spike`, `hotfix` (surgical-patch forbids drive-by improvement). **Lite version** for `bugfix-small`, `refactor` — shortens the always-on groups but still runs every content-gated group the diff triggers, because a one-line fix that adds a `.Result` is exactly the diff nobody reviews. **Full** for `crud-feature`, `bugfix-investigated`, `migration-only`, `fe-only`.
