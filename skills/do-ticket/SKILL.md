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

**Child skills are slots.** The phase table names the skill that fills each slot (`jira-to-requirements`,
`analyze-requirements`, `implement-plan`, `implement`, ...). Where a named skill is not shipped in this repo,
plug in your own skill with the same inputs and outputs — the contract in `phase-contracts.yaml` is what
matters, not the name.

### Companion files

| File | Purpose |
|------|---------|
| `phases/*.md` | The procedure of each phase, one file per part — § Phase files says which to read when |
| `ticket-types.md` | Type matrix: which phases run for each ticket_type |
| `phase-contracts.yaml` | Per-phase inputs/outputs/state writes — replaces static prereq table |
| `failure-modes.yaml` | FM-XX registry — auto-pivots before human gates |
| `ticket-context-schema.md` | Schema for the shared resolved-once context object |
| `run-telemetry-schema.md` | Schema for per-ticket telemetry → /learn auto-improvement |
| `blast-radius.md` | Phase 8.7 — count the legacy surfaces a change touches and arm the gates |
| `legacy-contract.md` | Phases 9.8 (T0) and 12.7 (T1) — the one file a legacy change is approved on, and its re-check |
| `code-quality-review.md` | Phase 9 §A structural gate and Phase 13.5 §B diff-scoped quality review |
| `do-ticket-patterns.md` | Code pattern registry protocol |
| `do-ticket-update.md` | Update cycle protocol, including the replan question |
| `<skill>/strategies.yaml` | Per-skill strategy registry (implement, analyze-requirements, write-test-cases, your live-API test skill) |

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
- `do-ticket PROJECT-1234 D3: use option b` — resume, and change a decision listed at the last `SESSION END` (§ Sessions)

**Auto speed-mode:** If `analyze-requirements` scores requirement clarity < 60/100 (vague verbs, no AC, "just make it work" signals), AI proposes activating self-detailing automatically. User can accept or override.

**Flow gate auto-routing:** Phase 6c (after analyze) checks `{project_docs}/flows/flow_index.yaml` for business flows touched by this ticket (matched by flow keywords + entity references). If a touched flow has `health != ok` OR `known_gates[]` → offers proactive DPS routing BEFORE plan (see Phase 6 step 6c in `phases/analyze.md`). Replaces the old "wait for FM-3X-SAME-ROOT during implement" recovery pattern.

**Worktree trigger detection:** also activate `--worktree` when the user says "separate worktree", "in parallel", "parallel", "isolated stack".

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
worktree_paths: {}            # service-keyed map: { shared_lib, api_service, api_admin, identity, frontend, ... } — keys match projects.yaml repos
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

### `RESUME.md`
Written at each session boundary (§ Sessions) and read by Phase 0. It holds only what lives nowhere else on
disk: the next step, decisions made in chat, things left running or moved, and pending yeses.

---

## Canonical phase enumeration

Reading order = execution order. The numbers below are the **canonical sequence for `crud-feature`** (the fullest flow). Other ticket types skip a subset — see `ticket-types.md` for which phases each type runs.

**Bootstrap (always runs, in this order):**

| # | Phase | What it does |
|---|-------|--------------|
| 0 | `load-state` | Read `ticket-state.yaml` + `ticket-context.yaml` + `RESUME.md`; branch on resume vs fresh |
| 1 | `branch` | Set up git branch (or worktree); verify repo paths |
| 2 | `classify` | Auto-classify `ticket_type` from Jira metadata; user confirms |
| 3 | `resolve-context` | Populate `ticket-context.yaml` with resolved paths + fingerprints |
| 4 | `rebase-check` | (Resume only) Verify branch is not stale vs base |

**Task-flow recall (after phase 3, before `plan`):** Once `ticket_type` + requirement tokens are known, read `{project_docs}/knowledge.md` `## FLOWS` table and match by keywords. This is the **task-sequence flow** track (`flows/flow_*.md` — verified "fastest sequence" recipes written by `/learn` D7), DISTINCT from the business-flow `flow_index.yaml` consumed by the 6c flow-gate. On a match: load the flow file and follow it instead of re-deriving plan/implement from scratch — its `Known pitfalls avoided` + `Known external failure modes` pre-empt the leaks that recur otherwise. If a flow is recalled and the session completes verified (`/learn` Step-1a = "yes"), `/learn` D7 increments that flow's `verified_runs` + bumps confidence — this is how a flow climbs medium → high → proven. Skipping recall is why flows stall at `verified_runs: 1`.

**Work phases (canonical crud-feature order — others skip per `ticket-types.md`):**

| # | Phase | Skill |
|---|-------|-------|
| 5 | `requirements` | jira-to-requirements |
| 5.5 | `enrich` | enrich-requirements (PO-proxy enrichment from project docs; skipped for bugfix-*, hotfix, doc-only, refactor, spike, migration-only) |
| 6 | `analyze` | analyze-requirements (sub-steps: 6a context-expansion → 6b analyze → 6c flow-gate) |
| 7 | `invariant-scope` | invariant-check (--pre) |
| 8 | `test-cases` | write-test-cases |
| 8.7 | `blast-radius` | do-ticket internal (count legacy surfaces, arm gates — see `blast-radius.md`) |
| 9 | `plan` | implement-plan |
| 9.5 | `fe-impact-check` | do-ticket internal (FE contract check scoped by the plan) |
| 9.8 | `legacy-contract` | do-ticket internal (T0 — runs only when gates are armed; see `legacy-contract.md`) |
| 10 | `unit-tests` | write-unit-tests |
| 11 | `implement` | implement |
| 12 | `regression` | do-ticket internal (re-runs the suite; gates on the runner's counts) |
| 12.7 | `contract-recheck` | do-ticket internal (T1 — runs only when gates are armed) |
| 13 | `completeness-audit` | do-ticket internal (per-change-type checklist) |
| 13.5 | `code-quality-review` | do-ticket internal (diff-scoped quality gate — see `code-quality-review.md`) |
| 14 | `env-gate` | do-ticket internal (services-running check) |
| 15 | `api-test` | your live-API test skill |
| 16 | `commit` | do-ticket internal (16a clarification recheck → 16b commit prompt) |
| 17 | `pre-push` | **push-code skill** (standard pre-push gate — final diff review + local analyzer run + 2 new-code gates (0 rule issues, coverage ≥ 80%) + push). Replaces the old internal secrets-scan-only pre-push. |
| 18 | `ci-check` | do-ticket internal — Sonar rules + new-code coverage already gated locally at 17, but CI remains the ONLY check for duplication-on-new-code, CONDITION coverage + the server quality gate. |
| 19 | `invariant-encoded` | invariant-check (--post) |
| 20 | `qa-checklist` | qa-checklist |
| 21 | `pr-ready` | pr-description |
| 22 | `pr-review` | handle-pr-review |
| 23 | `done` | do-ticket internal (close telemetry) |

**Hard ordering invariants** (cannot be reordered regardless of ticket type):
- `blast-radius` (8.7) must exist before `plan` (9) is written
- `implement` (11) may not start while `armed_gates` is non-empty and `contract_approved_at` is unset (9.8)
- `regression` (12) must complete before `commit` (16)
- `code-quality-review` (13.5) must complete (or be skipped per type) before `commit` (16); any `must-fix` open → loop to `implement` (11), not proceed
- `api-test` (15) must complete or be explicitly skipped before `commit` (16)
- `commit` (16) must complete before `pre-push` (17)
- `pr-ready` (21) requires explicit user `y/n` before `gh pr create`

When this file references "phase N" it means the table above. When it references a phase by name (e.g. `commit phase`), the same. Numbered sub-steps inside a phase use letters: `16a`, `16b`.

---

## Phase files — read only the one for the part you are in

This file is the router. The procedure of each phase lives in `phases/`. **Read a part's file when the run
enters that part. Never read the files of later parts ahead of time**, and never read the whole folder.

| Part | Phases | File |
|---|---|---|
| start | 0 `load-state`, 1 `branch`, 2 `classify`, 3 `resolve-context`, 4 `rebase-check` | `phases/start.md` — **every invocation** |
| analyze | 5 `requirements`, 5.5 `enrich`, 6 `analyze` (6a, 6b, 6c flow gate) | `phases/analyze.md` |
| design | 7 `invariant-scope`, 8 `test-cases`, 8.7 `blast-radius`, 9 `plan`, 9.5 `fe-impact-check`, 9.8 `legacy-contract` | `phases/design.md` |
| build | 10 `unit-tests`, 11 `implement`, 12 `regression`, 12.7 `contract-recheck`, 13 `completeness-audit`, 13.5 `code-quality-review` | `phases/build.md` |
| verify | 14 `env-gate`, 15 `api-test`, 16 `commit`, 17 `pre-push` | `phases/verify.md` |
| ship | 18 `ci-check` … 23 `done` | `phases/ship.md` |
| any | an inserted ad-hoc phase | `phases/adhoc.md` |

A resume reads `phases/start.md`, then only the file of the next phase to run.

---

## Ad-hoc phase escape hatch

The phase list of a type is the default path, not a cage. You may insert a whitelisted ad-hoc phase between
two regular phases: `quick-api-poke`, `consult-dps`, `read-reference-feature`, `verify-domain-rule`,
`quick-db-query`, `consult-runbook`. **Read `phases/adhoc.md` before you insert one** — it holds the
declare and finish lines and the log format.

Hard rules, always on: an ad-hoc phase never bypasses `secrets-scan`, `pre-push`, the `commit` user gate or
any G3/G7 gate; it never writes code; at most 3 per regular phase.

---

## Phase loop (generic)

For each phase in the type's phase list (from `ticket-types.md`):

0. **D1 skip check (resume only — bootstrap phases 0–3 exempt):**
   - If `state.last_completed_phase >= <this_phase>` AND all input fingerprints unchanged → skip this phase.
   - Append `{phase: "<name>", completed_at: <ISO8601>, action: "skipped-d1"}` to `phases_run[]` and proceed.

1. **Pre-phase:**
   - First phase of a part in this session → read that part's file (§ Phase files).
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
   - Fingerprint the outputs: write the SHA-256 of each output file to `ticket-context.fingerprints`, with a
     short reason (`<phase> output`).
   - **Editing an artifact after its phase has ended** (a decision written into `plan.md`, a step removed from
     `test-cases.md`) is the same step: refresh that file's fingerprint in the SAME turn, and add a note
     `# refreshed <date>: <reason>` on its line. Without it the next resume reads a correct, deliberate edit as
     drift and asks to regenerate it (PROJ-11212: 4 false prompts). The note lets a resume tell an edit from drift.
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

6. **Session boundary:** the phase just saved is a fixed boundary in § Sessions, or the size check there fires
   → end the session there.

---

## Sessions — end the session at fixed points

**Why.** The main session re-reads its whole context on every turn. Phase files, tool output and diffs from an
earlier part stay in that context, so a long session makes every later step cost more — splitting the files
alone saves little. A fresh session starts with only this router, `phases/start.md` and the next part's file.
Resume is already exact: `ticket-state.yaml`, `ticket-context.yaml` and the artifacts on disk, and Phase 0
picks up at the next phase.

| Boundary | End the session after | Skipped for |
|---|---|---|
| **S1** | the design part — the last of 9 / 9.5 / 9.8 the type runs, with its gate passed, just before the first build phase (10 or 11) | `bugfix-small`, `hotfix`, `doc-only` (lite plan — the session is short anyway) |
| **S2** | `pre-push` (17) — the push is done and CI needs minutes anyway | none |
| **S3** | each `pr-review` (22) round — the next round runs as `do-ticket <TICKET_ID> pr-review` | none |
| **SZ** | any phase, when the size check below fires | none |

**Size check (SZ) — after every saved phase.** If your client shows how much context the session uses, read
it. About **400k** tokens or more → this phase is a boundary. No way to read it → skip the check; S1–S3 still
apply. 400k is a start value: a fresh session already holds 90–200k, and long single-session tickets were
measured at a 555–573k median. Tune it from your own runs.

**At a boundary — the user opens the new session; you make it ready:**
1. State is already saved by the phase loop. Write `{ticket_dir}/RESUME.md` for the next session — only what
   lives nowhere else on disk (what `plan.md` or `ticket-context.decisions[]` holds is not copied):
   - **Next** — the phase that runs next and its first concrete step.
   - **Decided in chat** — each decision and its reason.
   - **Left running or moved** — background servers, a local stack, files moved aside, a branch switched in a
     repo outside the ticket. Stop what you can; list the rest with how to undo it (PROJ-11212 moved two
     migration files to a scratch folder — a new session that does not know breaks the DB).
   - **Waiting for the user** — each pending yes.
2. Append `{id: S1|S2|S3|SZ, after_phase: <phase>, context_k: <tokens used / 1000, or null>, action: ended}` to
   `run-telemetry.yaml.session_boundaries[]`.
3. Print, then stop — do not start the next phase:
   ```
   SESSION END — <TICKET_ID> after <phase> (<S1|S2|S3|SZ>, context <N>k)
   Done: <at most 3 lines — what is on disk>
   Handoff: RESUME.md — <one line: what it says the next session must know>
   This session stays in your history; reopen it to look something up.

   Check before the next part — decided without you since the last boundary:
   - <D-id> <the decision in one line> — <the reason> (<file where it is written>)
   - Open choice: <question> — options <a / b>, recommended <x>
   (none) when the list is empty.

   Open a NEW session in <the folder this session runs in> and paste:
   /do-ticket <TICKET_ID>
   To change a decision, add it after the command, e.g.  /do-ticket <TICKET_ID> D3: use option b
   ```
   The list holds every `ticket-context.decisions[]` entry the agent settled on its own (auto-proceed, a
   recommendation taken) and every open choice collected, since the previous boundary. At **S1** this is the
   user's cheap look at the design before any code exists. Never skip it at S1.
   A change given with the command is a design change: the new session takes it through the replan question
   (`do-ticket-update.md`) and re-runs `plan` before build.

The boundary is not a question — never ask whether to end. If the user then says to go on in this session,
go on: it is their call. Log the entry with `action: continued`.

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
| A gate that measured nothing and reported success | FM-EMPTY-MEASUREMENT | N/A, never pass — show the raw output |
| Domain layer importing infra | FM-LAYER-VIOLATION | warn + ack |
| Code-quality review found must-fix | FM-QUALITY-MUST-FIX | loop to implement, re-run 12/13/13.5 |
| Secrets in staged files | FM-SECRETS-IN-DIFF | HARD STOP |
| Unprotected HTTP endpoint | FM-UNPROTECTED-ENDPOINT | HARD STOP |
| MSB3027 / DLL locked | FM-DLL-LOCKED | ask user close VS+services |
| Plan-changeset drift | FM-PLAN-CHANGESET-DRIFT | ack both lists |
| Files in diff but not plan | FM-PREREQ-MISSING | suggest earliest entry phase |
| Service connection refused | FM-SERVICES-NOT-RUNNING | env-gate |
| Local Sonar gate green, CI Sonar red | FM-SONAR-LOCAL-CI-DIVERGE | ask the server what it counts, add the missing tests |

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
| G-T0 | Legacy contract approval (Phase 9.8) — only when gates are armed at 8.7 |

All gates: save `phase: blocked`, `blocked_reason`, `phase_before_block`. Resume on next invocation.

### Decision modes — what each decision owes

Every non-trivial decision in `plan.md` carries a `mode` in `ticket-context.decisions[]`
(`ticket-context-schema.md`). The mode is a router, not a label: it records what the agent owed.

| Mode | Meaning | Carries |
|---|---|---|
| `M1` | Code, docs or data can settle it — run the command, do not ask | the command that settled it |
| `M2-open` | A real choice between valid designs, or a number only the business owns | `options_count` (≥ 2, each explained, one recommended) |
| `M2-absolute` | An outside constraint (contract, standard, platform limit) | `source`, `revisit_when` |
| `M3` | Solved together with the user over rounds | `rounds` that each carried a **new code fact** |

Checked at Phase 9 exit and again at G-T0 (`phases/design.md`).

---

## Telemetry hook

Every phase write appends to `{output}/tickets/<TICKET_ID>/run-telemetry.yaml`. Schema in `run-telemetry-schema.md`. Captured signals:

- Phase outcomes (success / blocked / skipped / aborted) + duration + iterations
- Strategy used per phase + outcome (success / pivoted / failed)
- Failure modes hit + pivot used + resolution time
- Gates triggered + user choice + duration
- Type promotions + reason
- Session boundaries (`session_boundaries[]`)
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
- **A PASS is only as good as what it measured.** Every gate that prints a verdict also prints its scope (tests run, files reviewed, rows returned). Zero measured is N/A, never PASS (FM-EMPTY-MEASUREMENT).

---

## Known Gotchas

- **For an iterative test-fix LOOP, ask once for the VS debugger to stay STOPPED for the WHOLE phase —
  do not stop-start per iteration.** The existing post-implement reminder (FM-DLL-LOCKED) covers a
  single build. It does not cover a loop: one session hit 3+ lock/unlock cycles, and an aborted locked
  build then left a stale shared-library `bin` folder that failed the next restore with NU5026. Batch the
  builds, ask once. *(2026-04-22 / 2026-06-03 / 2026-07-02 / 2026-07-10)*
- **A file-exists check is not a gate.** An artifact can exist, parse, and still describe nothing — empty
  phase lists, a scope number quoted from another section, or a review left over from an earlier change on
  the same ticket. At every HARD PRE-CHECK, **open the artifact and check it describes the change in front of
  you.**
- **Large test file reads:** never `Read` full test files. Grep for signatures first, then targeted `Read` with offset/limit. Files >10000 tokens fail and waste a retry. *(2026-04-14)*
- **Frontmatter drift:** child skill frontmatters use varied formats (some quoted, some block-scalar). Phase contracts live in `phase-contracts.yaml`, not in child frontmatters, to avoid maintenance drift. *(2026-05-02)*
- **Long sessions need RESUME.md:** when a ticket spans multiple sessions (or session approaches context limits), write `RESUME.md` to the ticket folder capturing the **audit trail of design decisions** — not just status. Without it, next-session-Claude has to re-derive every choice. `ticket-state.yaml` captures workflow position; `RESUME.md` captures *why this design*. § Sessions sets the fixed points. *(2026-05-05)*
- **Local DB queries via MCP `postgres-local` are valuable for design.** During analyze/plan phases, fetching live config rows (e.g. existing dynamic rule JSON) instantly resolves design questions that would take much longer to derive from code alone. Use sparingly (READ-ONLY, LIMIT 10) but don't shy away from a targeted query. *(2026-05-05)*
- **Signature-refactor test sweep (before declaring green):** when a method's signature changes (param type or an added param), the "update broken tests" step must cover TWO blind spots a direct call-site grep misses, or CI goes red after a local "green": (1) **reflection / string-name callers** — grep the method NAME as a string literal (e.g. a private-method invoke helper passing the old argument); these fail at RUNTIME (a type-conversion error), not at compile, so a build won't catch them. (2) **DB-integration test classes** (e.g. Testcontainers-backed `[TestCategory]` DB tests) that a local unit-only `--filter` run skips — they run only in CI. If your stack can spin the DB up locally, run the impacted DB classes before declaring green (it takes seconds). *(2026-06-18)*
