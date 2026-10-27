# do-ticket — ship part

Phase procedure for phases 18 `ci-check` to 23 `done`. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`run-telemetry-schema.md`, `failure-modes.yaml`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 18 — `ci-check`
Because push-code (17) already ran the SonarAnalyzer rules + new-code coverage locally and gated on them, CI Sonar should not discover *those* late. **It is still the only check for duplication on new code, for CONDITION coverage and for the server-side quality gate**, so this phase is a real gate, not a formality: ask pass / not applicable / fail. On fail → FM-CI-FAILURE classify code vs env. If CI Sonar diverges from the local gate (e.g. new-code baseline mismatch — see `push-code/sonar-local-gate.md`), treat it as a signal to reconcile the local scan, not just re-push.

On a CI failure: read the failing check's log, fix, run the push-code gate for the repo you touched, commit a
NEW commit (no amend, no force push on a pushed branch), push.

**CI Sonar counts CONDITIONS, the local gate counts LINES (FM-SONAR-LOCAL-CI-DIVERGE).** One PR read 85.7%
locally (18/21 lines) and 70.7% in CI (16 of 38 conditions uncovered: every `?.`, `??` and ternary on a new
line). Do not guess. Ask the server which conditions are missing (`api/sources/lines?...&pullRequest=<n>` →
`conditions` / `coveredConditions`), then add one test per missing branch.

**Shared lib first, consumers after.** When the ticket changes a shared library that other services consume
as a package, consumer CI may NOT build against the shared PR. If consumer workflows install the shared
package with no pinned version, they compile against the newest package published from the shared repo's
main branch — while locally a `ProjectReference` uses the shared branch on disk. Three cases:
1. *Compatible change* (consumers only stop using removed members): consumer CI is green against the OLD
   package. It never built against the NEW one. After the shared PR merges and its `<Version>` is published
   (shared main-branch build green), re-run each consumer's CI once (`gh run rerun <id>`) BEFORE the consumer
   merges.
2. *Consumer needs a new shared API*: consumer CI is red (`CS0117` / `CS1061` / `CS0246` naming a member that
   exists only in the open shared PR). That is "waiting for shared", NOT a defect: change no code, do not
   "fix" it, note it on the PR. After shared is merged + published, `gh run rerun --failed`.
3. *Version collision* (another ticket bumps the shared package first): the shared PR gets a conflict ->
   merge `origin/<base_branch>` into the branch (merge commit, no force push), set `<Version>` = base + 1
   (FM-SHARED-VERSION-COLLISION), run the push-code gate, push.
Nothing re-runs consumer CI when a PR in another repo merges. The trigger for cases 1 and 2 is the shared PR
merging — then check the package is published and re-run consumer CI.

## Phase 19 — `invariant-encoded`
Skipped if `invariant-scope` (7) was skipped. Gaps warned, not blocked.

## Phase 20 — `qa-checklist`
Skipped for `refactor`, `hotfix`, `doc-only`, `migration-only`, `spike`.

## Phase 21 — `pr-ready`
**Update cycle handling:** if `state.pr_count > 0` → check if PR already exists for this branch (`gh pr view` or equivalent). If yes → `gh pr edit` to update description, not create. If no (PR was closed/merged) → confirm base branch is current before `gh pr create`.

Show generated PR description → wait for explicit user `y/n` before `gh pr create` / `gh pr edit`.

> **Windows note:** if `gh` not in PATH, fall back: `powershell -Command "& 'C:\Program Files\GitHub CLI\gh.exe' pr create ..."`.

## Phase 22 — `pr-review`
On reviewer comments → invoke `handle-pr-review`:
- SPLIT-REQUEST → write `split-plan.md`, increment `pr_count`, guide split.
- MUST-FIX → write `update-implement.md` → re-run the implementation chain in update mode: phases 9 (`plan`) → 10 (`unit-tests`) → 11 (`implement`) → 12 (`regression`) → 13 (`completeness-audit`) → 13.5 (`code-quality-review`) → 14 (`env-gate`) → 15 (`api-test`) → 16 (`commit`) → 17 (`pre-push`) → 18 (`ci-check`) → 19 (`invariant-encoded`).
- NICE-TO-HAVE → offer: (a) address in this PR — add to `update-implement.md`; (b) defer to follow-up ticket — log to `ticket-context.deferred_review_items[]` as `{comment_id, description, status: deferred}`; (c) dismiss with reason logged.
- Re-run pr-description (21) with delta summary. Increment `review_round`.

Each review round is a session boundary (S3 in the router § Sessions): the next round runs as
`do-ticket <TICKET_ID> pr-review` in a fresh session.

**Multi-PR base:** `pr_count >= 2` and prior PR merged → rebase on latest main first.

## Phase 23 — `done`
- **HARD CHECK before the Jira status moves on:** open what the ticket owes and check it by hand —
  `run-telemetry.yaml` (parses, holds the required minimum from `run-telemetry-schema.md`, describes this run),
  `implement-summary.md` (carries the Phase 12 `Regression:` line), and every other output the type's phases
  declare in `phase-contracts.yaml`. Something missing or hollow → fix it first; do not move the status on a
  failed check.
- Worktree cleanup if applicable.
- **DPS session cleanup:** if `ticket-context.dps_session_id` set → *"This ticket originated from DPS session `<session_id>`. Close it now? (y/n)"* → yes: move folder from `open/` to `closed/`, write `## Resolution Summary: resolved via <TICKET_ID>` at top of `investigation.md`.
- Print summary (required structure): (1) ticket ID + PR link, (2) phases completed + any skipped with skip reason, (3) total duration from `run-telemetry.yaml`, (4) any unresolved items — `completeness_gaps[status=deferred]`, `deferred_review_items`, `deferred_quality_items`, unresolved `requirements-clarifications.yaml` entries, and every open `M2-open` decision in `decisions[]`. If any unresolved items exist → list them as follow-up actions.

**Post-ticket quality debrief (mandatory — do not skip):**

Ask the user these 3 questions, one at a time. Answers written to `run-telemetry.yaml.quality_signals`. If user says "skip" or gives no answer → write empty arrays and proceed.

> **1. Noise:** Was there any phase where I asked for something I should have already known? (e.g. asked for the base branch, re-read a file already loaded, re-confirmed a decision already made)
> *(one line per item, or "none")*

> **2. Wrong output:** Was there any output you had to manually correct? (plan, requirements, test-cases, PR description, etc.)
> *(one line per item: what file + what was wrong, or "none")*

> **3. Missing:** Was there anything you expected to see in a phase output that wasn't there?
> *(one line per item: which phase + what was missing, or "none")*

After collecting answers → write to `quality_signals` per schema. Then close `run-telemetry.yaml` (set `ended_at`, `duration_seconds`). These signals feed `/learn` → concrete SKILL.md proposals after ≥2 occurrences.

**Post-ticket learn prompt (mandatory — runs after PR is merged and ticket is closed):**

> "PR merged and ticket complete. Run `/learn` now to capture session insights as permanent improvements? (y/n)"

- `y` → invoke `/learn`. The learn skill will ask the verification gate ("verified bug-free?") before writing anything permanent.
- `n` → skip. Remind: *"Run `/learn` any time to revisit this session."*

This step is the primary feedback loop from ticket execution back into skill quality. Do not skip it silently.
