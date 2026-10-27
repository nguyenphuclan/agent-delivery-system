---
name: push-code
description: >
  Standard pre-push quality gate — the ONLY sanctioned way to push code. Runs a final diff-scoped code review, then reproduces the CI SonarQube analysis LOCALLY the only way a sandboxed workstation allows — `sonarscanner begin` + `dotnet build` runs the SonarAnalyzer Roslyn analyzers in-process and writes their findings to `.sonarqube/out/*/Issues.json`, and `dotnet-coverage` produces `coverage.xml`; both are parsed off disk (no server upload). Enforces two hard gates on NEW code — zero Sonar rule issues, coverage ≥ 80% — before the branch is pushed. (Duplication-on-new-code needs the server upload, which a restricted-loopback sandbox blocks — see below — so it is deferred to CI.) Purpose: catch what CI's Sonar would catch, but locally, so you never push → wait for CI to go red → fix → re-push. Replaces do-ticket's pre-push/ci-check and every ad-hoc `git push`.
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

**Also check the ACTIVE `gh` account matches the repo's owner** — `gh auth status`, before any `gh pr` / `gh run` / `gh api` in this skill or the PR step after it. When more than one `gh` account is logged in, work on another repo can leave the wrong one active. With the wrong one, every call on an org repo returns **404 / "Could not resolve to a Repository"**, which reads like missing access and is not. It has led to CI logs being read and a PR being opened by hand through the browser, where the tooling could no longer track it. Wrong account → `gh auth switch -u <account>` first (`projects.<active>` can name the right one).
> **No Java needed.** `begin` (a .NET tool) and `build` (Roslyn) never invoke Java; only the server-upload step (`end`) does, and that step is not part of this gate (see below).

---

# push-code — standard pre-push quality gate

## Why this exists

CI runs the SonarQube analysis on every PR with `sonar.qualitygate.wait=true`. The old loop was: commit → push → open PR → wait minutes for CI Sonar → it flags a rule / low new-code coverage → fix → push again → wait again. This skill collapses that loop by producing **the same analyzer findings locally, before the push**, and refusing to push until the new code is clean.

**How the analysis runs locally — and why there is no upload.** `dotnet sonarscanner begin` (pure .NET) downloads the project's quality profile and injects the **SonarAnalyzer Roslyn analyzers** into the build. `dotnet build` then runs those analyzers **in-process** and the scanner writes every finding to `<repo>/.sonarqube/out/*/Issues.json` (SARIF) — this is exactly what CI would surface, sitting on disk *before* any upload. We read it there.

> **The server-upload path is dead on a sandboxed workstation — do not try to use it.** The upload step (`sonarscanner end`) runs a Java "scanner engine" whose `HttpClient` opens an NIO selector loopback self-pipe; a managed-endpoint sandbox with restricted loopback blocks it (`UnixDomainSockets.connect0: Invalid argument`). This fails identically **with the sandbox disabled** and at **every scanner version** (v11 engine and the v9 classic CLI both go through Java HTTP). So there is nothing to upload and nothing to read back over the Web API — the gate is computed **entirely from local files** (`Issues.json` + `coverage.xml`). The local-files path is the one that works there; the whole point of this revision is to stop re-discovering the dead end. (Ref: Claude issue #41432; same root cause as the SonarQube MCP not launching.)

**One rule:** code reaches the remote only through this skill. `do-ticket` calls it at the push phase; standalone `/push-code` is the manual entry point. There is no "just `git push`" path anymore.

## Triggers

- `/push-code`, "push code", "run push-code", "gate then push"
- Inside `do-ticket`: phase 17 (`pre-push`) delegates here (see `do-ticket/SKILL.md` phase 17).
- A bare "push" / "commit then push" in a **code** context (not spec) routes here. Bare `push` with a clean branch → say *"no code changes to push"* (if the project also has a spec-publishing skill, name it here so a bare `push` never silently means "publish the spec"), do not run.

## Pipeline (the contract)

Each step gates the next. A failure never proceeds — it loops back to a fix and re-runs from the failed step.

| # | Step | What it does | Blocks push on |
|---|------|--------------|----------------|
| 0 | **pre-flight** | Project config + `sonar` block + toolchain prereq-check | G-CONFIG, G-TOOLCHAIN |
| 1 | **changeset** | **`git fetch origin <base>` FIRST**, then resolve repos with commits ahead of `base_branch`; compute `git diff <base>...HEAD` per repo. Empty → stop (nothing to push). Also run the **already-merged check** below. | FM-STALE-BASE |
| 2 | **secrets-scan** | Secrets / credentials in diff; new/changed endpoints without an auth attribute | FM-SECRETS-IN-DIFF, FM-UNPROTECTED-ENDPOINT |
| 2b | **review-ran check** | **Verify the quality review actually RAN and left its artifact for THIS diff.** Not "did I think about quality" — the file must exist on disk. See below. | G-REVIEW-MISSING |
| 3 | **final-review** | Diff-scoped quality review — **reuse `do-ticket/code-quality-review.md` §B verbatim** (29 dimensions in 11 groups, severity + disposition). This is the "review one more time" pass. | any `must-fix` finding |
| 3b | **fe-review** *(FE repos only)* | Invoke the **FE repo's own `code-review` skill** (`acme-frontend/.claude/skills/code-review`) on the FE diff — it validates against the repo's CLAUDE.md conventions + dispatches its reviewer. Fix every must-fix finding, then **re-run this step** until clean. See `## Frontend repos` below. | any `must-fix` finding |
| 4 | **local-analysis** *(.NET repos)* | Per repo: `begin` + `dotnet build` (analyzers → `.sonarqube/out/*/Issues.json`), then **scoped** `dotnet-coverage` (only the test classes that cover the diff → `coverage.xml`). No `end`, no upload. See `sonar-local-gate.md`. | build/analyzer error → FM-ANALYSIS-FAILED |
| 5 | **local-gate** *(.NET repos)* | Parse the two artifacts and enforce the gates (below): `parse-sonar-issues.py` (rule issues on new lines) + `parse-new-coverage.py` (coverage on new lines) | FM-SONAR-NEWISSUE, FM-COVERAGE-LOW |
| 6 | **push** | All green → confirm once → `git push` (`--force-with-lease` if the branch was rebased). FE PR title follows the `[TASK]` convention (`## Frontend repos`). | — |

### Step 2b — G-REVIEW-MISSING: the review must have RUN, not merely been intended

**Do this before step 3, and never skip it because the code "looks reviewed".**

The quality review is a do-ticket phase (13.5) that some pushes reach by a path which never ran it —
a standalone `/push-code`, a resumed ticket, a hotfix branch, or a session where the review happened
as chat prose and no artifact was written. Prose is not an artifact. A review nobody can find later
did not happen.

**The manual check — open the file, do not recall it.** In the ticket's output folder, find
`code-quality-review.md` and verify all four:

1. The file **exists**.
2. It is **newer than the last commit** on the branch (file time after `git log -1 --format=%ci HEAD`).
   A review written before the last commit did not read that commit.
3. Its scope line names a **non-zero** file count and added-line count.
4. Its scope line names the **base ref / sha it reviewed**, and that matches the current `git diff <base>...HEAD`.

| Result | Action |
|---|---|
| all four hold | **RAN** → proceed to step 3 |
| file exists with real scope, but names a **different** base/commit, names none, or is older than the last commit | **STALE, not clean** → the review covered another change on this ticket. Review THIS diff and append a new dated section. A second change on one ticket inherits the first one's tick otherwise |
| file exists but its scope line says 0 files or 0 added lines | **HOLLOW, not clean** → re-resolve the base and the repo dir, then re-run the review. A review of an empty diff prints the same ✅ as a review of forty files |
| file missing | **G-REVIEW-MISSING → run the review NOW**, before anything else. Invoke `do-ticket` phase 13.5 (`code-quality-review.md` §B) on this diff, write the artifact, resolve every `must-fix`, and only then continue |
| no ticket dir at all (non-ticket push) | Run the review inline per §B and write `code-quality-review.md` beside the branch's notes. Still no push without the artifact |
| `ticket_type` ∈ `doc-only`, `spike`, `hotfix` | Genuinely skipped by type — record `skipped-by-type: <type>` in the push report, do not invent a review |

**Write the base ref INTO the review artifact.** Every review section starts with a scope line, and that
line must name the base it measured against (`git diff <base>...HEAD`, base at `<sha>`) plus the file and
added-line counts. Without it the check can only prove *a* review exists on this ticket, not that it read
*this* change — observed 2026-09-18 on PROJ-11372, where a second, different change on the same ticket
passed on the first change's artifact (scope 800 lines, a design that had since been replaced). It was
caught by reading, not by the check.

**Write that scope as a SENTENCE, not a table.** Counts that live only in table cells carry their unit in
the column header, so a reader (or any script) that looks for `<number> <unit>` sees bare numbers and
calls a real review hollow. A line like this reads fine to a human and to a tool:

> Reviewed `git diff origin/master...HEAD` across 2 repos: **4 files** and **384 added lines**
> (310 added lines in `<repo-a>` against base `<sha>`, 74 in `<repo-b>` against base `<sha>`).

Keep any table you like *underneath* it; the sentence is what the check reads.

**Any `must-fix` still open in that artifact blocks the push** exactly as a step-3 finding does: loop
to implement → regression → re-review, then return here.

**Why this check exists.** Steps 4 and 5 measure Sonar rules and coverage — machine checks. They pass
happily on code no human or agent ever read for shape, reuse, or a swallowed exception. Ordering the
review after them would let a green Sonar run stand in for a review it cannot replace. Observed
2026-08-27 on PROJ-7251: **three** declared artifacts were absent — `code-quality-review.md` at
commit-ready, `implement-summary.md` when `pr-description` asked for it, and the run telemetry never
written at all. A rule written only in prose did not bind; a numbered step with its own block id does.

### Step 1 — the already-merged check (do this before anything is measured or pushed)

A **stale `origin/<base>` ref makes every later number wrong**, and the cheapest way to get one is to skip
the fetch. Worse, a **squash-merged** branch keeps commits with fresh SHAs, so it still reports as "N commits
ahead" long after its content landed on the base. Commit count is not evidence. → **FM-STALE-BASE**.

```
git fetch origin <base>                                   # never trust the cached ref
git diff origin/<base>..HEAD --stat                       # CONTENT, not commit count
gh pr list --state all --search "<TICKET>"                # is a PR for this branch already MERGED?
```

- **Foreign commits — check before opening or updating any PR.** `git log origin/<base>..HEAD --oneline`
  must contain only THIS ticket's commits. Cutting a branch with `git checkout -b <TICKET>` while standing
  on another ticket's branch silently inherits its work, and the PR then ships two tickets while its
  description names one. Observed 2026-08-28 (PROJ-9449 carried a PROJ-11332 commit that was not on
  master; the reviewer blocked approval on it). Cut from a freshly-fetched base instead —
  `git checkout -b <TICKET> origin/<base>` — and if a foreign commit is already there, say so and let the
  user choose: split it out, or widen the PR description to name both tickets.
- Content diff empty (or empty for every production file) → **the work is already on the base.** Do not
  open a PR from this branch: GitHub diffs against the older merge-base, so the PR re-shows already-merged
  files and reads as if it reverts or duplicates them. Cut a fresh branch from the refreshed base, move
  across only what is genuinely new, and push that.
- Branch also **behind** the base by unrelated files → say so with the count. Merging it would be noisy.

Related: to answer "is this branch pushed?", use `git rev-parse --verify origin/<branch>` — it fails loudly
on a missing ref. `git log origin/<branch>..HEAD` prints nothing **both** when the branch is in sync and when
the remote ref does not exist, so it cannot tell those two apart.

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

**The scope must name its UNIT, and the per-file lines are the ones that matter.** A total that clears
80% can still be a red CI gate, because the two sides count different things: this gate counts **physical
added lines** from the diff, while Sonar counts **statements** (`new_lines_to_cover`). A line added inside
an existing statement — a field in an object initializer, a wrapped argument, a continuation — is not new
code to Sonar at all. Observed 2026-08-28 on PROJ-9449: local read **91.3% (21/23) and passed**; Sonar
read **0.0%** and blocked the merge, because 21 of those 23 lines were initializer fields Sonar ignores and
the only genuinely-new statement (one `else if` + `throw`) was uncovered. So:

- **Read the per-file lines, never only the total.** Any file showing `0/N` or a partial is a candidate CI
  blocker even when the total clears the threshold — Sonar's denominator may be *that file alone*.
- **Every brand-new statement needs a test** (an `if`/`else if`, a `throw`, a new method). Added fields and
  wrapped arguments will not carry it for you.
- **Sonar also counts CONDITIONS; this gate does not.** Every `?.`, `??`, `&&`, `||` and ternary on a new line adds
  branches to Sonar's new-code coverage. PROJ-11212: local 18/21 lines = 85.7% passed, CI read 70.7% because 16
  of 38 conditions were never taken. For each new line with `?.`/`??`/ternary, test both sides (null and not null).
- **Editing a line makes it new code too.** Refactoring call sites to reach a testable shape can *add*
  uncovered new lines and leave the gate worse than before. Prefer a change that keeps existing call sites
  byte-identical.
- **When CI blocks and local was green, ask the server before touching code** — it names the file and the
  count (all three need `&pullRequest=<n>`, or you silently read the main branch):
  ```
  curl -s -u "$SONAR_TOKEN:" "$HOST/api/qualitygates/project_status?projectKey=$K&pullRequest=$PR"
  curl -s -u "$SONAR_TOKEN:" "$HOST/api/measures/component_tree?component=$K&pullRequest=$PR&metricKeys=new_lines_to_cover,new_uncovered_lines&qualifiers=FIL"
  curl -s -u "$SONAR_TOKEN:" "$HOST/api/sources/lines?key=$K:<path>&pullRequest=$PR&from=A&to=B"
  ```
  `new_coverage = 0.0` alongside a successful coverage import means the new statements are uncovered — not
  that the report failed to upload.

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

Both parsers enforce this in code: **exit 2 = BLOCKED**, distinct from 1 (real finding) and 0 (clean).
Exit 2 goes to a measurement fix and a re-run from step 4 — **never into the implementation chain**,
because there is no defect to fix. See `sonar-local-gate.md` §4 for the full exit-code table.

**Prove the gate once.** A gate that has never gone red is unproven — inject a real violation (an
over-complex method for S3776, ~30 untested new lines for coverage) and confirm RED before trusting it.
*Done 2026-07-30:* all four blocked cases previously returned **0 with `0 issues` / `0/0 = 100.0%`**;
they now return 2, while a seeded issue on an added line still returns 1 and one on a pre-existing line
still returns 0. The gate has been red, and is still green for the right reasons.

## Gate-failure loop (steps 3 / 5)

On any block, do NOT push. Instead:
1. **Itemize** precisely — for a rule: `rule-key · file:line · message` (the parser prints this); for coverage: the new-code % + the uncovered new lines per file (the parser prints this).
2. **Route the fix.** Standalone → present the itemized list and stop for the user to fix (or fix inline if trivial and in scope). Inside `do-ticket` → hand back to the implementation chain (write `update-implement.md` → phases 11→12→13→13.5) exactly as an env-gate failure would.
3. **Re-run from the failed step** after the fix (step 4 if code changed, so the analyzers + coverage re-run; step 5 if you only need to re-parse). Never mark a gate "green with exceptions" without an explicit, logged user override.

**A failed build and a good build write into the SAME `.sonarqube/out`.** A parse taken after a dead
attempt carried ~10k `CS0234`/`CS0246` from that attempt and reported them as findings in the changed
file. `begin` does clear `out`, but only when it runs again — and `Remove-Item .sonarqube -Recurse` fails
on locked `bin/*.dll` while still looking like it worked. So: re-run `begin`, then exactly ONE build, and
**assert zero compile-error rule ids in `Issues.json` before parsing**. Compile errors in the SARIF mean
the artifact is from a broken build, not that the code has findings.

**Two self-inflicted reds, both seen twice in one session (PROJ-11255) — check these before hunting a real finding.**

- **`CS1573` — an XML `<param>` tag is all-or-nothing.** Adding a tag for ONE parameter makes the
  compiler demand one for EVERY parameter of that member, and Gate 1 counts each missing tag as a
  new-line issue (6 the first time, 1 the second). Either document every parameter, or put the note
  in `<summary>` / `<remarks>` instead. The mirror case is `CS1572`: a `<param>` for a parameter that
  no longer exists.
- **A whole-file diff means the tool rewrote the bytes, not the code.** If a 2-line edit shows ~300
  changed lines, look at the writer, not the code. Two known causes, both from patching with python:
  omitting `newline=""` on the WRITE re-translates every CRLF into CR-CR-LF, and `utf-8-sig` on the
  write ADDS a BOM. Either one makes the compiler report XML or parse errors on lines that hold no
  comment at all, so the reported line number points nowhere near the real edit. Check
  `git diff --stat -- <file>` and `head -c 3 <file> | xxd -p` against the base BEFORE re-reading the
  finding.

## Frontend repos

Extra discipline that applies **only to the frontend repo(s)** in the changeset (repo alias `frontend` / `frontend_admin` — i.e. `acme-frontend`). Never applied to .NET repos.

### fe-review gate (step 3b) — runs before the FE push

Before pushing any FE repo, run that repo's **own** review skill — it encodes the FE conventions (Angular idioms, signals/RxJS, i18n, template a11y, CLAUDE.md rules) that the generic §3 review and the (deferred) CI Sonar don't cover:

1. From the FE worktree, invoke the FE repo's `code-review` skill (`acme-frontend/.claude/skills/code-review`) — e.g. `Skill code-review` while cwd is inside the FE repo, or the repo's `/code-review`. It is **read-only** (never runs build/lint/test — those are this skill's/CI's job) and scopes to the branch's diff / open PR.
2. **Fix every must-fix finding** in the FE code (in scope). Nice-to-have / questions → note, don't block.
3. If any FE code changed, **re-run step 3b** (fresh review) — and, since production code moved, re-run the FE specs before pushing. Loop until the review comes back with no must-fix.
4. Only then proceed to step 6 (push). Never push FE with an unresolved must-fix from its own reviewer.

Standalone → present the findings + fixes to the user. Inside `do-ticket` → route fixes through the implementation chain like any other gate failure.

**Run the layers as DIRECT agents from the orchestrator — never one agent that fans out again.** The FE skill asks for a
fan-out (one agent per layer / per rule). Given to ONE background agent, that agent started 13 sub-agents and was cut off
5 times, each time handing back a partial list (PROJ-11212). What worked: the orchestrator itself started 2
agents — Layer 2 (the FE repo's `.claude/agents/code-review-structural.md`) and Layer 3 (`code-review-custom-rules.md`, all
matching rule files in one agent) — each told "do the work yourself, no sub-agents". Layer 1 can run inline. A partial
report is not a review: re-run the missing layers before pushing.

### FE PR title convention

The FE repo's PR title MUST be exactly:

```
[TASK] PROJ-<number> <short description>
```

- Literal `[TASK]` prefix, **including the square brackets**, then a space.
- The ticket id `PROJ-<number>`, then a space — **no colon** after the ticket.
- Then the short description.
- Example: `[TASK] PROJ-10996 message icon for broken/unknown attachments + case-insensitive image ext`
- **`[TASK]` for EVERY FE PR — including test-only, docs-only and refactor PRs.** The FE repo's own
  `CLAUDE.md` lists other prefixes (`[TEST]`, `[DOCS]`, `[REFACTOR]`, …) for *commit* messages, and a
  test-only PR looks like a natural fit for `[TEST]`. It is not. Team decision: PR titles stay
  `[TASK]` whatever the change contains. Do not pick a "more accurate" prefix.

This pattern is **FE-repo-only**. .NET repos keep their normal `PROJ-<number>: <description>` title (colon, no `[TASK]`). When opening/updating an FE PR (`gh pr create` / `gh pr edit --title`), enforce this exact shape.

## Push discipline (step 6)

- Push only after every gate is green **and** the user has confirmed the push (the skill invocation is the directive when run standalone with an explicit "push"; when called as a do-ticket phase, confirm once: *"All gates green — push `<branch>` to origin? (y/n)"*).
- Rebased/amended branch → `git push --force-with-lease` (never `--force`). `base_branch` / `master` pushes still require explicit confirmation per global git policy.
- **Clean up the measurement artifacts after a green gate.** `begin` + `build` leave `.sonarqube/` and the
  coverage collector leaves `coverage.xml` — on a large solution that is tens of megabytes, and neither is
  git-ignored in every repo, so both show up in `git status` and can be staged by a careless `git add .`.
  Delete both once the gate is green and the push is done. (If your environment refuses a recursive delete,
  remove the files first, then the empty folders.) Keep them only while a gate is RED and you are still reading them.
- After a successful push: standalone → offer `pr-description` / `gh pr create` (FE PR title MUST use the `[TASK] PROJ-<n> …` shape — see `## Frontend repos`). As a do-ticket phase → return control to `pr-ready` (21).
- **CI still gates.** Because duplication isn't checked locally and the server gate never ran, the PR's CI Sonar is still the source of truth — this skill front-loads the two gates it *can* check so the PR rarely bounces, not a replacement for CI.

## Scope & portability

- The skill is a **generic algorithm**. All company data — Sonar host, org, token env-var name, gate thresholds, and how to resolve each repo's Sonar project key — lives in `projects.<active>.sonar`. No host or key is hard-coded here.
- The scan command (exclusions, solution, coverage test command, project key) is **derived from each repo's own Sonar CI workflow** (`.github/workflows/*sonar*.y*ml` or `sonar-project.properties`), not duplicated in config — so it can never drift from what CI runs. See `sonar-local-gate.md` §2.
- The two parsers (`parse-sonar-issues.py`, `parse-new-coverage.py`) are diff-driven and project-agnostic — they take `<repo> <base_ref> [coverage.xml]` and read only local artifacts.
- Projects without a `sonar` block (no SonarQube server in their stack) never reach this skill; their pipelines keep their own push path.
