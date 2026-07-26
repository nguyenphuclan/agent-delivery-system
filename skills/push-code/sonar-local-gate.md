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

**Frontend repos** — `sonar-project.properties` + workflow; `sonar-scanner` CLI + Jest lcov. On-demand (user works mostly backend).

**Substitutions vs CI:**
| CI | Local |
|----|-------|
| `sonar.token=${{ secrets.SONAR_TOKEN }}` | `sonar.token=$<token_env>` (your PERSONAL token, never the CI secret / a literal) |
| `sonar.pullrequest.*`, `sonar.branch.name`, `sonar.qualitygate.wait` | **dropped** — no upload, no server gate |
| `-c Release` + `dotnet add package Acme.Shared` (NuGet) | **`-c Debug`** — uses the disk `ProjectReference` (Debug-only) so no csproj mutation / NuGet dance (acme-api-task gotcha). Debug vs Release does not change analyzer findings or line coverage. |
| full-suite coverage command | **scoped** coverage command (§3) |

## 3. Run sequence (.NET, per repo)

```
# from repo root, on the ticket branch; env: token_env set (no Java needed)
1. <prep steps from §2>                                   # e.g. cp configuration.example.json configuration.json
2. dotnet sonarscanner begin /k:"<key>" /o:"<org>" \
     /d:sonar.token="$<token_env>" /d:sonar.host.url="<host>" \
     /d:sonar.cs.vscoveragexml.reportsPaths=coverage.xml /d:sonar.solution="<sln>" \
     /d:sonar.exclusions="<...>" /d:sonar.coverage.exclusions="<...>"
3. dotnet build "<sln>" --no-restore -c Debug              # analyzers run here → .sonarqube/out/*/Issues.json
4. dotnet-coverage collect "dotnet test <TestProj> --no-build -c Debug \
     --filter \"<FILTER>\"" -f xml -o coverage.xml         # SCOPED — see below
#  NO `sonarscanner end`. Nothing is uploaded.
```

**Scoped coverage `<FILTER>` — the speed lever.** Run only the test classes that exercise the changed production code, joined by `|`:
`FullyQualifiedName~<ClassA>|FullyQualifiedName~<ClassB>|...`
Derive the classes from the diff: for each changed production type/method, the test class(es) that reference it (usually named `<Type>Tests` / `<Type>Test`, plus any integration test class that drives the changed flow). New-code coverage stays accurate because these cover every new line; the other tests don't touch new lines. Measured impact on acme-api-task: **full suite ≈ 22 min → scoped ≈ 16 s.** If you cannot confidently name the covering classes, widen the filter (or fall back to the full suite) and `log` that you did — never silently narrow coverage.

- `coverage.xml` and `.sonarqube/` are **build artifacts** — delete them after the gate; they are not gitignored in every repo, so never `git add` them. (`coverage.xml` can be tens of MB.)
- Timings: `begin` ~10–30 s, Debug build ~1–2 min (analyzers add overhead), scoped coverage seconds. No multi-minute upload.

## 4. Enforce the gates (parse local files — no server)

Two helper scripts live in this skill dir; both take `<repo> <base_ref>` and read only local artifacts.

1. **Rule issues on new code** —
   ```
   python parse-sonar-issues.py <repo> <base_ref>
   ```
   Reads `.sonarqube/out/*/Issues.json`, keeps `S####` results whose location is a **diff-added line**, prints `rule · file:line · message`. **Exit 1 if any** → FM-SONAR-NEWISSUE. Issues on pre-existing lines are listed for context only.
2. **Coverage on new code** —
   ```
   python parse-new-coverage.py <repo> <base_ref> coverage.xml <min_pct> [test_marker]
   ```
   Intersects `coverage.xml` covered/executable lines with the diff-added lines of changed **production** files (excludes the test project via `test_marker`, default `.MSTest`), prints per-file + overall %. **Exit 1 if overall < `min_pct`** (default 80) → FM-COVERAGE-LOW; prints the uncovered new lines to fix.

**Decision:** both exit 0 → step 6 (push). Either non-zero → the gate-failure loop in `SKILL.md`. **Duplication** on new code is not computed here (needs the server) — state that it's deferred to CI, don't imply it passed.

## 5. Notes / gotchas

- **Analyzer findings ≠ build warnings.** The scanner routes SonarAnalyzer diagnostics to `Issues.json` (often at Info severity), so they do **not** appear in `dotnet build` console output — always read the SARIF, not the build log.
- **New-code = diff** here, which matches CI's PR new-code when the PR's New Code setting is "reference branch = master". If a project uses version-based New Code, the local (diff) number is still the right thing to gate a *change* on; CI's number converges once the PR targets master.
- **SonarC# authoring gotchas** — `S125` (prose comments that look like code — avoid `;`/`()` in comments), `S3358` (nested ternary), `S3776` (cognitive complexity) fire most; pre-empt them in the final-review step so the parse comes back clean (memory `feedback_sonar_csharp_comment_ternary`).
- **Coverage exclusions** from §2 are honored by the scanner during collection; the coverage parser only looks at production diff lines, so excluded infra files never enter the denominator.
