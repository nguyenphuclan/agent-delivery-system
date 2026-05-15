---
name: do-ticket
description: End-to-end ticket execution — Jira → branch → analyze → plan → implement → test → PR. Adaptive flow shape per ticket type (crud-feature, bugfix, hotfix, refactor, spike, doc-only, migration, fe-only). Phase strategies are pluggable per-skill. Failure modes auto-pivot via registry. Supports resume, parallel worktrees, update cycles, PR review loops. Every run produces telemetry consumed by /learn for continuous improvement.
tech_stack: [jira, atlassian-mcp, github, gh-cli]
---

## Pre-flight

**Tier: A** (heavy multi-step orchestration, mutating side effects).

Follow `~/.claude/skills/_shared/pre-flight-protocol.md` BEFORE any other action — runs regardless of how this skill was invoked (direct `/do-ticket`, orchestrator routing, mid-flow handoff).

Skill-specific overrides:
- `requires_project_fields`: [active, output, repos, base_branch, jira_prefix]
- `risk_signals`: [g3-implied (commit, push, deploy may follow), g7-implied (potential prod data, auth surfaces)]
- `requires_phase_readiness`: true — before each phase runs, read `{project_docs}/_index.yaml` → `phase_readiness[<phase>]`. If `ready: false` → G10 with options `rescan` / `skip` / `abort`. Gate ID and missing artifacts per phase are defined in `phase-contracts.yaml` (`readiness_gate`, `stale_check` fields).
- `skip_when`: `ticket-state.yaml` exists for this `<TICKET_ID>` with `phase` not in [`initial`, `null`] (Tier D — resume mode)

User no longer needs `/assistant` prefix — pre-flight is built in.

---

# do-ticket — adaptive ticket orchestrator

## Architecture

**Spine** (rigid, consistent): phase contract — every phase has named inputs, outputs, state writes, and failure modes. The contract is the law.

**Strategies** (plural, adaptive): within each phase, multiple strategies achieve the contract. Picked per ticket type, risk, and prior outcomes. Strategy can switch mid-flow on failure.

**Flow shape** (per ticket type): the sequence of phases is computed from `ticket_type`, not hardcoded. A 1-line bugfix and a cross-service migration travel different paths through the same contracts.

**Failure pivots** (registry-driven): known failure patterns auto-pivot before falling back to human gates. The registry grows from telemetry over time.

### Companion files

| File | Purpose |
|------|---------|
| `ticket-types.md` | Type matrix: which phases run for each ticket_type |
| `phase-contracts.yaml` | Per-phase inputs/outputs/state writes — replaces static prereq table |
| `failure-modes.yaml` | FM-XX registry — auto-pivots before human gates |
| `ticket-context-schema.md` | Schema for the shared resolved-once context object |
| `run-telemetry-schema.md` | Schema for per-ticket telemetry → /learn auto-improvement |
| `do-ticket-patterns.md` | Code pattern registry protocol |
| `do-ticket-update.md` | Update cycle protocol |
| `<skill>/strategies.yaml` | Per-skill strategy registry (implement, analyze-requirements, write-test-cases, learn-crud) |

---

## Trigger

```
do-ticket <TICKET_ID> [phase] [--worktree] [--type=<type>] [--from-dps=<session-folder>]
```

Examples:
- `do-ticket PROJECT-1234` — fresh start or resume from last completed phase
- `do-ticket PROJECT-1234 plan` — force restart from `plan`
- `do-ticket PROJECT-1234 update` — new PR cycle
- `do-ticket PROJECT-1234 pr-review` — handle reviewer comments
- `do-ticket PROJECT-1234 --worktree` — parallel worktree stack
- `do-ticket PROJECT-1234 --type=hotfix` — explicit type override (skip auto-classification)
- `do-ticket PROJECT-1234 --from-dps=terminate-603-bug-2026-05-02` — DPS handoff mode: skip classify + requirements + analyze; hydrate context from `investigation-findings.md` in the given session folder
- `do-ticket PROJECT-1234 --speed-mode` — vague PO + hard deadline. Activates `_shared/self-detailing-requirements-protocol.md`: AI fills ambiguities with sourced defaults, surfaces only `needs_po` items (1-3), bulk-accept the rest. PR description auto-includes "AI-Decided Defaults" audit. Total user time at analyze ≈ 2 min.
- `do-ticket PROJECT-1234 show-context` — print ticket-context.yaml for debugging

**Auto speed-mode:** If `analyze-requirements` scores requirement clarity < 60/100 (vague verbs, no AC, "miễn chạy là dc" signals), AI proposes activating self-detailing automatically. User can accept or override.

**Flow gate auto-routing:** Phase 6c (after analyze) checks `{project_docs}/flows/flow_index.yaml` for business flows touched by this ticket (matched by flow keywords + entity references). If a touched flow has `health != ok` OR `known_gates[]` → offers proactive DPS routing BEFORE plan (see Phase 6 step 6c). Replaces the old "wait for FM-3X-SAME-ROOT during implement" recovery pattern.

**Worktree trigger detection:** also activate `--worktree` when user says "worktree riêng", "song song", "parallel", "isolated stack".

If `<TICKET_ID>` is missing → ask: *"Which ticket ID? (e.g. PROJECT-1234)"*

---

## Path resolution — `{output}` variable

`{output}` is read from `~/.claude/skills/assistant/projects.md` → active project → `output` field.

**Fresh start:** read projects.md → if `output` not set → G10: ask user → save → continue. All ticket files live under `{output}/tickets/<TICKET_ID>/`.

**Resume:** re-read projects.md every invocation — never hardcode in state. Path may have changed between sessions.

---

## State + Context files

Two files. State = workflow position. Context = resolved facts.

### `ticket-state.yaml`
```yaml
ticket_id: PROJECT-1234
phase: implement              # last completed phase (or "blocked" or "awaiting_dps")
phase_before_block: null
pr_count: 0
update_count: 0
review_round: 0
blocked_reason: null
worktree_path: null
worktree_mode: false
worktree_offset: null         # +100, +200, etc. — auto-allocated by worktree-setup
worktree_paths: {}            # service-keyed map: { identity_provider, third_party_mock, api_task, sla, connector, scheduler, api_portal, automation, shared_lib }
worktree_ports: {}            # service-keyed map (same keys as worktree_paths minus shared_lib): effective port = main_port + offset
# Flow-gate (Phase 6c) state — written when gate fires:
dps_briefing_path: null       # abs path to dps-briefing.md (when phase = awaiting_dps)
flow_gate_decided: false      # true once user has chosen route/skip/block on this run
last_updated: 2026-04-12T10:00:00
```

### `ticket-context.yaml`
Resolved snapshot read by all child skills. Schema in `ticket-context-schema.md`. Built at phase 3 (`resolve-context`), refined incrementally per phase.

### `run-telemetry.yaml`
Per-ticket signal capture. Schema in `run-telemetry-schema.md`. /learn consumes across all tickets.

---

## Canonical phase enumeration

Reading order = execution order. The numbers below are the **canonical sequence for `crud-feature`** (the fullest flow). Other ticket types skip a subset — see `ticket-types.md` for which phases each type runs.

**Bootstrap (always runs, in this order):**

| # | Phase | What it does |
|---|-------|--------------|
| 0 | `load-state` | Read `ticket-state.yaml` + `ticket-context.yaml`; branch on resume vs fresh |
| 1 | `branch` | Set up git branch (or worktree); verify repo paths |
| 2 | `classify` | Auto-classify `ticket_type` from Jira metadata; user confirms |
| 3 | `resolve-context` | Populate `ticket-context.yaml` with resolved paths + fingerprints |
| 4 | `rebase-check` | (Resume only) Verify branch is not stale vs base |

**Work phases (canonical crud-feature order — others skip per `ticket-types.md`):**

| # | Phase | Skill |
|---|-------|-------|
| 5 | `requirements` | jira-to-requirements |
| 6 | `analyze` | analyze-requirements (sub-steps: 6a context-expansion → 6b analyze → 6c flow-gate) |
| 7 | `invariant-scope` | invariant-check (--pre) |
| 8 | `test-cases` | write-test-cases |
| 9 | `plan` | implement-plan |
| 10 | `unit-tests` | write-unit-tests |
| 11 | `implement` | implement |
| 12 | `regression` | do-ticket internal (verify implement-summary) |
| 13 | `completeness-audit` | do-ticket internal (per-change-type checklist) |
| 14 | `env-gate` | do-ticket internal (services-running confirmation) |
| 15 | `api-test` | learn-crud |
| 16 | `commit` | do-ticket internal (16a clarification recheck → 16b commit prompt) |
| 17 | `pre-push` | do-ticket internal (secrets/auth scan) |
| 18 | `ci-check` | do-ticket internal |
| 19 | `invariant-encoded` | invariant-check (--post) |
| 20 | `qa-checklist` | qa-checklist |
| 21 | `pr-ready` | pr-description |
| 22 | `pr-review` | handle-pr-review |
| 23 | `done` | do-ticket internal (close telemetry) |

**Hard ordering invariants** (cannot be reordered regardless of ticket type):
- `regression` (12) must complete before `commit` (16)
- `api-test` (15) must complete or be explicitly skipped before `commit` (16)
- `commit` (16) must complete before `pre-push` (17)
- `pr-ready` (21) requires explicit user `y/n` before `gh pr create`

When this file references "phase N" it means the table above. When it references a phase by name (e.g. `commit phase`), the same. Numbered sub-steps inside a phase use letters: `16a`, `16b`.

---

## On every invocation

### Phase 0 — Load state + context

1. Read `ticket-state.yaml`. Read `ticket-context.yaml` (if exists).
   - If `ticket-context.yaml` exists but **fails to parse** (malformed YAML) → warn: *"ticket-context.yaml is corrupt. Recreate from state? (y/n)"* → yes: delete and go to step 3 backfill; no: abort.
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
4. Stale-fingerprint sweep (resume only — skip on fresh start): for each completed phase, compute current SHA of inputs vs `ticket-context.fingerprints`. Drift → FM-FINGERPRINT-STALE → offer regen of dependents.

### Phase 1 — Branch setup

**A. Fresh ticket (no worktree):**
1. Confirm repo paths from `projects.md` (skip if already loaded in pre-flight) → save to `ticket-context.resolved.repos`.
2. Confirm base_branch (default from `projects.md` or `master`).
3. Check current working tree: run `git status --short`.
   - **Dirty AND current branch = `<TICKET_ID>`** (F5) → user already on correct branch with in-progress work → proceed without stashing. No checkout needed.
   - **Dirty AND current branch ≠ `<TICKET_ID>`** (F4) → G5: offer (a) `git stash push -m "do-ticket stash: <current_branch> before switching to <TICKET_ID>"` then switch (never auto-pop), (b) git worktree (recommended for parallel work).
   - **Clean** → proceed to step 4.
4. Checkout or create branch:
   - Branch exists locally (F2) → `git checkout <TICKET_ID>` (do not re-create).
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

### Phase 2 — Classify ticket type

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
4. Confirm with user:
   > "Auto-classified as `<type>` based on `<signal>`. Key phases: `<3-4 most important phases only>`. Confirm or override? (confirm / use \<type\>)"
   - **Empty input (C4):** default = confirm.
   - **Override with unknown type (C3):** validate against type list in `ticket-types.md`. If invalid → *"Unknown type `<X>`. Valid types: [list]. Try again."* Re-prompt once; if still invalid → abort.
5. Recompute `risk_profile` + `risk_factors` from the confirmed type's entry in `ticket-types.md` (C2 — always recompute, even on override).
6. Save `ticket_type`, `risk_profile`, `risk_factors` to `ticket-context.yaml`.
7. Compute phase list from the type's section of `ticket-types.md`. This is the flow shape for the rest of the run.

### Phase 3 — Resolve context

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

### Phase 4 — Rebase check (on resume only — not first run)

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

---

## Ad-hoc phase escape hatch

The fixed phase list per `ticket_type` is the default path — **not a cage**. When the AI judges that the standard sequence is not the most effective path *for this specific situation*, it may insert an **ad-hoc phase** between two regular phases.

Ad-hoc phases are bounded — they preserve the spine while allowing exploration:

- **Allowed contexts:** mid-flow discovery suggests a quick check would change the plan; a domain question must be resolved before continuing; a similar feature should be read as reference.
- **Forbidden contexts:** skipping a regular phase (use type promotion instead); writing production code (must happen in `implement` phase only); modifying state of other tickets.

### Whitelisted ad-hoc phases

| Ad-hoc phase | Purpose | Output |
|--------------|---------|--------|
| `quick-api-poke` | Make 1 API call to validate an assumption before plan/implement | finding noted in `ticket-context.adhoc_findings[]` |
| `consult-dps` | Invoke domain-problem-solver mini-session for a specific question | `investigation-findings.md` (mini), reference in context |
| `read-reference-feature` | Read a similar feature already in codebase as a reference for plan/implement | reference paths added to `ticket-context.reference_files[]` |
| `verify-domain-rule` | Quick Track B lookup for one specific invariant | rule_id cited in `ticket-context.invariants_in_scope` |
| `quick-db-query` | One read-only DB query to confirm data shape (per assistant rules — psql, LIMIT 10, no writes) | finding noted in `ticket-context.adhoc_findings[]` |
| `consult-runbook` | Look up a saved runbook for a recurring problem | runbook path noted, applied if relevant |

### Protocol (mandatory transparency)

When the AI decides to insert an ad-hoc phase, it MUST declare in chat:

```
[ad-hoc] Pausing <current-phase> at step <N>.
Inserting <ad-hoc-phase> because <one-line reason>.
Will resume <current-phase> with new context.
Estimated time: <e.g., 2 min>.
```

Then run the ad-hoc phase. When done:

```
[ad-hoc complete] <ad-hoc-phase> finished.
Findings: <one-line>.
Resuming <current-phase>.
```

Append to `ticket-state.yaml.adhoc_phases[]` and `run-telemetry.yaml.adhoc_phases[]`:

```yaml
adhoc_phases:
  - id: quick-api-poke
    inserted_during: plan
    inserted_at_step: "validating field name on GET /tasks/<id>"
    reason: "Plan assumed field 'completionDate' but API may use 'finishedAt'"
    started: 2026-05-02T11:00:00
    duration_seconds: 90
    outcome: "Field is 'finishedAt'. Plan corrected before write."
    affected_phase_outputs: [plan.md]
```

### Hard rules

- Ad-hoc phase MUST NOT bypass `secrets-scan`, `pre-push`, `commit` user gate, or any G3/G7 gate.
- Ad-hoc phase MUST NOT write code (no edits to source). For code-writing exploration, escalate to a `quick-db-query` or `read-reference-feature` instead, then return to the proper phase.
- Maximum 3 ad-hoc phases per regular phase. After that → likely the type/strategy is wrong; switch instead.
- Each ad-hoc phase logged to telemetry. /learn detects patterns: if same ad-hoc fires often during the same regular phase → propose making it part of the regular phase.

### Why this exists

Without an escape hatch, the AI either rigidly follows the wrong path (waste) or hacks around the structure invisibly (untrustworthy). The escape hatch is bounded freedom: the AI can deviate, but must declare why and log the deviation for review.

---

## Phase loop (generic)

For each phase in the type's phase list (from `ticket-types.md`):

0. **D1 skip check (resume only — bootstrap phases 0–3 exempt):**
   - If `state.last_completed_phase >= <this_phase>` AND all input fingerprints unchanged → skip this phase.
   - Append `{phase: "<name>", completed_at: <ISO8601>, action: "skipped-d1"}` to `phases_run[]` and proceed.

1. **Pre-phase:**
   - Read phase contract from `phase-contracts.yaml`.
   - Verify `inputs.required` exist + fingerprints match.
   - If `strategies_picked.<phase>` not set in context → consult `<skill>/strategies.yaml` → apply selection rules → if no rule matches, ask user.
   - Save `strategies_picked.<phase>` to context.

2. **Invoke skill** (per phase contract `skill:` field) — pass:
   - Path to `ticket-context.yaml`
   - Strategy ID picked
   - Update mode flag (`first` | `update` | `continue`) per state

3. **Post-phase:**
   - Verify `outputs` produced.
   - Update `ticket-context.fingerprints` for new files.
   - Append `{phase: "<name>", completed_at: <ISO8601>}` to `ticket-context.phases_run[]`. This is the canonical telemetry format — always use this exact structure.
   - Append phase outcome to `run-telemetry.yaml.phases[]`.
   - Save state: `phase: <name>`, `last_updated: <now>`.

4. **On failure:**
   - Match error against `failure-modes.yaml`.
   - Match → execute pivot. If pivot needs user → save `phase: blocked` + `blocked_reason` + `phase_before_block`.
   - No match → log to `run-telemetry.unknown_failures[]` (for /learn proposals) → fall back to G1/G8.

5. **On strategy pivot** (e.g., FM-3X-SAME-ROOT):
   - Update `ticket-context.strategies_picked.<phase>`.
   - Re-invoke skill with new strategy.
   - Log `strategy_outcomes[]` entry to telemetry.

---

## Per-phase notes (deviations from generic flow)

These supplement the generic phase loop; full contracts in `phase-contracts.yaml`.

### Phase 5 — `requirements`
**DPS handoff mode (`dps_session_id` set):** skip Jira fetch entirely. Generate `requirements.md` directly from `investigation-findings.md`:
```markdown
# Requirements: <title from findings>

## Source
Investigation findings from DPS session <session_id> — <created_at>

## Bug repro
<one-line summary> + <confirmed evidence bullets>

## Acceptance criteria
- [derived from findings + open assumptions flagged as "verify before implement"]

## Out of scope
<copy from findings "Out of scope" section>
```
Save fingerprint. Proceed to Phase 6.

**Jira fail on fresh run (no existing requirements.md):** do not retry. Offer: *"Cannot reach Jira. Choose: (a) enter requirements manually — I'll open an editor stub, (b) abort."* There is no existing file to fall back to, so (b) stops the flow.

**Jira staleness (resume):** if `jira.fetched_at` is older than 24h → *"Requirements were fetched >24h ago. Re-fetch to catch new comments? (y/n)"* Yes → re-fetch and diff vs current; show delta before proceeding. No → proceed with cached version.

On `update_count > 0`: after rewrite, diff vs prior version → confirm delta with user before proceeding.

### Phase 6 — `analyze`

Two sub-steps in order: **6a context-expansion → 6b invoke analyze-requirements**.

**Step 6a — Context expansion (do-ticket internal, runs BEFORE invoking analyze-requirements)**

Pre-loads `incidents.yaml` and `topology.yaml` filtered to this ticket's scope. Output: `context-expansion.md` in ticket folder. Consumed by analyze-requirements AND plan phases as a pre-context hint — surfaces past incidents and cross-repo connectivity the agent might otherwise miss.

**Skip conditions:**
- Both `{project_docs}/incidents/incidents.yaml` AND `{project_docs}/topology/topology.yaml` missing → skip silently; analyze runs without expansion (log to telemetry: `context_expansion: not_available`)
- `--from-dps` mode → skip (DPS findings already supply richer context)
- `ticket_type == doc-only` → skip (no value)
- `ticket_type == hotfix` → skip step 6a; speed matters more than context completeness for hotfixes

**Algorithm:**

```
EXP-1  Read ticket-context.yaml + requirements.md
       Extract ticket scope:
         - components: from jira.components
         - keywords_from_title: lowercase words ≥4 chars from ticket title (skip stopwords)
         - keywords_from_desc: lowercase words ≥4 chars from requirements.md
         - mentioned_classes: ProperCase identifiers in title+description (e.g. "SyncAcPassiveEndpointJob")
         - mentioned_queues: UPPER_SNAKE_CASE tokens (e.g. "SYNC_AC_INFO_JOB")
         - mentioned_repos: any token matching ctx.resolved.repos values

EXP-2  Read {project_docs}/incidents/incidents.yaml (if status=fresh in _index.yaml)
       Score each incident:
         score = 0
         + 3 if any ticket.components overlap with incident.components
         + 2 per match between ticket keywords and incident.similar_pattern_keywords
         + 1 per match between ticket title/desc tokens and incident.root_cause_1line tokens
         + 2 if incident.recurrence_risk == "high" AND score > 0
         + 1 if incident.confidence == "confirmed"
       Output: top 10 by score, OR all with score ≥ 4, whichever is smaller
       Also collect:
         - high_risk_overlap: incidents where recurrence_risk=high AND any keyword match
         - keyword_hits_summary: which incident keywords matched, counts

EXP-3  Read {project_docs}/topology/topology.yaml (if status=fresh in _index.yaml)
       For each queue in queues:
         match_signals = []
         if queue.name in mentioned_queues → match_signals += ["queue-name"]
         if any published_by[].class in mentioned_classes → match_signals += ["publisher-class"]
         if any consumed_by[].class in mentioned_classes → match_signals += ["consumer-class"]
         if any published_by[].repo or consumed_by[].repo in mentioned_repos → match_signals += ["repo"]
       If match_signals non-empty → include this queue in output with full record (publishers, consumers, declared_in, health_flags, cross_links)
       Also flag: queues with high-severity health_flags + cross_links.incidents overlapping with EXP-2 results

EXP-4  Write {ticket_dir}/context-expansion.md (see schema below)

EXP-5  Update ticket-context.yaml:
         context_expansion:
           incidents_available: <bool>
           topology_available: <bool>
           incidents_matched: [<ids>]              # from EXP-2
           topology_queues_matched: [<names>]      # from EXP-3
           high_risk_overlap: [<incident_ids>]
           file: context-expansion.md
         fingerprints.context_expansion_sha: <sha256 of file>

EXP-6  If incidents_matched is empty AND topology_queues_matched is empty AND incidents_available
       AND topology_available → log to telemetry: `context_expansion: no_matches`
       (Not a failure — just signal that this ticket may be in untouched territory.)
```

**context-expansion.md format:**

```markdown
# Context Expansion — <TICKET_ID>

Generated by do-ticket Phase 6a. Read this BEFORE forming hypotheses.

## Past incidents matching this ticket's scope

<For each matched incident, ranked by score:>

### <ID> — <symptom_1line> (score: N, confidence: confirmed/likely/hunch)
- **Root cause**: <root_cause_1line>
- **Fix layer**: <code/infra/external/hybrid>
- **Recurrence risk**: <high/medium/low>
- **Matched on**: <component overlap, keyword X, keyword Y>
- **Lessons**: <bullets>
- **Full entry**: incidents.yaml#<ID>

<If high_risk_overlap non-empty:>
## ⚠ High-risk pattern overlap

These incidents have recurrence_risk=high AND overlap with this ticket's keywords. Strong signal that the same architectural trap may apply here:
- <id>: <root_cause_1line>

## Relevant topology (cross-repo messaging)

<For each matched queue:>

### Queue: `<QUEUE_NAME>` (broker: <broker>)
- **Publishers**: <repo.class:line>, ...
- **Consumers**: <repo.class:line>, ...
- **Infra config**: <if declared_in non-empty: durability=X, ack_mode=Y, prefetch=Z>
- **Cross-linked incidents**: <ticket ids>
- **Health flags**: <list with severity>
- **Why matched**: <match_signals>

<If a matched queue has high-severity health flags AND cross-linked incidents:>
## ⚠ Architectural concern + history

Queue `<NAME>` has open health flag `<flag_type>` (severity: high) AND prior incidents <ids>. The architectural concern has caused real bugs. Review this queue's config carefully.

## Read these BEFORE writing requirements-analysis.md

The hypothesis you form in analyze should explicitly reference these incidents/queues if relevant. If you decide none apply, note that in requirements-analysis.md so the agent doesn't re-mine the same ground later.
```

**Surface to user (optional G1 block):**
If `high_risk_overlap` is non-empty:
> *"Past incidents with high-recurrence-risk overlap this ticket: [list]. Strong signal that the architectural trap may apply here. Acknowledge before proceeding to analyze? (y/n)"*

If user `n` → do NOT block; just log to telemetry that user dismissed. The point is awareness, not gatekeeping.

If `topology_queues_matched` non-empty AND any matched queue has a high-severity health_flag:
> *"Topology found <N> queue(s) on the bug path with open high-severity flags: [list]. Review before analyze? (y/n)"*

Same — `n` is non-blocking, just logged.

---

**Step 6b — Invoke analyze-requirements (existing flow)**

**DPS handoff mode (`dps_session_id` set AND `dps_final_status: RESOLVED`):** skip analyze entirely. Carry forward from Phase 0 hydration: `domain_entities_in_scope`, `complexity_flags`, `risk_factors` already in ticket-context. Surface `dps_open_assumptions` as a G1 confirmation block:
> *"DPS session confirmed root cause. Open assumptions from investigation that need verification during plan/implement: [list]. Acknowledge and proceed? (y/n)"*
After acknowledgment → proceed to Phase 7 (invariant-scope) or next applicable phase.

**DPS handoff mode, `dps_final_status: PARTIAL`:** do NOT skip analyze — run normally, but seed analyze-requirements with the findings as pre-context (load investigation-findings.md alongside requirements.md).

Pass `context-expansion.md` (if exists) to analyze-requirements as a pre-context hint alongside requirements.md.

Open questions → G1 block. Save `phase_before_block: analyze`. Resume re-runs analyze after user resolves.

**Speed-mode activation:** if analyze returns clarity score < 60 and user accepts speed-mode → set `speed_mode: true` in `ticket-context.yaml`. Pass `--speed-mode` flag to all downstream phases (8, 9, 10, 11). If user rejects → G1 block for clarification before proceeding.

---

**Step 6c — Flow gate (proactive DPS routing)**

Runs after 6b succeeds, before Phase 7. Goal: detect tickets that touch business flows with known complexity or recorded gates, and route to DPS for a `flow-trace` BEFORE plan, instead of waiting for FM-3X-SAME-ROOT recovery during implement (which is what burned PROJ-10869a).

**Why flow-gate, not field-gate:** developers think in flows (rerouting, indication, sync), not in fields. A ticket usually touches ONE flow that may be triggered by N fields, not the other way around. flow_index is the right granularity — ~10-30 flows per project rather than 100s of fields. Field-level cascade is already implicit in code shards + topology; flow_index adds the unit-of-business view that's missing.

**Skip conditions (do not gate, proceed to Phase 7):**
- `--from-dps` mode → DPS already provided full context.
- `--from-briefing` mode → this run was itself spawned by a prior gate; do not re-gate.
- `ticket_type ∈ {doc-only, hotfix, spike}` → not enough surface area for cascade to matter.
- `state.flow_gate_decided == true` → user already decided on a prior run (don't re-prompt on resume).

**Algorithm:**

```
FG-1  LOAD: read {project_docs}/flows/flow_index.yaml (if exists)
      If missing → set ctx.flow_gate = "not_available" → skip to FG-4 (keyword-only fallback)

FG-2  FLOW MATCH: extract candidate tokens from requirements.md + requirements-analysis.md
      Lowercase ≥4-char tokens + UPPER_SNAKE_CASE tokens
      Match against flow_index.indexes.by_keyword AND flow_index.indexes.by_entity (when
      entity names appear).
      Also match flow names directly (e.g. "rerouting" → flow_index.flows.rerouting).

      touched_flows[] = unique set of matched flow ids
      For each touched_flow:
        Pull flow_index.flows.<id> record into scope.

FG-3  RISK ASSESSMENT per touched flow:
       For each touched_flow:
         If flow.health != "ok" (i.e. "degraded" or "broken") → add to risky_flows[] with reason
         If flow.complexity == "high" → add to risky_flows[]
         If flow.known_gates[] non-empty → add to risky_flows[] + carry forward gates for briefing

FG-4  KEYWORD SIGNAL fallback (no flow_index OR no flow match):
        grep requirements.md + requirements-analysis.md for any of:
          [update, trigger, connect, reroute, cascade, also fires, propagate,
           change triggers, flow doesn't trigger, when X changes Y should]
        If hit → set flow_keyword_signal = true (record matched phrases)

FG-5  DECIDE: gate fires IF (risky_flows non-empty) OR
                            (flow_keyword_signal AND ticket_type != bugfix-small AND ctx.flow_gate == "not_available")

      If gate does NOT fire → set ctx.flow_gate_decided = true, ctx.flow_gate = "passthrough"
        → log to telemetry: { gate: passthrough, touched_flows: [...], reason: <none risky> }
        → proceed to Phase 7

      If gate fires → continue to FG-6.

FG-6  SURFACE G10:
      Print:
        ⚠ Flow-gate fires for <TICKET_ID>:
          Touched flows (any): <list of flow names + one-line description each>
          Risky flows: <list with reason — health=degraded / has known_gates / complexity=high>
          Known gates pre-recorded: <list, or "none">
          Keyword signals: <matched phrases, or "none">
          Reason: <one sentence — e.g. "rerouting has 2 known gates blocking the 3rd-party API trigger path">

        Recommended: route to DPS for flow-trace BEFORE plan. DPS will:
          - Anchor on each entry handler of the flow (from flow_index + code shards)
          - Trace each TRIGGER PATH end-to-end (NOT per field)
          - Gap-analyze: which trigger paths silently drop the signal?
          - Recommend implementation options per gap
          do-ticket will then resume at plan with full flow context.

        Choose:
          a) Route to DPS (recommended)
          b) Skip — proceed to Phase 7 with plain context (logged as flow_gate_bypassed)
          c) Block — I want to investigate manually first (set phase: blocked)

FG-7  ON CHOICE a — Route to DPS:
        Write {ticket_dir}/dps-briefing.md per template below.
        Set state:
          phase: awaiting_dps
          phase_before_block: analyze
          dps_briefing_path: <abs path>
          flow_gate_decided: true
          flow_gate: routed_to_dps
        Print the exact invocation command:
          /domain-problem-solver --from-briefing=<abs path>
          (when DPS finishes, resume do-ticket via: do-ticket <TICKET_ID> --from-dps=<session-folder>)
        Halt.

FG-8  ON CHOICE b — Skip:
        Set ctx.flow_gate = "bypassed"
        Set ctx.flow_gate_decided = true
        Inject risky_flows + known_gates + keyword_signals as a WARNING block into plan context
          (saved to ctx.plan_warnings[] — implement-plan will surface them)
        Log to run-telemetry: { gate: bypassed, risky_flows: [...], reason: <user choice> }
        Proceed to Phase 7.

FG-9  ON CHOICE c — Block:
        Set state.phase: blocked, blocked_reason: "user requested manual flow investigation"
        Halt.
```

**`dps-briefing.md` template** (written at FG-7):

```markdown
# DPS Briefing — <TICKET_ID>

Generated by do-ticket Phase 6c flow-gate at <ISO>.

## Source ticket
<TICKET_ID> — <ticket title from requirements.md>
Source repos in scope: <from ticket-context.resolved.repos>

## Ticket summary
<first 5 lines of requirements.md>

## Flows in scope
<For each flow in risky_flows + touched_flows:>
### <flow_name> — <flow.description>
- Health: <ok | degraded | broken>
- Complexity: <low | medium | high>
- Triggers (from flow_index):
  - <trigger.id>: <description> (channel: <api|gui|rabbitmq|scheduled>, entry: <handler at file:line>)
  - ...
- Expected effects:
  - <effect 1>
  - <effect 2>
- Anchor handlers:
  - sync_entry: <from flow_index>
  - async_entry: <from flow_index>
  - invariant_owner: <from flow_index>
- Related entities: <list>
- Related flows: <list>
- Invariants respected: <list of rule_ids>
- Past incidents: <list of ticket ids>
- Known gates (pre-recorded blockers):
  - <kg.id>: <description> at <location>

## Keyword signals (from requirements text)
<List matched phrases — or "none">

## Past incidents to consider
<Copy from {ticket_dir}/context-expansion.md if present — entities + queues + high-recurrence overlap>

## Investigation goal
For EACH flow in scope, trace EACH TRIGGER PATH end-to-end:
1. From entry handler → cascade → final effect
2. Does each trigger actually REACH the flow's expected effect? Or is there a silent drop?
3. For each drop, what mechanism (silent-overwrite / conditional-guard / early-return / wrong-branch / missing-wire)?
4. Compare against ticket's new requirements — which trigger paths need to be wired/fixed?

## Specific decision questions (from analyze Phase 6b open items + known gates)
<bullets from ticket-context.open_questions + each known_gate.description, if any>

## Return format
Produce `investigation-findings.md` with:
- standard sections (Title, Confirmed, Open assumptions, ...)
- FLOW EXTENSION sections (flow_map per trigger path, Gap Analysis table, Decisions per gap)
- final_status: RESOLVED + suggested_implement_strategy

When DPS finishes, the user resumes this ticket via:
  do-ticket <TICKET_ID> --from-dps=<session-folder>
do-ticket will skip classify/requirements/analyze and enter plan with the full flow map
seeded into plan.md.

## Hard constraints
- Do not write code.
- Do not propose an option that conflicts with a flow invariant (flow_index.flows.<name>.invariants_respected) or a domain invariant in {project_docs}/domain/<Entity>.yaml. DPS-FM-FLOW-INVARIANT-CONFLICT applies.
- Cite each anchor handler with file:line.
- Trace BY TRIGGER PATH, not by field cascade. The question is "does this trigger reach the effect?", not "what does this field do?"
```

**Why 6c is between analyze and Phase 7 (not after plan):** the flow map informs WHAT to plan. After-plan routing means re-doing the plan once DPS returns. Before-plan routing means plan is written ONCE, with full flow context.

**Resume from `phase: awaiting_dps`:** when user invokes `do-ticket <TICKET_ID> --from-dps=<session>`, Phase 0 detects the flag, loads findings (including new flow_map + gaps + decisions), advances state to `phase: analyze` (marked complete), proceeds to Phase 7. The plan phase reads `ctx.flow_findings.*` as primary input alongside `requirements-analysis.md`.

### Phase 7 — `invariant-scope`
Skipped when `ticket_type ∈ {doc-only, hotfix, refactor}` or no entity has a domain shard.

### Phase 8 — `test-cases`
Show count + offer edit → user picks proceed/edit. **Error-path coverage check:** every `must not / cannot / reject when` constraint in analysis must have ≥1 negative test case → otherwise G1.

### Phase 9 — `plan`
- Save `plan_written_at: <now>`.
- **DPS handoff mode:** pre-set `strategies_picked.implement = <dps_suggested_strategy>` before strategy selection runs (treat as user-provided override). Surface any `dps_open_assumptions` not yet acknowledged as G1 items here.
- Pattern injection: load `do-ticket-patterns.md` → match registry → if match found: inject as decision card. If no match → run **auto-induction** (sample 3-5 sibling files) per `do-ticket-patterns.md` "Auto-induction" section → inject + **write-back**: append discovered pattern to `{project_docs}/patterns/_index.yaml` (create file if missing) + update `_index.yaml` artifacts.patterns. This is how `patterns/_index.yaml` is bootstrapped — it does not exist until first plan run, and grows ticket-by-ticket.
- Every non-trivial decision logged per `_shared/decision-confidence-protocol.md` with confidence tag (high/medium/low) + evidence cards.
- Lite mode for `bugfix-small` and `hotfix`: ≤1-page plan.

**Confidence-gated review (Q6):**
After plan.md written, compute summary:
- avg_confidence = average of all decision confidences
- low_count = count of decisions with confidence=low
- critical_mappings = count from `mapping-integrity-protocol.md` Tier 4/5 if relevant

Decision tree:

| Condition | Action |
|-----------|--------|
| `avg_confidence > 0.85` AND `low_count == 0` AND `critical_mappings == 0` AND no flagged risks | **Auto-proceed** to next phase. Print 1-line summary: *"Plan written. Confidence: high (12 decisions, 0 low). Proceeding."* |
| Any low-confidence decision OR any CRITICAL mapping OR `risk_profile == critical` OR plan flagged a risk | **G1 surface CRITICAL items only** (per `risk-prioritization-protocol.md`). Show ≤5 items, each with quick-verify action. Do NOT show full plan. User chooses per item: confirm / change / G1-block-and-edit. |
| User passes `do-ticket <ID> plan` (force-restart from plan) | Always show full plan for review (manual override) |

Goal: stop interrupting user when nothing's worth interrupting for. Surface only what matters.

### Phase 9.5 — `fe-impact-check`

Lazy FE compatibility check using the just-written plan as scope. Catches FE-BE contract drift, cardinality mismatches, and missing i18n BEFORE implement — the place mid-implementation surprises usually surface.

**Skip if:** `ticket_type ∈ {fe-only, doc-only, hotfix, refactor, spike}` OR plan touches no public API endpoint OR all affected endpoints are admin/internal (no FE caller).

**Algorithm:**
1. Extract `affected_endpoints[]` + proposed response shape / cardinality / status codes from `plan.md`.
2. Quick FE-consumer probe: grep FE repo for each endpoint URL. None consumed → write `fe-impact-check.md` with verdict `SKIPPED` and continue.
3. Otherwise spawn a narrow Explore sub-agent. Prompt carries the BE plan context (proposed shape, cardinality, status codes) + targeted FE grep scope (only the affected endpoints). Sub-agent reports conflicts (file:line + nature) and a verdict.

**Verdict gate:**

| Verdict | Action |
|---------|--------|
| `SAFE` | Continue to Phase 10. |
| `NEEDS_FE_CHANGE` | G1 surface to user: file follow-up FE ticket OR ack as known gap and continue. |
| `NEEDS_BE_ADJUST` | Loop back to Phase 9 `plan` to reconcile. |

**Output:** `tickets/{ID}/fe-impact-check.md` (small, ticket-scoped — NOT a scan-init artifact).

**Rationale:** Pre-scanning FE module structure is low-ROI for BE engineers. The only FE knowledge a BE engineer actually needs is contract compatibility per touched endpoint — and that is cheapest to derive at plan-time, scoped by the actual BE proposal, with always-fresh greps. Slip files pre-built into scan-init would go stale; an upfront full FE scan would over-collect FE wizard/i18n/state detail that the BE engineer never uses.

### Phase 10 — `unit-tests`
- Build must compile. False-green tests resolved before proceed (FM-FALSE-GREEN-TEST).
- DLL lock → FM-DLL-LOCKED.
- FE: also Jest specs + Storybook stories (mandatory for `fe-only`).

### Phase 11 — `implement`
- Strategy from `implement/strategies.yaml`. Default `tdd-strict` for crud-feature.
- DB migration → G3 pause for manual migration.
- 3 same-root failures → FM-3X-SAME-ROOT (auto-pivot before G8).
- Re-plan escape: if implement signals "REPLAN NEEDED" → write `update-implement-vN.md` → run `implement-plan update` → `write-unit-tests update` → `implement continue`.
- Domain layer importing infrastructure → FM-LAYER-VIOLATION (warn + ack).
- **Post-implement reminder:** after implement completes, always remind user: *"Restart the service in your IDE before running tests — running process holds the old DLL."* (mandatory — see FM-DLL-LOCKED observation).

### Phase 12 — `regression`
Verifies `implement-summary.md` contains `Regression check: PASS`. Then **plan-changeset drift check** (FM-PLAN-CHANGESET-DRIFT): `git diff --name-only` vs files in plan → ack both lists.

**Drift ack is two independent decisions:**
- Unplanned files in diff → show list: *"These files changed but are not in plan. Keep (y) or unstage (n)?"*
- Planned files missing from diff → show list: *"These planned files have no changes. Intentional skip (y) or implement them first (n)?"*
Both must be resolved before phase 12 completes.

**Do not commit yet** — commit happens at phase 16, after env-gate (14) and api-test (15).

### Phase 13 — `completeness-audit`

After `regression` (12) PASS, before `env-gate` (14). Senior-engineer review pass per `implement/completeness-checklist.md`.

For each change-type detected in this ticket (new_endpoint, new_field_on_entity, schema_migration, refactor, bugfix, etc.), AI runs the per-type checklist:
- ✅ Confirmed (with code reference)
- ⚠️ Skipped (with reason)
- ❌ Gap (must decide: add / defer / reject)

Output: `completeness-audit.md`. Gaps block phase 16 (`commit`) until user decides each.

**Gap tracking:** write each unresolved gap to `ticket-context.completeness_gaps[]` as `{id: "gap-N", description: "...", status: open}`. As user decides each → update status to `resolved | deferred | rejected`. Phase 16 step 16a checks that no entry has `status: open` before proceeding.

**Skipped for:** `doc-only`, `spike`, `refactor` (refactor uses characterization-tests checklist instead). Smoke version (5 items) for `bugfix-small`, `hotfix`. Full version for `crud-feature`, `bugfix-investigated`, `migration-only`, `fe-only`.

**Generate `review-priorities.md`** here too (per `_shared/risk-prioritization-protocol.md`):
- Walk decision cards from plan + implement
- Walk mappings from `mapping-integrity-protocol.md`
- Classify CRITICAL / IMPORTANT / ROUTINE per rules
- Cap CRITICAL at 5; if >5, scope likely too big → suggest split

User reviews `review-priorities.md` (5-min read), not 40-file diff.

### Phase 14 — `env-gate`
Runs after `completeness-audit` (13), before `api-test` (15). List required services → wait for explicit user confirmation services are running.

**Service restart reminder (mandatory):** also prompt: *"If you changed code in any running service during implement, restart it now to reload the updated DLL before testing."*

**build/run.yaml missing:** if the artifact is absent (readiness gate 14 not met) → ask user to list required services manually. Do not block the gate entirely — manual confirmation still satisfies the env-gate contract. Log `env_gate_manual: true` to telemetry.

### Phase 15 — `api-test` — **MANDATORY for `crud-feature` and `bugfix-investigated`**
Strategy from `learn-crud/strategies.yaml`. **Test data rule:** before creating fresh data, invoke `specimen-sandbox /specimen-find`; only create on `NOT_FOUND`. After flow produces a reusable entity, invoke `/specimen-add`.

**Hard ordering rule:** phase 15 (`api-test`) MUST complete (or be explicitly skipped per type definition) BEFORE phase 16 (`commit`) begins. Do not skip to commit even if implement + regression + unit tests all pass — running flows end-to-end against the live stack catches silent bugs that compile-time checks miss. To skip, the user must explicitly say so AND a reason is logged to telemetry.

Skip allowed only when:
- Ticket type explicitly excludes api-test (`bugfix-small` unless API surface, `refactor`, `doc-only`, `migration-only`, `fe-only`, `spike`, `hotfix`)
- User explicitly defers with "skip api-test, deploy first" — logged to `run-telemetry.skipped_phases[]`

Silent bug (200 + wrong data) → FM-SILENT-API-BUG → return to implement.

### Phase 16 — `commit`

Runs after phase 15 (`api-test`). Two sub-steps in order: 16a → 16b.

**Step 16a — Pre-commit Clarification Recheck (anti-laziness gate)**

Before showing commit prompt, run Tier 2 of `~/.claude/skills/_shared/requirements-clarification-protocol.md`:

1. Read `requirements-clarifications.yaml`.
2. Filter items with `status=deferred` AND no `addressed_at_phase` set, OR `status=dismissed` with `rework_probability > 0.7`.
3. If filtered list non-empty → **block with Tier 2 sharp reminder** (formatted box with rework cost, past incidents, 3-option choice).
4. User must choose: `pause` (default) / `commit-with-flags` / `accept-rework <reason>`.
5. `pause` → `phase: blocked`, `blocked_reason: "PO clarification pending"`. `commit-with-flags` → proceed; PR description auto-includes "Open questions" section. `accept-rework` → proceed with reason logged.

Also verify `ticket-context.completeness_gaps[]` — if any entry has `status: open` → surface each open gap and force a decision before proceeding. Choices per gap: `resolve` / `defer` / `reject` (no silent pass-through).

This is the last gate before commit. Designed to catch lazy auto-approve. Default on empty input is `pause` — laziness leads to safety.

**Step 16b — Commit prompt**

Only after unit tests + API test both green/skipped + clarifications resolved:
> "All tests green. Ready to commit. Proposed message: `<TICKET_ID>: <one-line>`. Files: [list]. Confirm? (y/n)"

After y: stage explicit files only (never `git add -A`), commit. Format: `PROJECT-XXXXX: short description`.

**If n at 16b:** ask: *"What to change? (a) add/remove files, (b) rewrite commit message, (c) abort until next session."* On c → set `phase: blocked`, `blocked_reason: "user declined commit"`, `phase_before_block: api-test`.

### Phase 17 — `pre-push`
Hard stops: FM-SECRETS-IN-DIFF, FM-UNPROTECTED-ENDPOINT.
Warns: FM-MIGRATION-DOWN-EMPTY.
Migration check: if plan mentioned migrations → ask if applied to local DB + tested on staging.

### Phase 18 — `ci-check`
Ask: pass / not applicable / fail. On fail → FM-CI-FAILURE classify code vs env.

### Phase 19 — `invariant-encoded`
Skipped if `invariant-scope` (7) was skipped. Gaps warned, not blocked.

### Phase 20 — `qa-checklist`
Skipped for `refactor`, `hotfix`, `doc-only`, `migration-only`, `spike`.

### Phase 21 — `pr-ready`
**Update cycle handling:** if `state.pr_count > 0` → check if PR already exists for this branch (`gh pr view` or equivalent). If yes → `gh pr edit` to update description, not create. If no (PR was closed/merged) → confirm base branch is current before `gh pr create`.

Show generated PR description → wait for explicit user `y/n` before `gh pr create` / `gh pr edit`.

> **Windows note:** if `gh` not in PATH, fall back: `powershell -Command "& 'C:\Program Files\GitHub CLI\gh.exe' pr create ..."`.

### Phase 22 — `pr-review`
On reviewer comments → invoke `handle-pr-review`:
- SPLIT-REQUEST → write `split-plan.md`, increment `pr_count`, guide split.
- MUST-FIX → write `update-implement.md` → re-run the implementation chain in update mode: phases 9 (`plan`) → 10 (`unit-tests`) → 11 (`implement`) → 12 (`regression`) → 13 (`completeness-audit`) → 14 (`env-gate`) → 15 (`api-test`) → 16 (`commit`) → 17 (`pre-push`) → 18 (`ci-check`) → 19 (`invariant-encoded`).
- NICE-TO-HAVE → offer: (a) address in this PR — add to `update-implement.md`; (b) defer to follow-up ticket — log to `ticket-context.deferred_review_items[]` as `{comment_id, description, status: deferred}`; (c) dismiss with reason logged.
- Re-run pr-description (21) with delta summary. Increment `review_round`.

**Multi-PR base:** `pr_count >= 2` and prior PR merged → rebase on latest main first.

### Phase 23 — `done`
- Worktree cleanup if applicable.
- **DPS session cleanup:** if `ticket-context.dps_session_id` set → *"This ticket originated from DPS session `<session_id>`. Close it now? (y/n)"* → yes: move folder from `open/` to `closed/`, write `## Resolution Summary: resolved via <TICKET_ID>` at top of `investigation.md`.
- Print summary (required structure): (1) ticket ID + PR link, (2) phases completed + any skipped with skip reason, (3) total duration from `run-telemetry.yaml`, (4) any unresolved items — `completeness_gaps[status=deferred]`, `deferred_review_items`, unresolved `requirements-clarifications.yaml` entries. If any unresolved items exist → list them as follow-up actions.

**Post-ticket quality debrief (mandatory — do not skip):**

Ask the user these 3 questions, one at a time. Answers written to `run-telemetry.yaml.quality_signals`. If user says "skip" or gives no answer → write empty arrays and proceed.

> **1. Noise:** Was there any phase where I asked for something I should have already known? (e.g. asked for the base branch, re-read a file already loaded, re-confirmed a decision already made)
> *(one line per item, or "none")*

> **2. Wrong output:** Was there any output you had to manually correct? (plan, requirements, test-cases, PR description, etc.)
> *(one line per item: what file + what was wrong, or "none")*

> **3. Missing:** Was there anything you expected to see in a phase output that wasn't there?
> *(one line per item: which phase + what was missing, or "none")*

After collecting answers → write to `quality_signals` per schema. Then close `run-telemetry.yaml` (set `ended_at`, `duration_seconds`). These signals feed `/learn` → concrete SKILL.md proposals after ≥2 occurrences.

---

## Update cycle

Triggered by `do-ticket <TICKET_ID> update`.

Load `do-ticket-update.md` in full. Key rules: increment `update_count` before any write; write versioned `update-implement-v<N>.md` (never overwrite); pass explicit filename to child skills.

---

## Strategy selection — quick reference

| Phase | Default strategy | Override triggers |
|-------|------------------|-------------------|
| analyze | full-domain-mapping | refactor → behavior-equivalence; bugfix-small → bug-repro-only; cross-service → cross-service-mapping |
| test-cases | exhaustive | hotfix → smoke-only; refactor → behavior-lock; bugfix → regression-focused |
| implement | tdd-strict | hotfix → surgical-patch; cross-service → prototype-then-harden; refactor → refactor-first; risk=critical → paired-with-user |
| api-test | full-learn-then-use | already-cached → use-cached; hotfix → surgical-bugfix-test; doc-only → skip |

Full registries in `<skill>/strategies.yaml`. Selection rules in each registry's `selection_rules:` block.

---

## Failure modes — quick reference

Full registry in `failure-modes.yaml`. Sample matrix:

| Trigger | FM-XX | Pivot |
|---------|-------|-------|
| `git rebase` produces conflicts | FM-REBASE-CONFLICT | block, surface files |
| `BEHIND > 20` commits | FM-LARGE-DIVERGENCE | rebase vs cherry-pick choice |
| 3+ same-root implement failures | FM-3X-SAME-ROOT | switch strategy → domain-deep-dive → ask user |
| HTTP 200 + wrong data | FM-SILENT-API-BUG | return to implement |
| Domain layer importing infra | FM-LAYER-VIOLATION | warn + ack |
| Secrets in staged files | FM-SECRETS-IN-DIFF | HARD STOP |
| Unprotected HTTP endpoint | FM-UNPROTECTED-ENDPOINT | HARD STOP |
| MSB3027 / DLL locked | FM-DLL-LOCKED | ask user close VS+services |
| Plan-changeset drift | FM-PLAN-CHANGESET-DRIFT | ack both lists |
| Files in diff but not plan | FM-PREREQ-MISSING | suggest earliest entry phase |
| Service connection refused | FM-SERVICES-NOT-RUNNING | env-gate |

Unmatched failure → log to `run-telemetry.unknown_failures[]` → /learn proposes new FM-XX after recurrence ≥3.

---

## Human Gates

Phase-specific gates surfaced by individual skills (open questions, risk decisions, edit/proceed). do-ticket-level gates:

| ID | Trigger |
|----|---------|
| G1 | Ambiguous task, open questions, ack required |
| G3 | Irreversible (DB migration, hotfix deploy) |
| G5 | Technical trade-off (stash vs worktree, rebase vs cherry-pick) |
| G6 | Scope larger than understood |
| G7 | Security-sensitive (HARD STOPs) |
| G8 | 3 failures same root cause |
| G10 | Required project field missing |
| G-ENV | Services not running before live test |

All gates: save `phase: blocked`, `blocked_reason`, `phase_before_block`. Resume on next invocation.

---

## Telemetry hook

Every phase write appends to `{output}/tickets/<TICKET_ID>/run-telemetry.yaml`. Schema in `run-telemetry-schema.md`. Captured signals:

- Phase outcomes (success / blocked / skipped / aborted) + duration + iterations
- Strategy used per phase + outcome (success / pivoted / failed)
- Failure modes hit + pivot used + resolution time
- Gates triggered + user choice + duration
- Type promotions + reason
- Update cycles, review rounds
- `unknown_failures[]` — error signatures not in registry (≥3 occurrences → /learn proposes new FM-XX)

`/learn` reads telemetry across all tickets to propose:
- New FM-XX entries (recurring unknown failures)
- Strategy default tuning (low success rate strategies → demote)
- Gate analytics + auto-pivot candidates
- Phase bottleneck detection
- Pattern priority promotions

---

## Rules

- Always read `ticket-state.yaml` AND `ticket-context.yaml` before any action.
- Phase contracts in `phase-contracts.yaml` are authoritative — never duplicate prereq logic in this file.
- Strategy selection runs once per phase entry; cached in `ticket-context.strategies_picked`.
- Strategy can switch mid-phase only via FM-XX pivot; record both in telemetry.
- Never switch git branches destructively without confirmation.
- Never run `git stash pop` automatically.
- Never run `git push` automatically — user always pushes manually.
- Secrets-in-staged-files gate: HARD STOP, no exceptions.
- Each phase completes fully before the next starts.
- **No inline code reads:** do-ticket must never directly Glob or Read source files. All code discovery delegated to `implement-plan` (which uses `{project_docs}/code/domain_index.yaml`) or `implement` (which follows `plan.md` paths). New context mid-ticket → write `update-implement-vN.md` → route to `implement-plan update`.
- Append-only context: child skills never delete or mutate fields they didn't write to `ticket-context.yaml`.
- Telemetry is append-only during the run; closed at `phase: done`.

---

## Known Gotchas

- **Large test file reads:** never `Read` full test files. Grep for signatures first, then targeted `Read` with offset/limit. Files >10000 tokens fail and waste a retry. *(2026-04-14)*
- **Frontmatter drift:** child skill frontmatters use varied formats (some quoted, some block-scalar). Phase contracts live in `phase-contracts.yaml`, not in child frontmatters, to avoid maintenance drift. *(2026-05-02)*
- **Long sessions need RESUME.md:** when a ticket spans multiple sessions (or session approaches context limits), write a comprehensive `RESUME.md` to the ticket folder capturing the **audit trail of design decisions** — not just status. Without it, next-session-Claude has to re-derive every choice. `ticket-state.yaml` captures workflow position; `RESUME.md` captures *why this design*. *(2026-05-05)*
- **Local DB queries via MCP `postgres-local` are valuable for design.** During analyze/plan phases, fetching live config rows (e.g. existing dynamic rule JSON) instantly resolves design questions that would take much longer to derive from code alone. Use sparingly (READ-ONLY, LIMIT 10) but don't shy away from a targeted query. *(2026-05-05)*
