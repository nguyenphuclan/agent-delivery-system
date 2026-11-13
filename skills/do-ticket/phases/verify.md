# do-ticket — verify part

Phase procedure for phases 14 `env-gate`, 15 `api-test`, 15.1 `e2e`, 16 `commit`, 17 `pre-push`. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`ticket-types.md`, `run-telemetry-schema.md`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 14 — `env-gate`
Runs after `completeness-audit` (13), before `api-test` (15).

**HARD PRE-CHECK — Phase 13.5 must have run (do NOT skip):** before listing services, verify
`{ticket_dir}/code-quality-review.md` exists (Phase 13.5 `code-quality-review` produced it), OR the
`ticket_type` explicitly skips 13.5 per `ticket-types.md` (`doc-only`, `spike`, `hotfix`). If it is
missing for a type that requires it → **STOP and run Phase 13.5 now**, before any env-gate / api-test /
commit. The quality gate precedes live testing + commit; skipping it in the rush to api-test/commit is a
recurring miss. Any `must-fix` finding loops to `implement` (11).

**Probe, do not only ask (`liveness_probe`).** A human "yes, it's running" is honest and can still be wrong:
the process may hold a stale DLL, and Phase 15 then tests the OLD code and passes. List the services
`build/run.yaml` names for this ticket (use worktree ports in worktree mode), then:
- For each service with a health/ping endpoint, call it and show the
  result next to the service name. All up → go on; write `env_gate: probed` to telemetry.
- A service that does not answer → ask the user to start it, naming the service and port. Ask only about
  these rows. A probe failure is not a hard block on its own — it means the user's "yes" and the machine
  disagree; ask which is right.
- **Staleness hint:** if the change touched a running service (or the shared library it uses), compare the
  service's start time with the last local build. Started before the build → it serves pre-change code; ask
  the user to restart it (it may be under their debugger).
- No probe possible (no endpoint listed) → fall back to the user's confirmation, plus the reminder:
  *"If you changed code in any running service during implement, restart it now to reload the updated DLL before testing."*

**build/run.yaml missing:** if the artifact is absent (readiness gate 14 not met) → ask user to list required services manually. Do not block the gate entirely — manual confirmation still satisfies the env-gate contract. Log `env_gate_manual: true` to telemetry.

## Phase 15 — `api-test` — **MANDATORY for `crud-feature` and `bugfix-investigated`**
Strategy from your live-API test skill's `strategies.yaml`; cache the pick as `strategies_picked.api-test`. **Test data rule:** before creating fresh data, look for an existing reusable record with your test-data skill (if you have one); only create on `NOT_FOUND`. After a flow produces a reusable entity, register it there.

**Hard ordering rule:** phase 15 (`api-test`) MUST complete (or be explicitly skipped per type definition) BEFORE phase 16 (`commit`) begins. Do not skip to commit even if implement + regression + unit tests all pass — running flows end-to-end against the live stack catches silent bugs that compile-time checks miss. To skip, the user must explicitly say so AND a reason is logged to telemetry.

Skip allowed only when:
- Ticket type explicitly excludes api-test (`bugfix-small` unless API surface, `refactor`, `doc-only`, `migration-only`, `fe-only`, `spike`, `hotfix`)
- User explicitly defers with "skip api-test, deploy first" — logged to `run-telemetry.skipped_phases[]`

Silent bug (200 + wrong data) → FM-SILENT-API-BUG → return to implement.

**Evidence is mandatory — a flow is "verified" only if its request/response is on disk (`evidence_contract`).**
This is a required pre-commit gate, yet it used to conclude on the agent's word with no artefact. Per flow,
into `{ticket_dir}/test-evidence/{flow}/`:

- `01_request.txt` — method, URL, headers (token redacted), body
- `02_response.txt` — HTTP status + full body, headed by three lines: `Expected: …` / `Observed: …` /
  `Entry: <the entry point used>` so the verdict stays checkable later without re-running anything
- `03_db_verify.txt` — the verification query **and its row count**, whenever the flow persists data

**A verification query returning 0 rows is N/A, never PASS.** Zero rows cannot tell "the write
failed" apart from "the query is wrong" — and the second one reads as success, because no bad row
was found. State the expected row count *before* running, then reconcile.

### 15b — Track B: run every case in `test-cases.md`, and record it

API flows alone are not enough: they never read `test-cases.md`, so `[API]` / `[DB]` cases were tied to
nothing, and `[GUI]` cases ran nowhere — AC proof images (Track A) quietly took their place. Now:
- `[API]` / `[DB]` → run each case through the live-API test skill (evidence folder as above, named `tc<NN>-…`).
- `[GUI]` → run each case through your GUI test tool (browser automation, not the AC proof). Save the run folder.
- `[UNIT]` / integration → name the test(s) that cover it (from `unit-tests-written.md`) and the green run.
- `[DOC]` and other tags → the check the case describes, with its output on disk.
- `[E2E]` → Phase 15.1; its row lives in `e2e/e2e-results.md`.

Write `{ticket_dir}/test-evidence/tc-results.md`, one row per case (the latest row per case and env decides):

| TC | Tag | How it ran | Env | Commit | Result |
|---|---|---|---|---|---|
| TC-08 | API | `tc08-create/` (gateway 5002, admin token) | local | `acme-api@0ac8503` | PASS |
| TC-04 | UNIT | `WindowConfigTests.CalculateWindowStart_…` (api run, 23 passed) | local | `acme-api@0ac8503` | PASS |

Results: `PASS` · `FAIL` (Observed ≠ Expected, even by one status code — fix the code or fix the case with the
owner, never re-word the result) · `PARTIAL — <shortcut>` (same rule as 15.1: API instead of GUI, recalc
instead of create, existing data instead of new) · `SKIP — <reason> — approved by <owner>, <date>`. A backticked
path in "How it ran" must exist under `test-evidence/`. An AC image is never a "How it ran".

**Commit** = the code the row ran on: `<repo>@<sha>` (HEAD of each repo under test, at least 7 hex chars; list
every repo the case touched). No code ran (a pure SQL read, a doc check) → `n/a — <reason>`. A PASS with no
Commit blocks. At `pre-commit`, `pre-push` and `pr` the gate finds the repo (ticket-state `worktree_paths`, else
`<repos_root>/<repo>`) and marks the row **stale** when a code commit (not `*.md`) follows that sha on the
ticket branch (else HEAD): run the case again and add a new row. It sees commits only, so after an
uncommitted edit run Track B again before `commit`. (PROJ-11685: 9 rule changes were committed after the
Track B run and the old PASS rows still counted.)

**Gate G-TC (SKILL.md phase list)** blocks `commit` (16) until every case has a row and none is FAIL, PARTIAL,
stale or an unapproved SKIP. Machine check: `check_artifacts.py {ticket_dir} pre-commit` (also `pre-push`, `pr`, `done`).

## Phase 15.1 — `e2e` — the full flow, through the real entry points

Runs the `## E2E track` of `test-cases.md`, case by case, on the local stack (env-gate confirmed). Runs for
every type whose list has `test-cases`. PROJ-11685 had 0 E2E cases: each AC was proven by a shortcut
(rule made through the admin API, an EXISTING record recalculated), each was recorded PASS, and the full flow
— configure in the GUI → create a record → read the stored result — never ran on any environment.

**Run.** Follow each case's entry points in order: GUI steps through your GUI test tool, API create through
the live-API test skill, DB checks read-only. Make the data the case needs through its own entry points; never seed it.

**Record** every run in `{ticket_dir}/test-evidence/e2e/e2e-results.md`, one row per case per env:

| Case | Type | Env | Entry points used | Result | Evidence |
|---|---|---|---|---|---|
| E2E-01 | standard | local | admin GUI → create form → DB | PASS | `e2e/E2E-01-local/` |

**Result values:**
- `PASS` — every entry point named in the case was used, and the check matched.
- `PARTIAL — <shortcut>` — the check matched, but a shortcut was used: API instead of GUI, recalc instead of
  create, an existing record instead of a new one, a rule that matches no record. **PARTIAL is never PASS**, even
  when each shortcut looks valid for its own AC.
- `FAIL` — the check did not match → FM-SILENT-API-BUG → back to `implement`.
- `SKIP — <reason> — approved by <owner>, <date>` — only with the owner's words. An entry the case marks
  `Entry not possible` still needs this approval.

**On TEST (after deploy).** The same cases run again on TEST, with the records approved at `plan`
(`ticket-context.test_env_writes`). Add rows with `Env = test`, then remove the records as the plan says.
No approval on file → ask now, once; a no → `SKIP` rows that need the owner's approved reason.

**Gate G-E2E** (SKILL.md phase list) is checked from this file plus the matrix in `test-cases.md`. Every
in-scope E2E case needs a `PASS` or an approved `SKIP` row for `local` before `pr-ready` (21), and for `test`
too before `done` (23). An AC proof, if your team keeps one, may reuse an E2E run as its image.
Machine check: run `python _shared/tools/check_artifacts.py {ticket_dir} e2e --type <ticket_type>` when 15.1
ends (exit 2 blocks). The same check also runs inside the `pre-commit`, `pre-push`, `pr` and `done` gates; it
is waived only for types with no `test-cases`.

## Phase 16 — `commit`

Runs after phase 15 (`api-test`). Sub-steps in order: 16-0 → pre-check → 16a → 16b.

**Step 16-0 — knowledge checkpoint K3 (write what build and verify taught into the docs).** Follow
`../promote-knowledge.md`. Look back to the last checkpoint: code reads in `implement`, failed live runs in
`api-test`, owner answers. Complete `knowledge_misses[]`, sort any open questions, then for each entry
write, fix or index the doc and set `promoted:`. No owner approval first (AI-first); the writes are listed
in the Phase 23 summary. Skip only for `doc-only`. The pre-check below blocks while an entry has no
`promoted` result, or `knowledge_checkpoints[]` lacks K3 (and K1 for types that run `analyze`).

**HARD PRE-CHECK — run the artifact gate (do NOT skip):**

```bash
python _shared/tools/check_artifacts.py {ticket_dir} pre-commit --type <ticket_type>
```
Exit 2 = BLOCKED; it names each missing or hollow file (`code-quality-review.md`, `plan.md`,
`run-telemetry.yaml`, the Phase 12 `Regression:` line in `implement-summary.md`, `test-evidence`, and
`legacy-contract.md` while gates are armed, the 6c `flow_gate` record, the knowledge checkpoints, and the
test gates G-MATRIX / G-E2E / G-TC — minus what the type skips). A PASS means the record exists,
not that it is right — so still do the `run-telemetry.yaml` read below.

**`run-telemetry.yaml` must exist and hold the required minimum.** Before the commit prompt, open
`{ticket_dir}/run-telemetry.yaml` and check it by hand (if the tool cannot run, also open each other file
listed above and check it exists, is non-empty, and measured something):
- it parses as YAML;
- it holds the **required minimum** subset defined in `run-telemetry-schema.md`: `ticket_id`, `ticket_type`,
  `schema_version`, `started_at`, `phases[]` (non-empty — one entry per phase run so far), and the four lists
  `failure_modes_hit` / `gates_triggered` / `unknown_failures` / `knowledge_misses` — written **explicitly**,
  `[]` included. Before writing `knowledge_misses`, walk `owner_answers` and the run's plan changes: each one
  that gave a system fact is an entry, with `docs_had_it` set by a grep of `{project_docs}`;
- it describes THIS run (the ticket id and the phases match what happened), not a copy from another ticket.

Any check fails → **write or fix it now from the run so far**, before committing. Pass = all three hold.

Why a gate: an audit once found **zero** telemetry files across every past ticket, so `/learn`'s D8
dimension — new FM-XX proposals, strategy tuning, gate analytics, bottleneck detection — had never run once,
even though `phase-contracts.yaml` declares the artifact and `failure-modes.yaml` promises `/learn` reads it.
It was never refused, only never affordable: ~30 fields appended after every phase, with nothing gated on it.
Hence the small required subset and this gate. **A declared artifact that no phase is gated on is an artifact
that will not exist.** `unknown_failures[]` is the highest-value field — an error pattern you had to work
around, that is not in `failure-modes.yaml`, becomes a proposed FM-XX once it recurs across three tickets.
Record it even when you resolved it.

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

## Phase 17 — `pre-push`

**HARD PRE-CHECK — run the artifact gate, do not eyeball it:**

```bash
python _shared/tools/check_artifacts.py {ticket_dir} pre-push --type <ticket_type>
```
Exit 2 = BLOCKED; it names each missing or hollow file. It also catches a file that exists but
measured nothing, and a `.yaml` that does not parse — both of which a plain file-exists test passes.

The tool cannot judge the third point below, so do that one by hand after a PASS. If the tool cannot run,
do all three by hand for each output the type's phases owe (per `phase-contracts.yaml` and `ticket-types.md`):
- the file exists, and a `.yaml` file parses;
- it **measured something**: the scope line is non-zero (tests run, change-types, files reviewed, flows
  with evidence) — a file that exists but measured nothing fails, though a plain file-exists test passes it;
- it describes the change in front of you, not an earlier change on the same ticket.

Any miss → name the missing or hollow file and stop. Pass = every owed file passes all three.

**`code-quality-review.md` must exist before push-code starts.** Phase 13.5 is
supposed to have produced it, but several paths reach 17 without it: a resumed ticket, a
run stopped before implement and continued later, a jump straight to `pre-push`, or a session where the
review happened as chat prose and no file was written. **Prose is not an artifact.** If
`{ticket_dir}/code-quality-review.md` is missing and the type does not skip 13.5 → **go run Phase
13.5 now**, then return here. push-code enforces the same thing in its own review step, so a bypass here is
caught there — but catching it here saves the round trip.

**Delegates to the `push-code` skill** — the standard pre-push gate and the ONLY sanctioned push path. There is no plain `git push` fallback. push-code runs, in order: secrets/auth scan (the old pre-push hard stops FM-SECRETS-IN-DIFF, FM-UNPROTECTED-ENDPOINT, still enforced there) → final diff-scoped review (reuses `code-quality-review.md` §B) → FE-repo review (3b, FE repos only) → local analyzer run (`sonarscanner begin` + `dotnet build` → `Issues.json`; scoped `dotnet-coverage` → `coverage.xml`) → the two local gates (zero Sonar rule issues on new code, coverage on new code ≥ 80%) → push. **Duplication on new code is NOT checked locally** (needs a server upload that a sandboxed host blocks) — it stays with CI at 18.
- Any gate blocks → push-code hands back here; write `update-implement.md` → re-run the implementation chain (11 → 12 → 13 → 13.5) → return to 17. Same loop shape as an env-gate failure.
- Migration check (still owned here): if plan mentioned migrations → ask if applied to local DB + tested on staging. Warn FM-MIGRATION-DOWN-EMPTY.
- Prereq: `projects.<active>.sonar` block + local toolchain (see `push-code/setup.md`). If absent, push-code stops at its own G-CONFIG/G-TOOLCHAIN gate — it does NOT fall through to an ungated push.
- Projects with no `sonar` block never reach the analyzer portion — push-code still runs the review + secrets scan + push.
