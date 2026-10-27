# do-ticket — start (every invocation)

Phase procedure for phases 0–4 — load state, branch, classify, resolve context, rebase check. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`ticket-types.md`, `do-ticket-update.md`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 0 — Load state + context

1. Read `ticket-state.yaml`. Read `ticket-context.yaml` (if exists). Read `{ticket_dir}/RESUME.md` (if exists) —
   it is the handoff a session boundary wrote: its **Left running or moved** items are true right now (undo or
   reuse them before any build or test), and its **Decided in chat** items are settled — do not ask them again.
   - Text after the ticket ID that is not a phase name (`D3: use option b`, a sentence) is the user changing
     a decision listed at the last `SESSION END`. It is not a phase arg. Write it to `decisions[]` as decided
     by the user (replacing the agent's own entry), take it through the replan question in
     `do-ticket-update.md`, and resume at `plan` instead of the next phase. None of the listed items changed →
     resume as normal.
   - If `ticket-context.yaml` exists but **fails to parse** (malformed YAML) → warn: *"ticket-context.yaml is corrupt. Recreate from state? (y/n)"* → yes: delete and go to step 4 backfill; no: abort.
2. Branch on state:
   - **No state** → fresh start → Phase 1.
   - **State exists, no phase arg, `phase != blocked` AND `phase != awaiting_dps`** → resume from next uncompleted phase.
   - **State exists, phase arg given** → validate prerequisites via `phase-contracts.yaml`. If any required input missing → FM-PREREQ-MISSING → offer earliest entry point.
   - **`phase == blocked`** → show `blocked_reason`, ask: *"Resolved? (y/n)"* → yes resume `phase_before_block` / no stop.
   - **`phase == awaiting_dps`** (set by Phase 6c lifecycle-gate) → check if `--from-dps=<session>` flag present in invocation:
     - yes → load findings, set `phase: analyze` (marked complete), advance to Phase 7 with lifecycle_findings hydrated.
     - no → show `state.dps_briefing_path` + remind user of the DPS invocation command, then exit (do not silently proceed).
3. **DPS handoff detection (fresh start only):** if `--from-dps=<session>` passed:
   - Resolve session folder: `{output}/domain-problem-solver/open/<session>/` or `closed/<session>/`
   - If folder missing → error: *"DPS session `<session>` not found. Provide full folder name or omit `--from-dps`."*
   - If `investigation-findings.md` missing in folder → error: *"Session found but no `investigation-findings.md` — DPS must reach verdict 'code change needed' before handoff."*
   - If `final_status: BLOCKED` → warn: *"DPS session is BLOCKED (inconclusive). Handoff not recommended. Proceed anyway? (y/n)"*
   - Load findings → store in `ticket-context.yaml`:
     - `dps_session_id` ← frontmatter `session_id`
     - `dps_session_path` ← resolved folder path
     - `dps_final_status` ← frontmatter `final_status`
     - `domain_entities_in_scope` ← "Entities involved"
     - `risk_factors` ← derived from "Risk level"
     - `complexity_flags` ← from findings (cross-service flag if present)
     - `dps_open_assumptions` ← "Open assumptions" section (array of strings)
     - `dps_suggested_strategy` ← "Suggested implement strategy" field
   - Set `ticket_type = bugfix-investigated` (skip Phase 2 classify)
   - Set `skip_phases: [classify, requirements, analyze]` in ticket-context
   - Proceed to Phase 1 (branch) as normal.

4. Backfill missing context: if `ticket-state.yaml` exists but `ticket-context.yaml` doesn't, reconstruct these fields from state + projects.md — do not ask user:
   - `resolved.output_root` ← from projects.md `output`
   - `resolved.repos` ← from projects.md `repos`
   - `resolved.base_branch` ← from state `base_branch` or projects.md `base_branch`
   - `resolved.branch_name` ← from state `branch`
   - `ticket_type` ← from state `ticket_type` (if set)
   - `worktree_mode` ← from state `worktree_mode`
   - All other fields left empty — downstream phases will repopulate incrementally.
5. Stale-fingerprint sweep (resume only — skip on fresh start): run
   `python _shared/tools/ticket_fingerprints.py check {ticket_dir}`. Exit 0 → continue silently. Exit 3 →
   FM-FINGERPRINT-STALE for the files printed as `DRIFT` only (`unmapped` keys are not drift). Exit 2 → the
   tool could not read the folder; fix the path or do the sweep by hand. If the tool cannot run, do it by
   hand: for each file in `ticket-context.fingerprints`, compute its current SHA-256 (first 16 hex chars,
   as the tool writes them) and compare. Same →
   continue. Different → FM-FINGERPRINT-STALE for the drifted files only (a key with no file behind it is not
   drift). A fingerprint line carrying
   `# refreshed <date>: <reason>` is an edit the run made on purpose and already accepted — do not re-ask about
   it. Before raising the FM, open the drifted file's own history if the folder is a git repo
   (`git -C {output} log -1 -- <file>`): if the last change came from this ticket's own run, refresh it with
   that reason instead of asking.

## Phase 1 — Branch setup

**A. Fresh ticket (no worktree):**
1. Confirm repo paths from `projects.md` (skip if already loaded in pre-flight) → save to `ticket-context.resolved.repos`.
2. Confirm base_branch (default from `projects.md` or `master`).
3. Check current working tree: run `git status --short`.
   - **Dirty AND current branch = `<TICKET_ID>`** (F5) → user already on correct branch with in-progress work → proceed without stashing. No checkout needed.
   - **Dirty AND current branch ≠ `<TICKET_ID>`** (F4) → G5: offer (a) `git stash push -m "do-ticket stash: <current_branch> before switching to <TICKET_ID>"` then switch (never auto-pop), (b) git worktree (recommended for parallel work).
   - **Clean** → proceed to step 4.
4. Checkout or create branch:
   - Branch exists locally (F2) → `git checkout <TICKET_ID>` (do not re-create) — unless its work is
     already merged. Squash merges hide this from `git branch --merged`, so check
     `gh pr list --head <TICKET_ID> --state merged`. Merged → create `<TICKET_ID>a` (then b, c) from
     `<base_branch>`, or delete the old local branch first. Never stack new work on a merged branch.
   - Branch exists on remote only (F3) → `git checkout -b <TICKET_ID> origin/<TICKET_ID>`.
   - Branch does not exist anywhere → `git checkout -b <TICKET_ID> <base_branch>`.
5. Save `ticket-state.yaml` and initial `ticket-context.yaml`.

**B. Worktree mode (`--worktree` or trigger phrase):**
1. Check if worktrees already exist (W2): read `state.worktree_paths` — if set and all paths exist on disk → reuse existing worktrees, skip `worktree-setup`, proceed to step 3.
2. If worktrees do not exist → invoke `worktree-setup <TICKET_ID>`. Port conflicts are resolved inside `worktree-setup` (W3).
3. Save returned `worktree_paths` + `worktree_ports` to state with `worktree_mode: true`.
4. All subsequent file ops resolve through `worktree_paths`. The `env-gate` phase (14) reminds user to use worktree ports.

**C. Resume — normal mode:**
1. Run `git status --short` before any checkout.
   - **Dirty AND current branch ≠ state branch** (R4) → G5: offer (a) `git stash push -m "do-ticket stash: <current_branch> before resuming <TICKET_ID>"` then switch, (b) git worktree.
   - **Clean** → proceed.
2. Current branch ≠ state branch → `git checkout <state.branch>` automatically.
3. Branch missing locally (R3):
   - Ask: *"Branch `<state.branch>` not found. Recreate from `<base_branch>`? (y/n)"*
   - yes → `git checkout -b <state.branch> <base_branch>`.
   - no → `phase: blocked`, `blocked_reason: "branch missing, user declined recreate"` → stop.

**D. Resume — worktree mode:**
1. Read `state.worktree_paths`.
   - **All paths exist on disk** (R5) → validate each path is a valid git worktree (`git worktree list`) → proceed.
   - **Any path missing** (R6) → warn: *"Worktree(s) at `<missing_paths>` no longer exist. Recreate? (y/n)"* → yes: re-invoke `worktree-setup <TICKET_ID>` → update state; no: `phase: blocked`, `blocked_reason: "worktrees missing, user declined recreate"`.
   - **`worktree_paths` empty but `worktree_mode: true`** (R7) → treat as R6: offer recreate.

## Phase 2 — Classify ticket type

Runs after `branch` (1) so Jira metadata can be fetched alongside.

**Skip conditions (D1):**
- `--type=` flag provided → apply directly, skip to step 5.
- `--from-dps` mode → `ticket_type` already set to `bugfix-investigated` in Phase 0 → skip entirely.
- Resume AND `ticket-context.yaml` already has `ticket_type` set → skip entirely, use existing type.

1. Load `do-ticket/ticket-types.md`.
2. Fetch Jira metadata (issue_type, labels, components, title).
   - **API fail / ticket not found (A4):** do not retry. Ask user once: *"Cannot reach Jira. Enter ticket type manually or type 'abort'."* Valid types listed in `ticket-types.md`. User input → skip to step 4 with that type; 'abort' → stop.
3. Apply classification heuristics → propose `ticket_type` + signal used.
   - **Sub-task (A5):** if `issue_type == "Sub-task"` → fetch parent ticket type → propose same type as parent with note: *"Sub-task of `<PARENT_ID>` — inheriting type `<parent_type>`. Correct?"*
   - **Hotfix signal (B3):** if classified as `hotfix` → stop and redirect: *"This looks like a hotfix. Use `/hotfix-deploy` instead of `do-ticket`. Proceed with hotfix-deploy? (y/n)"* → y: hand off to `hotfix-deploy`; n: continue with user-specified type.
   - **Spike signal (B4):** if classified as `spike` (issue_type `Spike`/`Question`, or a "Questions to Answer" / `Q-1` list in the description) → stop and redirect: *"This is a spike — it asks questions, it does not ask for code. Use `/spike <TICKET>`. Proceed with spike? (y/n)"* → y: hand off to the `spike` skill; n: continue with user-specified type. do-ticket has no runnable phase list for this type (see `ticket-types.md`).
4. Confirm with user:
   > "Auto-classified as `<type>` based on `<signal>`. Key phases: `<3-4 most important phases only>`. Confirm or override? (confirm / use \<type\>)"
   - **Empty input (C4):** default = confirm.
   - **Override with unknown type (C3):** validate against type list in `ticket-types.md`. If invalid → *"Unknown type `<X>`. Valid types: [list]. Try again."* Re-prompt once; if still invalid → abort.
5. Recompute `risk_profile` + `risk_factors` from the confirmed type's entry in `ticket-types.md` (C2 — always recompute, even on override).
6. Save `ticket_type`, `risk_profile`, `risk_factors` to `ticket-context.yaml`.
6b. **Record the triage prior** (one line, no analysis): from the **ticket text alone** — before any code
   or plan evidence exists — write `ctx.triage_prior: easy | normal | hard` per the rule in
   `triage-scoring.md`. Phase 9.7 compares it against the scored `CLEAR` to detect the
   *looks-easy-but-isn't* trap. Computing it later, with the plan already read, would make that flag
   unfalsifiable hindsight — so it is captured here or not at all. Skip when the type skips 9.7.
7. Compute phase list from the type's section of `ticket-types.md`. This is the flow shape for the rest of the run.

## Phase 3 — Resolve context

Finalize `ticket-context.yaml` so every downstream child skill can read it without re-fetching anything.

**Step 1 — Verify resolved.* fields (B1: do NOT re-read projects.md if already set)**
These fields are set by Phase 1 step 5 (fresh start) or Phase 0 backfill (resume without context). Only populate if missing:
- `resolved.output_root` ← from projects.md `output` (if missing)
- `resolved.repos` ← from projects.md `repos` (if missing)
- `resolved.base_branch` ← from projects.md or state `base_branch` (if missing)
- `resolved.branch_name` ← from state `branch` (if missing)

**Step 2 — Compute fingerprints (idempotent — safe to recompute on retry)**
- `fingerprints.projects_md_sha` ← SHA-256 of `~/.claude/skills/assistant/projects.md`
- `fingerprints.project_docs_index_sha` ← SHA-256 of `{project_docs}/_index.yaml` (skip if file does not exist)

**Step 3 — Append phases_run entry**
Write `{phase: "resolve-context", completed_at: <ISO8601>}` to `phases_run[]` per the canonical format defined in the phase loop.

**Contract:** after Phase 3, every child skill reads `ticket-context.yaml` as single source of truth. No independent project re-reads allowed outside `{project_docs}/`.

## Phase 4 — Rebase check (on resume only — not first run)

```bash
git -C <repo_root> fetch origin
BEHIND=$(git -C <repo_root> rev-list --count HEAD..origin/<base_branch>)
```

**Fetch failure:** if `git fetch` fails (network, auth, no remote) → warn: *"Cannot reach origin — branch staleness unknown. Proceed anyway? (y/n)"*. Yes → continue with BEHIND=0 assumption, log `rebase_skipped: "fetch-failed"` to telemetry. No → `phase: blocked`, `blocked_reason: "fetch failed"`.

| BEHIND | Action |
|--------|--------|
| 0 | Proceed |
| 1-20 | Warn + offer rebase. **If user declines** → proceed without rebase, log `rebase_declined: true, behind_count: N` to telemetry. On conflict if rebase accepted → FM-REBASE-CONFLICT |
| >20 | FM-LARGE-DIVERGENCE → offer rebase vs cherry-pick to fresh `-v2` branch. **If user declines both** → `phase: blocked`, `blocked_reason: "large divergence, user declined options"`. |

**Post-rebase push warning:** always remind user to use `git push --force-with-lease` (never `--force`).

**Plan staleness check:** if `plan.md` exists, `plan_written_at` set, and `BEHIND > 0` → show new commit subjects → ask whether they affect plan → if yes, re-run `implement-plan update`. If no → proceed.
