---
name: do-ticket-update
description: Update cycle handler for do-ticket. Invoked when requirements change mid-ticket or QC finds missing cases after initial PR. Child skill — not user-facing.
---

# Update Cycle

Triggered by: `do-ticket <TICKET_ID> update`

Phase numbers below match the canonical enumeration in `do-ticket/SKILL.md` (§ "Canonical phase enumeration").

1. Ask: *(a) requirements changed in Jira, (b) QC found missing cases*
   - **(c) the design shape changed** — the requirements are the same, but the chosen shape was replaced
     (the user overrode the plan's shape, or `implement` found the shape cannot hold the requirement).
     This is not an update cycle: nothing about the ask moved. Do **not** increment `update_count`.
     **Freeze code first:** stop editing source files, leave uncommitted work as it is, and do not
     resume until the new shape is approved. Then re-enter at phase 9 (`plan`). See step 3b for the
     file rule.
2. **Increment `update_count` first** (before writing any files). In the same step, in `run-telemetry.yaml`:
   `update_cycles.count += 1` and append `{at: <date>, trigger: requirements-changed | qc-found-bug,
   after_merge: <true if Phase 23 done already ran>}` to `update_cycles.triggers[]`. A `qc-found-bug` with
   `after_merge: true` is the quality number that cost is weighed against: a bug that got past every gate.
   `requirements-changed` is not a miss — keep the two apart.
3. Write delta to `update-implement-v<update_count>.md` — never overwrite a previous version. Preserves full history of what changed each round.
3b. **`plan.md` is under the same never-overwrite rule when the SHAPE changes.** Copy the current file to
   `plan-v<N>.md` first (N = the count of shapes tried, starting at 1), then write the new shape into
   `plan.md`. The step-3 rule was written for update cycles only, so a shape swap slipped past it and
   overwrote the plan wholesale — seen on PROJ-11350, where the rejected option-C plan survived only
   in git history. **A `## Options considered` table is worthless once the rejected shape is unreadable:**
   the reader cannot check whether it was rejected for a real reason, or just for the newest opinion. Each
   `plan-v<N>.md` keeps its own header line: `Superseded by plan-v<N+1> — <the fact that killed this shape>`.
4. If (a): re-run phase 5 (`requirements`) → phase 6 (`analyze`) → show requirements diff → write `update-implement-v<N>.md` → re-run the implementation chain in update mode: phases 9 (`plan`) → 10 (`unit-tests`) → 11 (`implement`) → 12 (`regression`) → 13 (`completeness-audit`) → 14 (`env-gate`) → 15 (`api-test`) → 16 (`commit`) → 17 (`pre-push`) → 18 (`ci-check`) → 19 (`invariant-encoded`) → 21 (`pr-ready`, regenerate description).
5. If (b): ask user for missing cases → update `test-cases.md` (phase 8) → write `update-implement-v<N>.md` → re-run the implementation chain (same phase list as step 4).
6. Child skills (`implement-plan`, `implement`) receive the path `update-implement-v<N>.md` explicitly — they do not assume the filename.
7. Increment `pr_count` when user confirms PR raised.

---

## The replan question — answer it before writing any new plan

Applies at **every** replan: the (c) branch above, an `implement` signal of `REPLAN NEEDED`, and a
user override of the plan's shape. `phases/build.md` Phase 11 points here rather than repeating it.

> **Is this a DECISION, or is it FOLLOWING the existing code?**

| Answer | What it obliges |
|---|---|
| **Following** | The pattern already in the code holds the new requirement. Go lite. **Name the pattern and the file you are following.** |
| **Decision** | The existing pattern cannot hold it. Then, before editing any source file: counts from `blast-radius.md`, a `## Options considered` table, and approval |

**The teeth:** *"follows the existing code"* with **no file named** is not a follow — it is a decision nobody
has looked at. **No name → it is a DECISION.** Same shape as the 8.7 rule that an inventory row marked "no"
must say why. The default leans to the expensive side on purpose: guessing wrong that way costs time, and
guessing wrong the other way costs what PROJ-11350 lost.

**Why here and not at classify (Phase 2).** Phase 2 has only the ticket text, and ticket text lies.
PROJ-11350 is `issue_type: Bug` with no "regression" in the title, so the classify rules make it
`bugfix-small` — a one-page lite plan and no `analyze`, for a change that replaced the change-history
mechanism across three record types. Correct by the rules, wrong in every way that mattered. At replan
the evidence exists: the code has been touched, something has failed, and the counts are on disk.

**It runs more than once.** A type promotion is one-way and fires once. This question is asked at every
replan — PROJ-11350 replanned twice, and neither time produced an options table until the user asked for
one.
