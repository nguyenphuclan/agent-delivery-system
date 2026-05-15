# do-ticket Quality Review

**Started:** 2026-05-10
**Status:** Complete — all 23 phases reviewed

---

## Evaluation methodology

For each phase, run in this order:

### Step 1 — Enumerate real-world cases first
Before evaluating or improving, list ALL cases that can actually occur at that phase.
Think in terms of state variables: what are all the values each variable can hold, and what combination of those values produces a distinct code path?

Example variables for Phase 1:
- fresh vs resume
- branch exists locally / remote only / not at all
- working tree clean / dirty
- current branch = target / different
- worktree mode on / off / worktree already exists

Do NOT evaluate quality until the case matrix is complete. Missing a case = missing a gap.

### Step 2 — Score each case against 3 criteria

| Criterion | What it means | Red flag |
|---|---|---|
| **Fast** | Does this case produce unnecessary waits, re-asks, or round-trips the user already answered? | G10 for known info, retry loops, re-confirming confirmed decisions |
| **Save token** | Does this case waste tokens on duplicate reads, full phase lists, unnecessary fetches? | Re-reading already-loaded files, printing 20-phase lists when 3 suffice, retrying failed API calls |
| **Quality / Exactly** | Does this case produce ambiguous, wrong, or incomplete output? | Silent failures, wrong defaults, missing "no" paths, unvalidated user input, crash without message |

### Step 3 — Fix only what hits a criterion
If a gap does not impact any of the 3 criteria → drop it. Do not fix for completeness alone.

---

## Review progress

### ✅ Phase 0 — load-state
**Cases reviewed:** fresh start, resume with context, resume without context, corrupt context, blocked state, stale fingerprints
**Fixes applied:**
- Corrupt `ticket-context.yaml` → warn + offer recreate (Quality)
- Backfill schema defined explicitly — list of fields to reconstruct without asking user (Quality + Fast)
- Stale-fingerprint sweep guarded `resume only` (Quality — minor)

---

### ✅ Phase 1 — branch setup
**Cases reviewed:** 14 cases across fresh/resume × worktree/normal × dirty/clean × branch-exists/missing
**Fixes applied:**
- F2: Branch already exists locally → `checkout` not `create` (Quality — crash fix)
- F3: Branch on remote only → `checkout -b origin/<branch>` (Quality)
- F5: Dirty tree, already on correct branch → continue without stash (Quality — wrong-stash prevention)
- W2: Worktree already exists → reuse, skip worktree-setup (Fast + Save)
- R4: Resume, dirty tree on wrong branch → G5 before checkout (Quality)
- R6: Resume worktree mode, worktrees deleted → validate + offer recreate (Quality)
- R7: `worktree_mode: true` but `worktree_paths` empty → treat as R6 (Quality)
- Stash message now includes source branch + target ticket ID (Quality)
- "Branch missing, user says no" → `phase: blocked` with reason (Quality — missing path)

---

### ✅ Phase 2 — classify ticket type
**Cases reviewed:** Jira metadata quality, classification signals, user actions, resume state
**Fixes applied (SKILL.md + ticket-types.md):**
- A4: Jira API fail → ask user once, no retry loop (Fast + Save)
- A5: Sub-task → fetch parent type, inherit + confirm (Quality)
- B3: Hotfix signal → hard stop + redirect to `hotfix-deploy` (Fast + Save + Quality)
- C2: User override → always recompute `risk_profile` + `risk_factors` from lookup table (Quality)
- C3: Invalid type string → validate + re-prompt once → abort (Quality)
- C4: Empty input → default = confirm (Quality)
- D1: Resume with `ticket_type` already set → skip phase entirely (Fast + Save)
- Confirm prompt now shows 3-4 key phases only, not full list (Save)
- `risk_factors` lookup table added to `ticket-types.md` as recompute source (Quality)

---

### ✅ Phase 3 — resolve-context
**Cases reviewed:** fresh/normal, Phase-0-backfill, crash-retry, _index.yaml missing, phases_run format
**Fixes applied:**
- B1: Phase 3 re-populated Phase 1 fields → now "verify if missing, do not re-read projects.md if already set" (Save + Quality)
- B2: No idempotency note on fingerprint writes → added "idempotent — safe to recompute on retry" (Quality)
- D1: `phases_run` entry format undefined → defined: `{phase: "resolve-context", completed_at: <ISO8601>}` (Quality — /learn telemetry)

---

### ✅ Phase 4 — rebase-check
**Cases reviewed:** fresh (skip), fetch fails, BEHIND=0, BEHIND 1-20 user accepts/declines rebase, BEHIND>20 user declines both options, rebase conflict, plan staleness with BEHIND>0
**Fixes applied:**
- Fetch failure → warn + offer continue; log `rebase_skipped: "fetch-failed"` to telemetry (Quality — missing "no" path)
- User declines rebase (1-20) → proceed + log `rebase_declined: true` (Quality — missing path)
- User declines both options on LARGE-DIVERGENCE → `phase: blocked` (Quality — missing path)
- Plan staleness "no" path → now explicit: proceed if commits don't affect plan (Quality — implicit was ambiguous)

---

### ✅ Phase 5 — requirements
**Cases reviewed:** fresh + Jira accessible/fails, resume + requirements.md exists/missing, jira.fetched_at stale, update_count > 0, comment-count changed
**Fixes applied:**
- Jira fail on fresh run → offer manual entry or abort (Quality — no path existed; could loop or crash)
- Jira staleness on resume (>24h) → offer re-fetch + show delta (Quality — stale requirements silently used)
- D1 skip: covered by universal M1 added to generic phase loop

---

### ✅ Phase 6 — analyze
**Cases reviewed:** fresh, resume with existing analysis + unchanged inputs, open questions, clarity < 60, dependent ticket not done, readiness gate miss
**Fixes applied:**
- Speed-mode activation result → set `speed_mode: true` in context, pass `--speed-mode` to phases 8-11 (Quality — orchestrator had no handling for accept/reject)
- D1 skip: covered by universal M1

---

### ✅ Phases 7–8 — invariant-scope, test-cases
**Cases reviewed:** skip conditions, readiness gate, D1 resume, update cycle for test-cases
**Fixes applied:**
- D1 skip for both: covered by universal M1 (Fast + Save)
- No other criteria-hitting gaps found; existing docs are complete for these phases.

---

### ✅ Phases 9–10 — plan, unit-tests
**Cases reviewed:** fresh, update mode, auto-proceed vs surface-critical, force-restart, pattern file missing, FE mode, build fail
**Fixes applied:**
- D1 skip: covered by universal M1
- Pattern file missing on fresh project → skip pattern matching, proceed with auto-induction only (already implied by SKILL.md "if no match" language; no explicit fix needed — criteria score 0)

---

### ✅ Generic Phase Loop
**Cases reviewed:** D1 skip (absent for all phases), phases_run format (only defined in Phase 3)
**Fixes applied:**
- **M1 — Universal D1 skip:** added as Step 0 to generic phase loop (resume only, bootstrap phases 0-3 exempt) (Fast + Save — every resume was re-running completed phases)
- **phases_run canonical format:** moved to generic loop step 3; Phase 3 note simplified (Quality — format was duplicated / inconsistently implied)

---

### ✅ Phase 11 — implement
**Cases reviewed:** fresh tdd-strict, DB migration, 3x same root, re-plan, resume mid-implement, layer violation, service running during implement
**Fixes applied:**
- Post-implement service restart reminder (mandatory, per FM-DLL-LOCKED observation) (Quality — observation rule had no enforcement point in skill flow)

---

### ✅ Phase 12 — regression
**Cases reviewed:** PASS present, PASS missing, plan-changeset drift (unplanned files, planned files missing)
**Fixes applied:**
- Drift ack split into two independent decisions with y/n for each (Quality — "ack both lists" was ambiguous; no defined meaning for each)

---

### ✅ Phase 13 — completeness-audit
**Cases reviewed:** all gaps resolved, some gaps open, doc-only/spike skip, bugfix smoke version
**Fixes applied:**
- `completeness_gaps[]` structured tracking in `ticket-context.yaml` with `status: open/resolved/deferred/rejected` (Quality — gaps had no machine-readable state; Phase 16 had no way to check them)

---

### ✅ Phase 14 — env-gate
**Cases reviewed:** user confirms, services not running, worktree ports, build/run.yaml missing, service restarted after code change
**Fixes applied:**
- Service restart reminder added (mandatory) (Quality — implement could deploy stale DLL)
- build/run.yaml missing → ask user to list manually; do not block entirely (Quality — hard block was wrong; manual confirmation still satisfies gate)

---

### ✅ Phase 15 — api-test
**Cases reviewed:** fresh learn, cached entities, specimen find/create, silent bug, wrong env profile, services not running, skip path
**Fixes applied:** None — phase is well-specified. No gaps hit any criterion.

---

### ✅ Phase 16 — commit
**Cases reviewed:** all green → 16a → 16b, deferred clarifications, completeness gaps open, user says n at 16b, commit-with-flags path
**Fixes applied:**
- Step 16a: also checks `completeness_gaps[status=open]` — forces decision per gap before commit (Quality — completeness-audit gaps had no enforcement path)
- Step 16b "n" path: offer (a) files, (b) message, (c) abort → on abort `phase: blocked` at api-test (Quality — missing "no" path caused undefined state)

---

### ✅ Phases 17–20 — pre-push, ci-check, invariant-encoded, qa-checklist
**Cases reviewed:** secrets, unprotected endpoint, empty migration Down, CI pass/fail/env, invariant skip conditions, qa skip conditions
**Fixes applied:**
- Phase 17 migration double-ask: scored (Save token) but migration is still asked because user may have skipped api-test — leaving it as-is is safer.
- D1 skip for phases 19-20: covered by universal M1
- No other criteria-hitting gaps found.

---

### ✅ Phase 21 — pr-ready
**Cases reviewed:** first PR, PR already exists (update cycle), PR closed/merged before re-create, gh not in PATH, user says n
**Fixes applied:**
- Update cycle: check if PR exists → `gh pr edit` if yes; `gh pr create` after rebase confirm if no (Quality — would create duplicate PRs on review rounds)

---

### ✅ Phase 22 — pr-review
**Cases reviewed:** SPLIT-REQUEST, MUST-FIX, NICE-TO-HAVE, no comments, multi-PR base
**Fixes applied:**
- NICE-TO-HAVE handling: offer include/defer/dismiss; defer logs to `ticket-context.deferred_review_items[]` (Quality — category was silently unhandled)

---

### ✅ Phase 23 — done
**Cases reviewed:** normal completion, worktree cleanup, deferred items remaining
**Fixes applied:**
- Summary structure defined: ticket ID + PR link, phases completed/skipped, duration, all deferred/unresolved items as follow-up actions (Quality — "print summary" was undefined)

---

## 🔲 Remaining phases

| Phase | Status |
|---|---|
| All phases complete ✅ | — |

---

## How to resume

1. Open this file first to see what's done.
2. Pick the next phase from the remaining list.
3. Follow the methodology: enumerate cases → score against 3 criteria → fix only what hits a criterion.
4. Mark the phase ✅ when done, list all fixes applied.
