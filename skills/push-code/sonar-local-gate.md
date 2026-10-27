# sonar-local-gate — reproduce the CI Sonar findings locally (no upload), then gate

Detail behind pipeline steps 4 (`local-analysis`) and 5 (`local-gate`). Runs **per repo in the changeset** (step 1). Backend (.NET) is the primary path; frontend is noted where it differs.

The gate is computed **entirely from local files** — `.sonarqube/out/*/Issues.json` (analyzer findings) and `coverage.xml` — because the server-upload step is blocked on a sandboxed workstation (SKILL.md "Why this exists"). Do not attempt `sonarscanner end` / Web-API read-back; they do not work in that environment.

---

## 1. What produces the two artifacts

- **`sonarscanner begin`** (pure .NET): downloads the project's quality profile from the server (needs the token + host reachable) and injects the **SonarAnalyzer Roslyn analyzers** + a generated ruleset into the build. No Java.
- **`dotnet build`**: the analyzers run in-process; the scanner writes every finding to `<repo>/.sonarqube/out/<n>/Issues.json` (SARIF v1). This is the same finding set CI's PR analysis reports.
- **`dotnet-coverage collect`**: runs the tests and writes `coverage.xml` (VS coverage XML). We scope it to the changed-code tests (§3) — the gate is new-code-only, so the full suite is unnecessary.
- **"New code" = the git diff** (`base...HEAD`). We do not rely on the server's new-code baseline, so no branch analysis / `sonar.branch.name` is required.

## 2. Derive the scan inputs from the repo's own CI workflow (do NOT hard-code)

The single source of truth is the repo's Sonar CI workflow — read it and extract, so the local run stays in lockstep with CI.

**.NET repos** — read `.github/workflows/*sonar*.y*ml`. From the `dotnet sonarscanner begin` invocation extract: `/k:` project key, `/o:` org, `sonar.host.url`, `sonar.solution`, `sonar.exclusions`, `sonar.coverage.exclusions`, `sonar.cs.vscoveragexml.reportsPaths`. Also the **coverage test command** (e.g. `dotnet-coverage collect "dotnet test <TestProj> --no-build -c Release" -f xml -o coverage.xml`) and any prep the tests need (`cp <TestProj>/configuration.example.json <TestProj>/configuration.json`, nuget source add, etc. — replicate what affects build/test; skip CI-only concerns like spinning up a Postgres *service* container — point tests at the local/dev DB per `_config/projects.yaml`, or use the project's own test-DB tooling).

**Frontend repos** — `sonar-project.properties` + workflow; `sonar-scanner` CLI + Jest lcov. On-demand only; the primary path is .NET.

**Substitutions vs CI:**
| CI | Local |
|----|-------|
| `sonar.token=${{ secrets.SONAR_TOKEN }}` | `sonar.token=$<token_env>` (your PERSONAL token, never the CI secret / a literal) |
| `sonar.pullrequest.*`, `sonar.branch.name`, `sonar.qualitygate.wait` | **dropped** — no upload, no server gate |
| `-c Release` + `dotnet add package Acme.Shared` (NuGet) | **`-c Debug`** — uses the disk `ProjectReference` (Debug-only) so no csproj mutation / NuGet dance (acme-api-task gotcha). Debug vs Release does not change analyzer findings or line coverage. |
| full-suite coverage command | **scoped** coverage command (§3) |

## 3. Run sequence (.NET, per repo)

### Hard rules first — each one has produced a false green on a real run

Rules (a)–(c) come from PROJ-11239, (d)–(e) from PROJ-11249, (f) from PROJ-11416. All six share one
shape: **the gate printed a confident, non-zero-looking number over something it had not actually
measured.**

**(f) One `begin`, then exactly ONE build. A failed build poisons `Issues.json`.** The scanner writes every
build in the directory into the same `.sonarqube/out`, and compile errors land there as rule ids like any
finding. On PROJ-11416 a Release build died with 10k `CS0246`/`CS0234` (outside Debug the repo references
`Acme.Shared` as a NuGet package from a private feed that needs credentials the local run did not have); the
Debug build that followed was clean, but the parse still reported those dead errors against the changed
file. Cleaning by hand does not save you either — `Remove-Item .sonarqube -Recurse` fails on locked
`bin/*.dll` and still looks like it worked. **Assert before parsing:** zero compile-error rule ids
(`CS####`) across the SARIF files. Non-zero means you are reading a build that never completed.

> Corollary: if Release cannot build locally, run the analyzers in **Debug** and say so in the gate
> summary as a deviation from CI. Silently switching configuration is how a local green stops predicting a
> CI green.

**(a) Measure a COMMITTED, clean tree. Never a dirty one.** Both parsers compute added lines from
`git diff -U0 <base>...HEAD` — **committed only** — while `Issues.json` and `coverage.xml` carry line numbers
from the build of the **working tree**. With uncommitted edits the two sides describe different files, so
findings get pinned to the wrong lines: they flicker in and out of "new" between runs, and a brand-new
**untracked** file is invisible to the diff entirely — neither gated nor counted in coverage. On PROJ-11239
that silently excluded a fully-covered new service and reported 78.4% when the real number was 82.9%.
**So: commit → confirm `git status` is clean (ignoring `.sonarqube/` + `coverage.xml`) → then begin/build/
collect/parse.** If a gate goes red, fix, commit again, re-measure. Amending is fine before the push.
`parse-sonar-issues.py` enforces this: modified tracked files → exit 2 (BLOCKED).

**(b) Build with `--no-incremental`.** MSBuild skips `CoreCompile` for up-to-date projects, so their
analyzers never run and no `Issues.json` is written for them. The parser then prints a confident
`2/2 SARIF file(s) read` over a **reduced project set**. (`parse-sonar-issues.py` also returns exit 2 when a
changed source file is newer than the oldest `Issues.json` — a stale SARIF reads exactly like a live one.)

**(c) Count the `out/*` folders — it must equal the number of projects ANALYSED (not the number of
`Project(` lines in the .sln).** A solution whose projects carry `ProjectReference`s to repos outside
the .sln gets one `out/` folder per *compilation*, so the counts legitimately differ: on `acme-idp`
(2 sln projects) a clean run produces **4** — a sibling expression-builder library, `Acme.Shared`, the app
and its test project. Read `out/*/ProjectInfo.xml` → `<ProjectName>` to name them, and judge staleness by
`LastWriteTime` against the current run, not by the count alone. When `.sonarqube/bin/*.dll` is locked
(MSBuild node reuse), the delete fails and the next `begin` **adds** `out/2`, `out/3` beside the stale
`out/0`, `out/1`. The parser reads 2 fresh + 2 stale and reports `4/4 SARIF file(s) read, 7027 results`
— a number that looks better than the truth. Check `LastWriteTime` on every `Issues.json`, and delete
`.sonarqube/` with Bash `rm -rf` when PowerShell cannot.

**(d) A test run is only evidence if the build that preceded it SUCCEEDED.** `dotnet test --no-build`
runs whatever DLLs are on disk from the **last successful** build. So a build that ends `7 Error(s)` still
leaves the previous binaries in place, and the test step prints a full, confident `Passed! … Total: 43`
**for code that does not compile**. Nothing in the two parsers catches this: `Issues.json` and
`coverage.xml` look plausible, the counts are non-zero, and the gate goes green over a phantom.

Observed 2026-08-03 (PROJ-11249): a branch freshly cut from `master` failed to build with
`CS1061`/`CS0117`, and the same command block reported 43 tests passed from the previous branch's DLLs.

So: **read the build result before running or trusting any test count.** Require a literal `0 Error(s)` /
`Build succeeded`, and if the build fails, the test numbers from that block are void — do not report them,
do not push. A common root cause is a **Debug-only `ProjectReference` to a sibling shared-lib checkout**:
the Debug build compiles whatever that local checkout holds, so a checkout behind master breaks a build of
the service's master. Fix with `git fetch origin master && git merge --ff-only origin/master` in the
shared-lib checkout, then rebuild — needed after a rebase **and** after cutting any fresh branch off master.

**(e) Run `sonarscanner` from PowerShell, never Git Bash.** Git Bash (MSYS) rewrites `/k:`-style arguments
as file paths, so `begin` receives garbage, rejects each argument, and **prints its whole argv back —
including the expanded `sonar.token`** — into the transcript. That is a credential leak caused by the tool,
not by writing the secret literally, so the usual "never inline a password" habit does not prevent it. If
it happens, tell the user to rotate the token. See `setup.md` §5.

```
# from repo root, on the ticket branch; env: token_env set (no Java needed)
# run the `begin` line from PowerShell — see (e)
# Shortcut: steps 2-4 in one go → push-code/sonar-local.ps1 (PowerShell):
#   -Repo -Key -Org -HostUrl -Build -TestTarget [-Exclusions] [-CoverageExclusions] [-Filter]
#   token read from $env:SONAR_TOKEN, never echoed; exit 2 on begin/build/coverage failure;
#   ends by listing .sonarqube/out/* (ProjectName + Issues.json time) so you can check rule (c)
1. <prep steps from §2>                                   # e.g. cp configuration.example.json configuration.json
2. dotnet sonarscanner begin /k:"<key>" /o:"<org>" \
     /d:sonar.token="$<token_env>" /d:sonar.host.url="<host>" \
     /d:sonar.cs.vscoveragexml.reportsPaths=coverage.xml /d:sonar.solution="<sln>" \
     /d:sonar.exclusions="<...>" /d:sonar.coverage.exclusions="<...>"
3. dotnet build "<sln>" --no-incremental -c Debug          # analyzers run here → .sonarqube/out/*/Issues.json
                                                            # --no-incremental per rule (b); DO NOT use --no-restore alone
4. dotnet-coverage collect "dotnet test <TestProj> --no-build -c Debug \
     --filter \"<FILTER>\"" -f xml -o coverage.xml         # SCOPED — see below
#  NO `sonarscanner end`. Nothing is uploaded.
```

**First: does scoping buy anything?** Time the full suite once (`dotnet test --no-build`). **If it finishes in
under ~60 s, use the FULL suite and skip the filter entirely** — scoping then adds under-measurement risk for
no wall-clock gain. Measured: `acme-idp` full suite = **6 s** (597 tests), so the filter is pure downside
there; `acme-api` = **~22 min**, where scoping is the whole point. Say which one you used in the gate summary.

**Scoped coverage `<FILTER>` — the speed lever when the suite is slow.** Run only the test classes that exercise the changed production code, joined by `|`:
`FullyQualifiedName~<ClassA>|FullyQualifiedName~<ClassB>|...`
Derive the classes from the diff: for each changed production type/method, the test class(es) that reference it (usually named `<Type>Tests` / `<Type>Test`, plus any integration test class that drives the changed flow). New-code coverage stays accurate because these cover every new line; the other tests don't touch new lines. Measured impact on acme-api-task: **full suite ≈ 22 min → scoped ≈ 16 s.** If you cannot confidently name the covering classes, widen the filter (or fall back to the full suite) and `log` that you did — never silently narrow coverage.

**After the run, count the tests of EACH class you named — a class with 0 tests is BLOCKED.** `~` is a
substring match, so it fails silently in both directions: `~OrderSyncWorkflowTest` does NOT match the
sibling `OrderSyncWorkflowTwoPassTest` (the infix breaks it), and a short stem matches classes you did not
mean. The run still prints `Passed!` with a plausible total. Observed 2026-10-13: one of four named classes
ran in none of three runs, and every total looked fine. Run `dotnet test ... --list-tests --filter "<FILTER>"`
first, or read the per-test lines, and check each class appears.

**Pass the repo's own test-project marker to the coverage parser.** `parse-new-coverage.py` takes it as a
5th argument (`|`-separated substrings). With no 5th argument it matches **both** common conventions,
`.mstest|.test`. An older default of `.mstest` alone was right for MSTest repos (`Acme.Api.MSTest`) and
**wrong for every xunit repo**, where the test project is named `*.Test`: it silently classed the new test
FILE as production code and counted its lines in the new-code denominator. Observed 2026-08-27 on
`acme-idp`: reported `98/98 = 100.0%` where the real production figure was **5/5**. The verdict was
unaffected because both are 100%, but a poorly-covered test file would move the number in either direction.
Pass it explicitly when a repo uses another naming scheme:

```bash
python parse-new-coverage.py <repo> <base_ref> coverage.xml 80 .test    # xunit repos (*.Test) only
python parse-new-coverage.py <repo> <base_ref> coverage.xml             # default: .mstest|.test
# add the CI's own exclusions — copy them from the repo's workflow (grep -rn exclusions .github/workflows/):
python parse-new-coverage.py <repo> <base_ref> coverage.xml 80 .test \
  --exclude="src/Acme.App/Migrations/**/*,src/Acme.App/Startup.cs,src/Acme.App/EmailTemplates/**/*"
```

**Always pass `--exclude=` with the CI's exclusion globs.** Without it, files CI never measures (EF
migrations, generated code) land in the denominator. Measured 2026-10-07 on `acme-idp` (PROJ-11570): no
flag → `14/5225 = 0.3%`, exit 1 (a 5 211-line migration Designer); with the CI globs → `14/14 = 100%`,
exit 0, "3 file(s) excluded". The output names every excluded file as NOT EXAMINED — read that list; a
production file in it means the glob is too wide.

State the production line count in the gate summary, not just the percentage — `5/5` and `98/98` read
the same as a percentage and are not the same measurement.

- `coverage.xml` and `.sonarqube/` are **build artifacts** — delete them after the gate; they are not gitignored in every repo, so never `git add` them. (`coverage.xml` can be tens of MB.)
- Timings: `begin` ~10–30 s, Debug build ~1–2 min (analyzers add overhead), scoped coverage seconds. No multi-minute upload.

## 4. Enforce the gates (parse local files — no server)

Two helper scripts live in this skill dir; both take `<repo> <base_ref>` and read only local artifacts.

1. **Rule issues on new code** —
   ```
   python parse-sonar-issues.py <repo> <base_ref> --exclude="<the CI workflow's sonar.exclusions>"
   ```
   **Always pass `--exclude=`.** The analyzers run in the build, so `Issues.json` also holds findings for
   files the server drops (EF migrations). Without it, PROJ-8665 read 49 `S1192` in a generated
   migration as new-code issues; with it, 0. The `NOT EXAMINED` line names every excluded file — check
   no production file is in it.

   Gated rule ids are `S####` (SonarC#), `CA####` (Roslyn analyzers the profile imports) and `CS####`
   (compiler diagnostics Sonar's Roslyn engine imports, e.g. `CS1573`). Any other id shape on a changed
   file is **not dropped in silence**: it is counted on an `UNGATED RULE SHAPES` line — read it, and check
   none of those is CI-enforced. Method-scoped rules (`S3776`, `S1541`, `S138`, `S134`, `S1067`) also gate
   when an added line falls inside the member body; class-scoped rules (`S6960`, `S6934`, `S1200`, `S1448`,
   `S1820`, `S110`) gate when an added line falls at or below the class line. `test-parse-sonar-issues.py`
   in this skill dir is the red-first test for all of this — re-run it after ANY edit to the parser.

   Reads `.sonarqube/out/*/Issues.json`, keeps `S####` results whose location is a **diff-added line**, prints `rule · file:line · message`. **Exit 1 if any** → FM-SONAR-NEWISSUE. Issues on pre-existing lines are listed for context only.
2. **Coverage on new code** —
   ```
   python parse-new-coverage.py <repo> <base_ref> coverage.xml <min_pct> [test_marker] [--exclude=<glob,...>]
   ```
   Intersects `coverage.xml` covered/executable lines with the diff-added lines of changed **production** files (excludes the test project via `test_marker`, default `.mstest|.test`), prints per-file + overall %. **Exit 1 if overall < `min_pct`** (default 80) → FM-COVERAGE-LOW; prints the uncovered new lines to fix.

**Decision — three exit codes, not two** (`_shared/measurement-integrity-protocol.md`):

| Exit | Meaning | What to do |
|---|---|---|
| **0** | clean, over a **non-zero** scope printed on the `SCOPE` line | → step 6 (push) |
| **1** | RED — a real finding (issue on a new line / coverage below gate) | → gate-failure loop in `SKILL.md`. **Fix the code.** |
| **2** | **BLOCKED — the measurement did not happen** | **Fix the MEASUREMENT, not the code**, then re-run from step 4 |

Exit 2 fires on: a base ref that doesn't resolve, an empty diff, no `Issues.json` (analyzers never
ran — a cached/no-op build writes none), an unreadable SARIF, a dirty tree (modified tracked files —
rule (a)), a changed source file newer than the oldest `Issues.json` (stale SARIF — rule (b)/(c)), a missing or empty `coverage.xml`, or a
coverage report that covers **none** of the changed production files. Never route exit 2 into the
implementation chain — there is no defect to fix, and looping the developer on it burns a cycle on a
tooling problem. Never treat it as green either: **`0/0` coverage is 100%**, which is the most
convincing false green this pipeline can produce.

Both scripts print a `SCOPE` line (files, added lines, artefacts read) and a `NOT EXAMINED` line
before any verdict. A verdict without them means an older copy of the script is on disk.

**Proven red** (2026-07-30, a real .NET repo + a synthetic SARIF fixture): all four blocked cases
returned 2, a seeded S3400 on an added line returned 1, and the same issue on a pre-existing line
returned 0 and was listed as context. Before that fix all four blocked cases returned **0 with
`0 issues` / `0/0 = 100.0%`** — the gate had never been exercised against an empty input.

**Duplication** on new code is not computed here (needs the server) — state that it's deferred to CI,
don't imply it passed.

### ⚠ The gate's "new code" test DISAGREES with the server in BOTH directions

The parser asks *"is the issue's reported line among the diff's added lines?"*. The server asks *"did this
issue exist before?"*, and it treats a **relocated** line as changed. So the gate can print `0 on new lines`
while CI reports new issues. Both cases hit on PROJ-11239:

| Blind spot | What happened |
|---|---|
| Issue reported on an **unchanged** line but **caused** by an added line in the same construct | `S107` (constructor 8 params > 7) is reported on the *class declaration* line; the added line was the new parameter 6 lines below. Master had 7 params, so the change caused it — and the gate called it "pre-existing". |
| Issue on a line that **moved** | Extracting a method shifted `_logger.LogError(ex, ex.Message)` from line 104 to 64. Git matched it as context, the gate saw "unchanged", the server saw new code (`CA2254`). |

**Until the parser covers these, do this manually — it is not optional:** read the
*"Sonar issues on pre-existing lines in changed files (not gated)"* list in full; do **not** skim past it.
For every entry sitting in a member you touched, ask *"would this exist on master?"* and check with
`git show <base>:<file>`. A rule about a **declaration** — parameter count, member count, cognitive
complexity — belongs to the member, not to one line. Cheapest defence when a refactor relocates legacy
code: **clear every finding in the touched region**, so no later line shift can resurface one as new.

Planned parser patch (deferred): gate issues whose enclosing member overlaps changed lines, and treat
moved lines as new. Ship a red-first test for both cases before trusting it.

#### The other direction: a FALSE RED on a class-scoped rule

The two blind spots above make the gate too narrow. A class-scoped rule makes it too WIDE. The parser
annotates such a finding `[class gained members in this diff]` and counts it as new code — but it does
not verify that claim. Editing ONE line inside an existing method is enough to trigger it, and then a
rule about the class as a whole (`S6960` too many responsibilities, `S6934` route attribute) is reported
against a change that added no member at all.

**Settle it with the server, never by judgement, and never by softening the gate.** The Web API read
works even where the upload path does not:

```
curl -s -u "$SONAR_TOKEN:" "$HOST/api/issues/search?componentKeys=$KEY&rules=csharpsquid:S6960&resolved=false&ps=100"
```

If the issue is already listed on the project at the SAME file and line, with a `creationDate` older than
the branch, it is pre-existing and the server will not count it as new code. Put the rule, the file:line
and that creationDate in the gate summary, so the decision is auditable instead of a claim.

Observed 2026-09-29: two findings annotated "class gained members" sat on classes whose diff was a
single-line edit inside an existing method. Both had been on master for over a year, and the PR's
SonarQube check passed — confirming the local red was the false one.

## 5. Notes / gotchas

- **Analyzer findings ≠ build warnings.** The scanner routes SonarAnalyzer diagnostics to `Issues.json` (often at Info severity), so they do **not** appear in `dotnet build` console output — always read the SARIF, not the build log.
- **New-code = diff** here, which matches CI's PR new-code when the PR's New Code setting is "reference branch = master". If a project uses version-based New Code, the local (diff) number is still the right thing to gate a *change* on; CI's number converges once the PR targets master.
- **SonarC# authoring gotchas** — `S125` (prose comments that look like code — avoid `;`/`()` in comments), `S3358` (nested ternary), `S3776` (cognitive complexity) fire most; pre-empt them in the final-review step so the parse comes back clean.
- **Coverage exclusions** from §2 are honored by the scanner during collection; the coverage parser only looks at production diff lines, so excluded infra files never enter the denominator.
