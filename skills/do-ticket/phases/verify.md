# do-ticket — verify part

Phase procedure for phases 14 `env-gate`, 15 `api-test`, 16 `commit`, 17 `pre-push`. The router is `../SKILL.md`: trigger, state files, the phase list, the
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
- `02_response.txt` — HTTP status + full body, headed by two lines: `Expected: …` / `Observed: …`
  so the verdict stays checkable later without re-running anything
- `03_db_verify.txt` — the verification query **and its row count**, whenever the flow persists data

**A verification query returning 0 rows is N/A, never PASS.** Zero rows cannot tell "the write
failed" apart from "the query is wrong" — and the second one reads as success, because no bad row
was found. State the expected row count *before* running, then reconcile.

## Phase 16 — `commit`

Runs after phase 15 (`api-test`). Two sub-steps in order: 16a → 16b.

**HARD PRE-CHECK — `run-telemetry.yaml` must exist and hold the required minimum (do NOT skip).** Before the
commit prompt, open `{ticket_dir}/run-telemetry.yaml` and check it by hand:
- it parses as YAML;
- it holds the **required minimum** subset defined in `run-telemetry-schema.md`: `ticket_id`, `ticket_type`,
  `schema_version`, `started_at`, `phases[]` (non-empty — one entry per phase run so far), and the three lists
  `failure_modes_hit` / `gates_triggered` / `unknown_failures` — written **explicitly**, `[]` included;
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

**HARD PRE-CHECK — open the artifacts, do not eyeball the folder.** For each output the type's phases owe
(per `phase-contracts.yaml` and `ticket-types.md`), check by hand:
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
