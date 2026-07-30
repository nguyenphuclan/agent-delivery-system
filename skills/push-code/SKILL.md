---
name: push-code
description: Standard pre-push quality gate — the ONLY sanctioned way to push code. Runs a final diff-scoped code review, then reproduces the CI SonarQube analysis LOCALLY the only way a sandboxed workstation allows — `sonarscanner begin` + `dotnet build` runs the SonarAnalyzer Roslyn analyzers in-process and writes their findings to `.sonarqube/out/*/Issues.json`, and `dotnet-coverage` produces `coverage.xml`; both are parsed off disk (no server upload). Enforces two hard gates on NEW code — zero Sonar rule issues, coverage ≥ 80% — before the branch is pushed. (Duplication-on-new-code needs the server upload, which a restricted-loopback sandbox blocks — see below — so it is deferred to CI.) Purpose: catch what CI's Sonar would catch, but locally, so you never push → wait for CI to go red → fix → re-push. Replaces do-ticket's pre-push/ci-check and every ad-hoc `git push`.
tech_stack: [git, gh-cli, dotnet-sonarscanner, dotnet-coverage, python, roslyn-analyzers]
---

## Pre-flight

**Tier: A** (mutating: `git push`).

Follow `~/.claude/skills/_shared/pre-flight-protocol.md` BEFORE any other action — runs regardless of how this skill was invoked (direct `/push-code`, orchestrator routing, or as do-ticket's push phase).

Skill-specific overrides:
- `requires_project_fields`: [active, output, repos, base_branch]
- `requires_project_config`: `projects.<active>.sonar` block (host, org, token_env, gates, project_key resolution). If absent → **G-CONFIG**: this skill cannot run without it; point to `setup.md` and stop.
- `risk_signals`: [g3 (push is imminent), g7-implied (auth surfaces in diff)]
- `skip_when`: never — the whole point is that nothing pushes without this gate.

**Prerequisite check (runs inside pre-flight, first thing):** verify the toolchain the local path actually uses —
`dotnet-sonarscanner` + `dotnet-coverage` global tools, `python`, the token env var set, and the Sonar server reachable + token valid (`curl -s -u "$TOKEN:" <host>/api/authentication/validate` → `{"valid":true}`; `begin` needs it to fetch the quality profile that configures the analyzers). Any missing → **G-TOOLCHAIN**: print exactly what's missing and point to `setup.md`. Do NOT silently skip the Sonar gate — a skipped gate that reads as green is the one failure mode this skill exists to prevent.
> **No Java needed.** `begin` (a .NET tool) and `build` (Roslyn) never invoke Java; only the server-upload step (`end`) does, and that step is not part of this gate (see below).

---

# push-code — standard pre-push quality gate

## Why this exists

CI runs the SonarQube analysis on every PR with `sonar.qualitygate.wait=true`. The old loop was: commit → push → open PR → wait minutes for CI Sonar → it flags a rule / low new-code coverage → fix → push again → wait again. This skill collapses that loop by producing **the same analyzer findings locally, before the push**, and refusing to push until the new code is clean.

**How the analysis runs locally — and why there is no upload.** `dotnet sonarscanner begin` (pure .NET) downloads the project's quality profile and injects the **SonarAnalyzer Roslyn analyzers** into the build. `dotnet build` then runs those analyzers **in-process** and the scanner writes every finding to `<repo>/.sonarqube/out/*/Issues.json` (SARIF) — this is exactly what CI would surface, sitting on disk *before* any upload. We read it there.

> **The server-upload path is dead on a sandboxed workstation — do not try to use it.** The upload step (`sonarscanner end`) runs a Java "scanner engine" whose `HttpClient` opens an NIO selector loopback self-pipe; a managed-endpoint sandbox with restricted loopback blocks it (`UnixDomainSockets.connect0: Invalid argument`). This fails identically **with the sandbox disabled** and at **every scanner version** (v11 engine and the v9 classic CLI both go through Java HTTP). So there is nothing to upload and nothing to read back over the Web API — the gate is computed **entirely from local files** (`Issues.json` + `coverage.xml`). The local-files path is the one that works there; the whole point of this revision is to stop re-discovering the dead end. (Ref: Claude issue #41432; same root cause as the SonarQube MCP not launching.)

**One rule:** code reaches the remote only through this skill. `do-ticket` calls it at the push phase; standalone `/push-code` is the manual entry point. There is no "just `git push`" path anymore.

## Triggers

- `/push-code`, "push code chuẩn", "push chuẩn", "chạy push-code", "gate rồi push"
- Inside `do-ticket`: phase 17 (`pre-push`) delegates here (see `do-ticket/SKILL.md` phase 17).
- A bare "push" / "commit đi rồi push" in a **code** context (not spec) routes here — see the assistant push-disambiguation rule. Bare `push` with a clean branch → say *"no code changes to push"* (if the project also has a spec-publishing skill, name it here so a bare `push` never silently means "publish the spec"), do not run.

## Pipeline (the contract)

Each step gates the next. A failure never proceeds — it loops back to a fix and re-runs from the failed step.

| # | Step | What it does | Blocks push on |
|---|------|--------------|----------------|
| 0 | **pre-flight** | Project config + `sonar` block + toolchain prereq-check | G-CONFIG, G-TOOLCHAIN |
| 1 | **changeset** | Resolve repos with commits ahead of `base_branch`; compute `git diff <base>...HEAD` per repo. Empty → stop (nothing to push) | — |
| 2 | **secrets-scan** | Secrets / credentials in diff; new/changed endpoints without an auth attribute | FM-SECRETS-IN-DIFF, FM-UNPROTECTED-ENDPOINT |
| 3 | **final-review** | Diff-scoped quality review — **reuse `do-ticket/code-quality-review.md` §B verbatim** (11 dimensions, severity + disposition). This is the "review one more time" pass. | any `must-fix` finding |
| 3b | **fe-review** *(FE repos only)* | Invoke the **FE repo's own `code-review` skill** (`acme-frontend/.claude/skills/code-review`) on the FE diff — it validates against the repo's CLAUDE.md conventions + dispatches its reviewer. Fix every must-fix finding, then **re-run this step** until clean. See `## Frontend repos` below. | any `must-fix` finding |
| 4 | **local-analysis** *(.NET repos)* | Per repo: `begin` + `dotnet build` (analyzers → `.sonarqube/out/*/Issues.json`), then **scoped** `dotnet-coverage` (only the test classes that cover the diff → `coverage.xml`). No `end`, no upload. See `sonar-local-gate.md`. | build/analyzer error → FM-ANALYSIS-FAILED |
| 5 | **local-gate** *(.NET repos)* | Parse the two artifacts and enforce the gates (below): `parse-sonar-issues.py` (rule issues on new lines) + `parse-new-coverage.py` (coverage on new lines) | FM-SONAR-NEWISSUE, FM-COVERAGE-LOW |
| 6 | **push** | All green → confirm once → `git push` (`--force-with-lease` if the branch was rebased). FE PR title follows the `[TASK]` convention (`## Frontend repos`). | — |

Full algorithm for steps 4–5: **`sonar-local-gate.md`**. One-time toolchain + token setup: **`setup.md`**. Failure handling: **`failure-modes.yaml`**.

> **Per-repo shape.** Steps 4–5 are the .NET Sonar gate; FE repos have no local dotnet Sonar (their Sonar new-code%/rule-scan + duplication run in CI), so for an FE repo the gate is: secrets-scan → final-review → **fe-review (3b)** → push. A mixed BE+FE push runs the .NET gate on the BE repo(s) and the fe-review on the FE repo(s).

## The gates (step 5)

Thresholds come from `projects.<active>.sonar.gates`.

| Gate | Source (local file) | Pass condition |
|------|---------------------|----------------|
| **Sonar rule issues on new code** | `.sonarqube/out/*/Issues.json` (SARIF) ∩ diff added lines — via `parse-sonar-issues.py` | **0** `S####` issues on new lines (complexity `S3776`, commented-code `S125`, nested-ternary `S3358`, param-count `S107`, …) |
| **Coverage on new code** | `coverage.xml` ∩ diff added lines (production files) — via `parse-new-coverage.py` | `≥ gates.coverage_new_code_pct_min` (default 80) |

- Issues on **pre-existing** lines in changed files are reported for context but do **not** block (they are not "new code").
- **Duplication on new code** (`gates.duplication_new_code_pct_max`, default 0) can only be computed by the server after upload, which needs the (blocked) server upload → **deferred to CI's PR analysis**. Note this in the gate summary; do not claim it was checked locally.

### Gate summary must carry its scope

Follow `_shared/measurement-integrity-protocol.md`. **A bare `✅ gates green` is rejected output** — every
gate line states the size of what it measured and the summary states what was not examined:

```
Sonar rule issues : 0 on 312 new lines across 14 files   (Issues.json: 4.2 MB, 1 847 issues parsed, 312 lines intersected)
Coverage new code : 87.4% of 289 new production lines    (coverage.xml present, 36 uncovered)
Not examined      : duplication-on-new-code (needs server upload — deferred to CI)
                    pre-existing lines in changed files (context only, non-blocking)
```

**Empty scope is BLOCKED, never green** — and it is the likeliest failure of this pipeline, because
each of these is a silent zero:

| Zero | Usual cause |
|---|---|
| step 1 resolves 0 commits / 0 changed files | wrong `base_branch`, wrong repo dir, already-merged branch |
| diff ∩ new lines = 0 while the diff is non-empty | the diff is all deletions or all non-production files — say so explicitly, don't print `0 issues` |
| `Issues.json` missing or 0 issues across the whole solution | analyzers never ran (build served from cache, wrong `-p:` flags, `begin` step skipped) — see `sonar-local-gate.md` |
| `coverage.xml` missing or 0 total lines | `dotnet-coverage` produced nothing; coverage is then `n/a`, **never** `100%` |

On any of these: report `BLOCKED — measurement failed`, fix the measurement, re-run from step 4. Never
push on a gate that measured nothing.

**Prove the gate once.** A gate that has never gone red is unproven — inject a real violation (an
over-complex method for S3776, ~30 untested new lines for coverage) and confirm RED before trusting it.

## Gate-failure loop (steps 3 / 5)

On any block, do NOT push. Instead:
1. **Itemize** precisely — for a rule: `rule-key · file:line · message` (the parser prints this); for coverage: the new-code % + the uncovered new lines per file (the parser prints this).
2. **Route the fix.** Standalone → present the itemized list and stop for the user to fix (or fix inline if trivial and in scope). Inside `do-ticket` → hand back to the implementation chain (write `update-implement.md` → phases 11→12→13→13.5) exactly as an env-gate failure would.
3. **Re-run from the failed step** after the fix (step 4 if code changed, so the analyzers + coverage re-run; step 5 if you only need to re-parse). Never mark a gate "green with exceptions" without an explicit, logged user override.

## Frontend repos

Extra discipline that applies **only to the frontend repo(s)** in the changeset (repo alias `frontend` / `frontend_admin` — i.e. `acme-frontend`). Never applied to .NET repos.

### fe-review gate (step 3b) — runs before the FE push

Before pushing any FE repo, run that repo's **own** review skill — it encodes the FE conventions (Angular idioms, signals/RxJS, i18n, template a11y, CLAUDE.md rules) that the generic §3 review and the (deferred) CI Sonar don't cover:

1. From the FE worktree, invoke the FE repo's `code-review` skill (`acme-frontend/.claude/skills/code-review`) — e.g. `Skill code-review` while cwd is inside the FE repo, or the repo's `/code-review`. It is **read-only** (never runs build/lint/test — those are this skill's/CI's job) and scopes to the branch's diff / open PR.
2. **Fix every must-fix finding** in the FE code (in scope). Nice-to-have / questions → note, don't block.
3. If any FE code changed, **re-run step 3b** (fresh review) — and, since production code moved, re-run the FE specs before pushing. Loop until the review comes back with no must-fix.
4. Only then proceed to step 6 (push). Never push FE with an unresolved must-fix from its own reviewer.

Standalone → present the findings + fixes to the user. Inside `do-ticket` → route fixes through the implementation chain like any other gate failure.

### FE PR title convention

The FE repo's PR title MUST be exactly:

```
[TASK] PROJ-<number> <short description>
```

- Literal `[TASK]` prefix, **including the square brackets**, then a space.
- The ticket id `PROJ-<number>`, then a space — **no colon** after the ticket.
- Then the short description.
- Example: `[TASK] PROJ-10996 message icon for broken/unknown attachments + case-insensitive image ext`

This pattern is **FE-repo-only**. .NET repos keep their normal `PROJ-<number>: <description>` title (colon, no `[TASK]`). When opening/updating an FE PR (`gh pr create` / `gh pr edit --title`), enforce this exact shape.

## Push discipline (step 6)

- Push only after every gate is green **and** the user has confirmed the push (the skill invocation is the directive when run standalone with an explicit "push"; when called as a do-ticket phase, confirm once: *"All gates green — push `<branch>` to origin? (y/n)"*).
- Rebased/amended branch → `git push --force-with-lease` (never `--force`). `base_branch` / `master` pushes still require explicit confirmation per global git policy.
- After a successful push: standalone → offer `pr-description` / `gh pr create` (FE PR title MUST use the `[TASK] PROJ-<n> …` shape — see `## Frontend repos`). As a do-ticket phase → return control to `pr-ready` (21).
- **CI still gates.** Because duplication isn't checked locally and the server gate never ran, the PR's CI Sonar is still the source of truth — this skill front-loads the two gates it *can* check so the PR rarely bounces, not a replacement for CI.

## Scope & portability

- The skill is a **generic algorithm**. All company data — Sonar host, org, token env-var name, gate thresholds, and how to resolve each repo's Sonar project key — lives in `projects.<active>.sonar`. No host or key is hard-coded here.
- The scan command (exclusions, solution, coverage test command, project key) is **derived from each repo's own Sonar CI workflow** (`.github/workflows/*sonar*.y*ml` or `sonar-project.properties`), not duplicated in config — so it can never drift from what CI runs. See `sonar-local-gate.md` §2.
- The two parsers (`parse-sonar-issues.py`, `parse-new-coverage.py`) are diff-driven and project-agnostic — they take `<repo> <base_ref> [coverage.xml]` and read only local artifacts.
- Projects without a `sonar` block (no SonarQube server in their stack) never reach this skill; their pipelines keep their own push path.
