---
name: worktree-setup
description: Generic git worktree setup for multi-repo .NET microservice stacks. Creates mirrored worktrees so a parallel ticket stack runs without leaking shared code or port-clashing with the main branch. Per-worktree port offset auto-allocated. Generates VS Code `.vscode/launch.json` + `tasks.json` so the user can click "Run All" in the worktree workspace. All company-specific config (repo names, service list, ports, tokens) lives in `_config/projects.yaml` — the skill itself is portable across companies.
tech_stack: [git-worktree, dotnet, multi-repo, microservices]
---

## Pre-flight

**Tier: B** (local filesystem changes, reversible).

Invoked by `do-ticket`, which already runs `~/.claude/skills/_shared/pre-flight-protocol.md`. If invoked standalone, run pre-flight first.

Skill-specific overrides:
- `requires_project_fields`: [active, jira_prefix, repos.shared_lib, paths.repos_root, paths.worktree_base, worktree.services, worktree.port_offsets, worktree.health_check.endpoint_template, worktree.health_check.bearer_token, worktree.health_check.nonexistent_task_id]
- `risk_signals`: [g4-local-fs-mutation]
- `skip_when`: never

---

# worktree-setup

## Portability

This skill is **company-agnostic**. It encodes the algorithm only:
- Mirrored worktree layout for relative ProjectReference resolution
- Port offset auto-allocation
- Copy gitignored `.Development.json` from main + rewrite URLs
- Build (shared serial → services serial, main `.csproj` only)
- Generate VS Code `.vscode/` files for click-Run-All
- Optional agent-driven start/health-probe/stop

**Everything company-specific** (repo names, service projects, ports, JWT token, health endpoint, gateway service alias) lives in `_config/projects.yaml`. To onboard a new company: fill `projects.yaml.<project>.{repos, worktree.services, worktree.health_check}` — skill itself does not change.

---

## Modes

| Mode | Triggered by | Action |
|---|---|---|
| `health` | resume a ticket in an existing worktree, after any rebase, "check worktree" | Phase 0: `check_worktree.py` freshness + running-services check (manual table as fallback) |
| `setup` (default) | `do-ticket --worktree`, "setup worktree" | Phase 1–5: pick offset → create worktrees (incl. static FE) → copy/rewrite Dev configs → build-verify → generate `.vscode/launch.json` |
| `port-default` (new) | "switch to main ports", "use default ports" | Phase 5b: rewrite all `.Development.json` + `.vscode/launch.json` URLs from `localhost:<offset_port>` → `localhost:<main_port>`. Use when user wants FE to talk to this worktree's BE instead of main BE. Pre-condition: main BE must be stopped (default ports free) AND no other worktree is currently in `port-default`. |
| `port-offset` (new) | "switch back to offset", "use worktree ports" | Phase 5b reverse: rewrite from `localhost:<main_port>` → `localhost:<offset_port>`. Restores parallel-safe coexistence with main. |
| `start` (optional) | "start worktree", agent-driven test | Phase 6: spawn services in dep order via background bash + health probe. Alternative: user opens `${WT_ROOT}` in VS Code, clicks **Run All** |
| `stop` | "stop worktree" | Phase 7: kill background bash sessions |
| `cleanup` | `do-ticket` Step 15, "remove worktree" | Phase 8: stop if running → remove worktrees |

### Port-mode lifecycle

```
setup → port_mode=offset (BE on main_port+offset, parallel-safe with main)
   ↓
[user verifies BE via API tests + bearer token through gateway]
   ↓ "switch to main ports" + user stops main
port-default → port_mode=default (BE on main_port, FE-compatible)
   ↓
[user verifies FE workflow against worktree BE]
   ↓ "switch back to offset" + user starts main again
port-offset → port_mode=offset (back to parallel-safe)
```

---

## Core invariant: mirrored layout

If service `.csproj` files reference shared via relative paths like:
```xml
<ProjectReference Include="..\..\..\<shared_repo>\src\<shared_proj>\<shared_proj>.csproj" />
```

then for the worktree's services to reference the **worktree's shared** (not main's shared), worktree layout MUST mirror the parent dir of repos exactly:

```
<worktree_base>/<TICKET_ID>/         ← mirrors <repos_root>/
  ├── <service_repo_1>/              (worktree)
  ├── <service_repo_2>/              (worktree)
  ├── …
  └── <shared_lib_repo>/             (worktree — mandatory)
```

Non-negotiable. Different layouts will silently fall back to main-branch shared code.

---

## Project config

Reads from `_config/projects.yaml`:

| Field | Purpose |
|---|---|
| `${project.repos.shared_lib}` | shared-lib repo alias (mandatory worktree) |
| `${project.paths.repos_root}` | parent dir of source repos |
| `${project.paths.worktree_base}` | parent dir for worktrees |
| `${project.base_branch}` | branch every new worktree starts from (template key: `branch.main_branch`) |
| `${project.worktree.always_be_only}` | optional. `true` = never create FE / static worktrees and never ask (Phase 2a) |
| `${project.worktree.services}` | map of N services. Each entry: `repo_alias`, `project_path`, `main_port`, `start_order`, optional `dll_relative` (defaults to `${project_path}/bin/Debug/net8.0/<csproj-stem>.dll`) |
| `${project.worktree.port_offsets}` | candidate offsets for auto-allocation (e.g. `[100, 200, …, 900]`) |
| `${project.worktree.health_check.gateway_service}` | name of service that fronts the stack and is hit by health probe (typically the API gateway) |
| `${project.worktree.health_check.endpoint_template}` | path template for the probe (e.g. `/api/v1/tasks?Id={task_id}`) |
| `${project.worktree.health_check.bearer_token}` | long-lived bearer token validating against local stack |
| `${project.worktree.health_check.nonexistent_task_id}` | resource ID known not to exist |

If a required field is blank or `(fill in)` → stop and ask user to fill `_config/projects.yaml`.

---

## Phase 0 — Health check (run FIRST on any existing worktree)

Before doing anything in a worktree that already exists — resuming a ticket, starting a session,
and **always after a rebase** — run:

```bash
python _shared/tools/check_worktree.py <WT_ROOT> --fetch     # drop --fetch only if you fetched every repo just now
```

Exit 0 = safe. Exit **2** = BLOCKED, with the reason named. It answers two things a glance cannot:
every repo's distance from the base branch (`--base` defaults to the project's base branch; without
`--fetch` it warns when the remote refs are old), and whether this worktree's services are still running
(ports from the `ports:` map in `.worktree-meta.yaml`, or `--ports`). A running service is reported, not
blocked: you want it for an API test, not for a build.

The tool does not check that ports agree with the config files, so do that row of the table below by hand.
If the tool cannot run, the whole table is the check. Any "fail" blocks work until fixed.

| Check | How | Pass / fail |
|---|---|---|
| Freshness, **every** repo | `git -C <repo> fetch origin <base> --quiet` then `git -C <repo> rev-list --count HEAD..origin/<base>` | `0` = pass. Non-zero = that repo is behind the base branch |
| Ports agree | compare `port_offset` in `.worktree-meta.yaml` with the ports in each `appsettings.Development*.json` | every port = `main_port + offset` (or `main_port` in `default` mode) |
| No stale services | list `dotnet` processes whose command line contains this worktree's folder | none running before a build. A live one holds the shared lib dll and breaks the next build (`MSB3021`) |

**The freshness check is the one that earns its keep.** A base-branch move requires refreshing
**EVERY repo in the worktree**, not just the one being edited. A cross-repo ticket breaks the build
from the side you did not touch: on PROJ-7251, rebasing the service left the shared lib 3 commits
behind, and the build failed with `CS0117 … does not contain '<Member>'` — a missing-member error
that reads exactly like your own bug. Measured after that ticket: two *other* repos in the same
worktree were still 7 and 1 commits behind, silently, because nothing had forced them to break.

Refresh a stale repo only when it has no local changes:
```bash
git -C <repo> status --porcelain      # must be empty
git -C <repo> fetch origin <base> --quiet && git -C <repo> checkout --detach origin/<base>
```
A repo that has local changes or its own ticket branch: rebase it instead, or ask the user.

---

## Phase 1 — Pick port offset

Goal: each parallel worktree gets a unique offset so N services × M worktrees never clash.

1. List existing meta files: `${project.paths.worktree_base}/*/.worktree-meta.yaml`. Read `port_offset` from each → set of taken offsets.

   **A worktree with no meta file is not automatically a claimant.** Most such folders are
   code-only checkouts (a few repos, or a full set whose Phase 3 never ran) and hold no
   `appsettings.Development.json`. Without dev configs a worktree cannot run the stack at all, so it
   can never occupy a port.

   So when a meta file is missing, decide by config presence rather than assuming the worst:
   ```bash
   find "<worktree>" -iname "appsettings.[Dd]evelopment*.json" -not -path "*/bin/*" | head -1
   ```
   Nothing found → not a port claimant, ignore it. Found → infer its offset from the ports inside
   that file and treat the offset as taken.
2. For each candidate offset in `${project.worktree.port_offsets}`:
   - Skip if already taken by another worktree.
   - Compute effective ports: `effective = service.main_port + offset` for every service.
   - Check each via `netstat -ano | grep -E ":<port>\s" | grep LISTENING` — must all be free.
   - First candidate where all ports are free → choose it.
3. If none fit → ask user for a custom offset.

For each service, `effective_port = service.main_port + offset`. Used everywhere downstream.

---

## Phase 2 — Create worktrees (atomic)

`WT_ROOT="${project.paths.worktree_base}/${TICKET_ID}"`. `mkdir -p "$WT_ROOT"`.

### 2a. Confirm FE / static-worktree scope (mandatory gate)

**Check `${project.worktree.always_be_only}` first.** When it is `true`, set
`static_set = []` and move on — **do not ask**. The user has given a standing
answer, and re-asking every ticket is noise.

Only when that flag is absent or `false`, and `${project.worktree.static_worktrees}`
is non-empty, ask via AskUserQuestion — never clone FE by default. Most BE-only
tickets don't need a FE worktree, and a needless one drags in the `node_modules`
junction (and its cleanup hazard, see Phase 9):
> *"This ticket touches FE? Should I also create worktree(s) for: `<list static_worktrees>`? (BE services + shared-lib are always created regardless.)"*
> Options: **No — BE only (recommended)** / **Yes — clone FE too**

- **No / no answer / BE-only** → set `static_set = []`. Skip all FE worktrees AND the `node_modules` junction entirely. This is the default.
- **Yes** → set `static_set = ${project.worktree.static_worktrees}`.

A FE worktree can still be added later on request — nothing here is one-way.

Record the decision in `.worktree-meta.yaml` (`static_worktrees_created: [...]`) so Phase 9 knows exactly what (if anything) to clean up.

### 2b. Branch resolution per repo — never `HEAD`

```bash
git -C "${project.paths.repos_root}/<repo>" fetch origin ${project.base_branch} --quiet
if git -C "${project.paths.repos_root}/<repo>" show-ref --verify --quiet "refs/heads/${TICKET_ID}"; then
  BASE="${TICKET_ID}"                              # this ticket's branch already exists -- resume it
else
  BASE="--detach origin/${project.base_branch}"
fi
```

- Branch `${TICKET_ID}` exists in that repo → use it.
- Otherwise → **detached at `origin/${project.base_branch}`**, after a fetch.

Detached is correct and deliberate — branches are created lazily, only in repos
that actually receive edits (keeps empty branches out of git history). What
must never happen is detaching at **`HEAD`**.

> **Why `HEAD` is wrong (caught 2026-08-26, PROJ-7251).** The main checkouts
> are usually sitting on *another* ticket's branch. That day the service repos
> were spread over three other tickets' branches, each 1–3 commits ahead of
> `origin/<base>`. `worktree add <path> HEAD` silently based the new ticket on
> that unrelated work. Nothing errors; the build is green; the ticket is simply
> built on top of another ticket's commits, and it surfaces later as a dirty PR
> diff or a "why is this change already here" confusion.

**Fetch first.** A local `origin/<base>` can be days stale mid-sprint, and the
whole point is a clean base.

**Verify after creating** (right after 2c), do not assume — one line, and it is the only check
that catches this class of error:

```bash
git -C "${WT_ROOT}/<repo>" rev-list --count "origin/${project.base_branch}..HEAD"
```
Must be `0` for every repo where the ticket branch did not already exist.
Non-zero means the worktree is carrying commits that are not on the base branch —
remove it and recreate it from `origin/${project.base_branch}`.

### 2c. Create the worktrees

For each repo to worktree — union of:
- All `${project.worktree.services}` (BE service repos)
- `${project.repos.shared_lib}` (mandatory shared)
- `static_set` (FE / static repos — **only if user confirmed in 2a**; code-only worktrees, no config rewiring)

```bash
REPO_NAME="${project.repos.<repo_alias>}"
git -C "${project.paths.repos_root}/${REPO_NAME}" \
    worktree add "${WT_ROOT}/${REPO_NAME}" ${BASE}    # from 2b -- never HEAD
```

**Atomicity**: any `git worktree add` fails → `git worktree remove --force` the successful ones, delete `${WT_ROOT}`. Never leave a half-set.

**Static worktrees** (e.g. FE): created here **only when the 2a gate confirmed** (otherwise skipped entirely). When created, they are skipped by Phase 3 (no `.Development.json` rewrite), Phase 4 (no `dotnet build`), and Phase 5 (no entry in generated `.vscode/launch.json` — FE has its own launch system). Their config stays exactly as main, including hardcoded BE port URLs. They become useful only in `port-default` mode.

If a static worktree has `link_node_modules: true` AND main repo has `node_modules/` populated, also create a Windows junction:
```powershell
New-Item -ItemType Junction `
  -Path  "${WT_ROOT}/<repo>/node_modules" `
  -Target "${project.paths.repos_root}/<repo>/node_modules"
```
Saves install time. If the worktree branch needs new deps, user runs `pnpm install` manually — that breaks the junction (Windows replaces it with a real dir on write). Document the trade-off to user.

> ⚠️ **The junction shares the MAIN repo's real `node_modules`.** Anything that recursively deletes the junction will follow it and wipe the main repo's modules. Cleanup MUST remove the junction **link-only** (never `Remove-Item -Recurse` / `rm -rf`) — see Phase 9's junction-safe procedure. Track every junction created here so Phase 9 can find and unlink it.

---

## Phase 3 — Copy gitignored `.Development.json` + rewrite URLs

`appsettings.Development.json` is typically gitignored — lives only in main working tree, NOT carried by `git worktree add`. Without it, services fall back to `appsettings.json` (production hostnames) and can't talk to neighbors.

### 3a. Copy from main → worktree (case-insensitive)

For each service, `iname` match because some services use `Development` (capital D) and others `development`:
```bash
SRC=$(find "${project.paths.repos_root}/<repo>/<project_path>" -maxdepth 1 -iname "appsettings.development*.json" | head -1)
if [ -n "$SRC" ]; then
  cp "$SRC" "${WT_ROOT}/<repo>/<project_path>/$(basename "$SRC")"
fi
```

If a service has none in main → skip and document. If runtime later shows it's needed, user creates one in main first.

**Do NOT touch the main repo's `.Development.json`** — contains real DB strings, signing keys, JWT tokens. Modifying or echoing it leaks secrets.

### 3b. Rewrite URLs

Build the rewrite map from `${project.worktree.services}`:
```
http://localhost:<service.main_port> → http://localhost:<service.effective_port>   (per service)
```

For each `appsettings.development*.json` in each service worktree:
1. Read the file.
2. For each `(main → effective)` pair, string-replace across the whole content.
3. Write back. Log path + count of replacements.

Brute-force string replace is intentional: robust to schema changes, catches every URL form (with or without `http://` prefix).

DB connection strings are NOT rewritten — DB is shared between main and worktree per project policy.

### 3c. Copy the TEST project's gitignored config too

The service `.Development.json` files are not the only gitignored config. A test project can carry its
own — e.g. `src/<test-project>/configuration.json`, gitignored, present only in main. Without it the
test project fails to BUILD, not just to run:

```
error MSB3030: Could not copy the file "…/configuration.json" because it was not found.
```

That error names a copy task, not a missing test setting, so it reads like a broken worktree rather
than a missing file. Copy it the same way as the service configs:

```bash
for f in configuration.json; do
  SRC="${project.paths.repos_root}/<repo>/src/<test-project>/$f"
  [ -f "$SRC" ] && cp "$SRC" "${WT_ROOT}/<repo>/src/<test-project>/$f"
done
```

Prefer main's copy over the repo's `configuration.example.json`: main holds the working local values,
the example holds placeholders. Fall back to the example (what CI does) only when main has none.

**Why this is easy to miss:** Phase 4 builds each service's main `.csproj`, never the test project, so
setup passes clean and the gap only shows later when someone runs the tests. If a worktree is meant
for test work, build the test project in Phase 4 as well.

---

## Phase 4 — Build verify (order matters)

Lessons from real runs: parallel `dotnet build` on `.sln` paths fails for two reasons:
1. **File-lock contention** on shared/sub-projects (`obj/Debug/<shared>.dll`)
2. **Test project errors** unrelated to runtime (missing `configuration.json`, code compile errors in test mocks)

Use this order:
```bash
# Step 1: build shared first, serially (no contention)
dotnet build "${WT_ROOT}/${project.repos.shared_lib}" --nologo --verbosity quiet

# Step 2: parallel restore for all N service main .csproj
for svc in <services>; do
  dotnet restore "${WT_ROOT}/<repo>/<project_path>/<csproj>" --verbosity quiet &
done
wait

# Step 3: serial build of each service main .csproj (NOT .sln — skips test projects)
for svc in <services>; do
  dotnet build "${WT_ROOT}/<repo>/<project_path>/<csproj>" --nologo --verbosity quiet --no-restore
done
```

### Failure modes

- `error NU1301: Failed to retrieve information about <pkg> from <feed>` — service depends on private package on a feed (e.g. GitHub Packages) requiring auth.
  Surface to user: *"Service `<X>` needs PAT for `<feed>`. Required scopes: `read:packages` + `repo` (for private). If org uses SAML SSO, authorize PAT for the org. Set credentials via `dotnet nuget add source <feed> --name <name> --username <user> --password <PAT> --store-password-in-clear-text` or edit `%APPDATA%\NuGet\NuGet.Config`. Then retry."*

- `error CS… in <repo>/src/<X>.Test/…` — only surfaces if you build the .sln. Build the main `.csproj` instead.
- `error MSB3030 … configuration.json … not found` in a test project — the test config was not copied. See 3c.

- `error: could not find <shared>.csproj` — mirrored layout is wrong. Verify `${WT_ROOT}/<shared_repo>` exists.

### Sanity check shared resolution

```bash
cd "${WT_ROOT}/<any-service-repo>/<any-service-project_path>"
RESOLVED=$(realpath "../../../${project.repos.shared_lib}/<known-shared-csproj-relpath>")
```
`RESOLVED` must start with `${WT_ROOT}/`. If not, leakage to main — stop and report.

---

## Phase 5 — Generate `.vscode/launch.json` + `tasks.json`

This is the recommended way to run the stack: user opens `${WT_ROOT}` as the VS Code workspace, picks the **🚀 Run All** compound config, clicks play. Mirrors how the user runs main, but with worktree paths and offset ports.

### Generate `${WT_ROOT}/.vscode/launch.json`

For each service in `${project.worktree.services}`:
```json
{
  "name": "<order>. <display-name> [WT]",
  "type": "coreclr",
  "request": "launch",
  "preLaunchTask": "build: <display-name>",
  "program": "${workspaceFolder}/<repo>/<dll_relative>",
  "args": [],
  "cwd": "${workspaceFolder}/<repo>/<project_path>",
  "env": {
    "ASPNETCORE_ENVIRONMENT": "Development",
    "ASPNETCORE_URLS": "http://localhost:<effective_port>"
  },
  "stopAtEntry": false,
  "justMyCode": false
}
```

Plus a compound at the bottom:
```json
"compounds": [{
  "name": "🚀 Run All [WT <TICKET_ID>, ports +<offset>]",
  "configurations": [<all configs in start_order ascending>],
  "stopAll": true
}]
```

`${workspaceFolder}` resolves to whatever folder VS Code is opened on. Since user opens `${WT_ROOT}`, paths resolve correctly.

**Why `ASPNETCORE_URLS` is mandatory**: VS Code `coreclr` debug type launches the `.dll` directly — it does NOT load `Properties/launchSettings.json`'s `applicationUrl`. Without the env var, Kestrel binds default 5000/5001 (clash). Always set it.

**Copying main's `launch.json` is not enough.** Main's configs may carry only `ASPNETCORE_ENVIRONMENT`
(main relies on default ports), so a copied file with ports rewritten still starts every worktree
service on the MAIN port. After writing the file, check: `ASPNETCORE_URLS` count == service count,
and no main port is left in it (PROJ-10837: 0 of 8 had it until fixed).

### Generate `${WT_ROOT}/.vscode/tasks.json`

Mirror main's `tasks.json`. Each `"build: <name>"` task runs `dotnet build "${workspaceFolder}/<repo>/<project_path>/<csproj>" --configuration Debug` with `dependsOn: ["build: <shared_lib>", …]` for proper ordering.

If main has a `wait: <gateway_service> ready` task that polls a hardcoded port, copy it but **change the port to the effective worktree port** for `<gateway_service>` (not the main port).

**Always add a standalone "Stop stale services" task as the FIRST task.** A stack that shares a project-referenced lib (e.g. `Acme.Shared`) hits `MSB3021 "<lib>.dll … being used by another process"` whenever a prior **Run All** left app processes alive (session closed/detached without Stop → the compound's `stopAll` never fired), because a live app holds the loaded lib dll and the next build can't overwrite it. This one-click task kills only THIS worktree's dotnet app processes (matched by the worktree folder name in their command line, so it never touches main or a sibling worktree). Keep it **standalone** — do NOT wire it into any `preLaunchTask`, or launching a single service would kill its siblings.

```json
{
  "label": "🧹 Stop stale [WT] services",
  "detail": "Kill dotnet apps still running from THIS worktree's bin (fixes MSB3021 lib-in-use). Run when a build fails with a file-lock.",
  "type": "process",
  "command": "powershell",
  "args": [
    "-NoProfile", "-Command",
    "Get-CimInstance Win32_Process -Filter \"Name='dotnet.exe'\" | Where-Object { $_.CommandLine -match [regex]::Escape('${workspaceFolderBasename}') -and $_.CommandLine -match 'bin\\\\Debug' } | ForEach-Object { Write-Host ('Stopping ' + ($_.CommandLine -replace '.*\\\\','')); Stop-Process -Id $_.ProcessId -Force }"
  ],
  "problemMatcher": []
}
```
(`${workspaceFolderBasename}` = the worktree root folder, which every service path under it contains — e.g. `PROJ-10996`. On non-Windows hosts substitute a `pgrep -f`/`kill` equivalent.)

After files are written, tell user:
> *"VS Code config generated at `${WT_ROOT}/.vscode/`. Open Folder → `${WT_ROOT}` → Ctrl+Shift+D → pick **🚀 Run All [WT <TICKET_ID>, ports +<offset>]** → click play. If a build ever fails with `MSB3021 … being used by another process`, run the **🧹 Stop stale [WT] services** task (Ctrl+Shift+P → Run Task) to kill leftover app processes, then re-run. Always **Stop** (Shift+F5) before re-running to avoid it."*

---

## Phase 5b — Set port mode (callable independently as `port-default` / `port-offset`)

Toggles the worktree between two port states:

| Port mode | BE listens on | Use case | Compat with main |
|---|---|---|---|
| `offset` (default after setup) | `main_port + offset` (e.g. 5102, 5103, …) | Agent verifies BE via API tests with bearer token through gateway | ✅ Parallel-safe with main |
| `default` | `main_port` (5002, 5003, …) — same as main | FE testing: FE keeps default-port URLs, talks to worktree BE seamlessly when main is stopped | ❌ Main BE must be stopped first |

### Pre-checks before flipping to `default`

1. Read `${WT_ROOT}/.worktree-meta.yaml` → if `port_mode` already `default` → no-op, return.
2. Scan `${project.paths.worktree_base}/*/.worktree-meta.yaml` — if **any other worktree** has `port_mode: default` → fail: *"Worktree `<X>` is already on default ports. Switch it back to offset first (or pick that one to use)."*
3. Check each `service.main_port` is free via `netstat`. If any is occupied → fail: *"Port `<X>` is in use (likely main BE). Stop main first, then retry."*

### Flipping algorithm (forward: `offset` → `default`)

For each service, build the rewrite map:
```
http://localhost:<effective_port> → http://localhost:<main_port>
```

For each `appsettings.development*.json` in each BE service worktree (case-insensitive iname):
1. String-replace each `(effective → main)` pair across the file.

For `${WT_ROOT}/.vscode/launch.json`:
1. For each service config, replace `"ASPNETCORE_URLS": "http://localhost:<effective_port>"` → `"http://localhost:<main_port>"`.
2. Update compound name to reflect the mode: `"🚀 Run All [WT <TICKET_ID>, DEFAULT ports — main must be stopped]"`.

For `${WT_ROOT}/.vscode/tasks.json`:
1. Update `wait: <gateway_service> ready` task port from `<gateway_effective>` → `<gateway_main>`.

Update `${WT_ROOT}/.worktree-meta.yaml`:
```yaml
port_mode: default
ports: { <service>: <main_port>, … }   # all reverted
```

Tell user:
> *"Worktree flipped to default ports. Stop main BE if not already, then **Shift+F5** in VS Code → click Run All again. FE in `${WT_ROOT}/<frontend_repo>` (or main FE) will now hit worktree BE."*

### Flipping algorithm (reverse: `default` → `offset`)

Symmetric. Re-allocate the same offset previously used (or pick a fresh one if it conflicts now). Replace `(main_port → effective_port)` everywhere. Update meta.

Tell user:
> *"Worktree flipped back to offset +<N>. Safe to start main BE again on default ports. Restart worktree services in VS Code if running."*

### Idempotency & safety

- If file modification fails partway → restore from `.worktree-meta.yaml.bak` (write before mutation). Never leave half-flipped state.
- Skill writes `.worktree-meta.yaml.bak` before any rewrite, deletes it on success.
- Static worktrees (FE) are NEVER touched by port-mode flips. Their config stays as main.

---

## Phase 6 — Persist meta + return state

Write `${WT_ROOT}/.worktree-meta.yaml`:
```yaml
ticket_id: ${TICKET_ID}
created_at: <ISO timestamp>
port_offset: ${offset}
port_mode: offset                 # "offset" (default after setup) or "default" (occupying main ports)
ports:           # service_name → currently-active port (effective when offset, main when default)
worktree_paths:  # service_name → absolute worktree path; plus shared_lib + static_worktrees
static_worktrees_created: []      # FE/static repos actually cloned (per the Phase 2a gate); [] = BE-only
junctions: []                     # absolute paths of every junction created (Phase 2) — Phase 9a unlinks these link-only
running_bash_ids: {}    # populated only if Phase 7 (agent-driven start) is used
```

Return for `do-ticket` ticket-state.yaml:
```yaml
worktree_mode: true
worktree_root: ${WT_ROOT}
worktree_offset: ${offset}
worktree_paths: { … }
worktree_ports:  { … }
```

---

## Phase 7 — Agent-driven start (alternative to VS Code Run All)

Use only when user explicitly says "start worktree" / "start for testing" and doesn't want VS Code.

Group services by `start_order` ascending. For each group:

1. Spawn each via Bash `run_in_background: true`. **Env vars are mandatory** (matching the `.vscode/launch.json`):
   ```bash
   cd "${WT_ROOT}/<repo>/<project_path>"
   ASPNETCORE_ENVIRONMENT=Development ASPNETCORE_URLS="http://localhost:<effective_port>" \
     dotnet run --no-build --no-launch-profile
   ```
   `--no-launch-profile` is required to bypass `launchSettings.json` (which would force the main port). The env vars take its place.

2. Save bash IDs to `${WT_ROOT}/.worktree-meta.yaml` → `running_bash_ids.<service>`.

3. Wait for every service in this group to listen (poll up to 90s, every 3s):
   ```bash
   curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://localhost:<effective_port>/" || echo "no_response"
   ```
   Any HTTP code (incl. 404, 401) = listening. `no_response` = not yet up.

4. If any service fails 90s → read its bash output, surface, abort start sequence (started services keep running).

### Health probe (after final group)

Resolve gateway port from current `port_mode`:
- `offset` → `<gateway_service.main_port> + offset`
- `default` → `<gateway_service.main_port>`

```bash
URL=http://localhost:<gateway_active_port><endpoint_with_id_substituted>
curl -s -o /tmp/wt-health.json -w "%{http_code}" \
  -H "Authorization: Bearer ${project.worktree.health_check.bearer_token}" \
  -H "Accept: application/json" \
  "${URL}"
```

Decision tree:

| Result | Meaning |
|---|---|
| HTTP 404 with body indicating not-found | ✅ Stack live |
| HTTP 200 + body `{ success: false, message: /not found/i }` | ✅ Wrapper-style not-found, stack live |
| HTTP 200 with full resource | Resource ID exists — pick a larger `nonexistent_task_id` |
| HTTP 401/403 | Token invalid OR auth service not validating the long-lived token |
| HTTP 5xx with "<downstream> unreachable" | Gateway up, downstream not — read its bash output |
| Connection refused | Gateway not up |
| 90s elapsed | Read all bash outputs, identify failing service |

---

## Phase 8 — Stop

Read `${WT_ROOT}/.worktree-meta.yaml` → `running_bash_ids`. KillBash each. Verify ports freed via netstat. Clear `running_bash_ids`.

---

## Phase 9 — Cleanup

If `running_bash_ids` non-empty → run Phase 8 first.

### 9a. Unlink junctions FIRST (before any worktree/dir removal)

A junction (e.g. `node_modules`) points at the **main repo's real folder**. A recursive delete that descends into it destroys the main repo's data. So: find every reparse point inside `$WT_ROOT` and remove the **link only**, never recursing.

Detect: read `.worktree-meta.yaml` → `junctions: [...]` if present; otherwise scan:
```powershell
Get-ChildItem "${WT_ROOT}" -Recurse -Force -Directory -ErrorAction SilentlyContinue |
  Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 } |
  Select-Object -ExpandProperty FullName
```

For EACH junction path found:
```powershell
$j = "<junction-path>"
$target = (Get-Item $j -Force).Target          # capture for the post-check
# Unlink the junction ONLY. `rmdir` (no /s) deletes the reparse point and never
# touches the target. NEVER use Remove-Item -Recurse / rm -rf on a junction —
# on Windows PowerShell 5.1 that follows the link and wipes the target's contents.
cmd /c rmdir "$j"
```

Then **verify the target survived** before going further:
```powershell
# target dir must still exist and still have contents
if (-not (Test-Path $target) -or (Get-ChildItem $target -Force | Measure-Object).Count -eq 0) {
  # ABORT — do not continue cleanup. Surface to user: target may have been damaged.
}
```
If a junction can't be confirmed safely removed (e.g. `Target` is null, or the post-check shows the target emptied) → **stop and report**; do not run `git worktree remove` or any `rm`.

> If the user said "don't delete the junction", skip 9a's removal entirely — leave junctions in place and tell the user the worktree dir can't be auto-removed while junctions exist; they remove it manually when ready.

### 9b. Remove worktrees + scaffold

Only after 9a confirms no live junctions remain inside `$WT_ROOT`:
```bash
git -C "${project.paths.repos_root}/<each-repo>" worktree remove "${WT_ROOT}/<each-repo>"
rm -rf "${WT_ROOT}/.vscode" "${WT_ROOT}/.worktree-meta.yaml"
rmdir "${WT_ROOT}"
```

Uncommitted changes in a worktree → `git worktree remove` fails. Surface to user. Never use `--force` (discards work).

---

## Rules

- Never modify files in MAIN paths (`${repos_root}/…`). Only inside `${WT_ROOT}/…`.
- Committed `appsettings.json` is never touched — only `.Development*.json`.
- **FE / static worktrees are opt-in only.** Ask the user first (Phase 2a) unless `always_be_only: true` answers it; default to BE-only.
- **Never base a worktree on `HEAD`.** Fetch, then detach at `origin/${project.base_branch}` (or resume the ticket's own branch), and verify `rev-list --count origin/<base>..HEAD` = 0 (Phase 2b). Never clone FE — and therefore never create a `node_modules` junction — without explicit confirmation.
- **Never recursively delete a junction/symlink** (`Remove-Item -Recurse`, `rm -rf`). A `node_modules` junction points at the MAIN repo's real modules; recursing through it wipes the source. Always unlink link-only via `cmd /c rmdir <junction>` (no `/s`), then verify the target survived (Phase 9a). If unsure it's safe, leave the junction and tell the user.
- Shared-lib worktree is ALWAYS created. All N service worktrees ALWAYS created. No "minimal" mode.
- Mirrored layout `${WT_ROOT}/<repo-name>/` ↔ `${repos_root}/<repo-name>/` is mandatory.
- Setup never auto-starts services. Phase 7 (start) only on user request.
- DB is shared between main and worktree. Skill does not isolate DB schema.
- Bearer token in `worktree.health_check.bearer_token` is sensitive — never echo in logs.

---

## Known limitations

- **URL rewrite is brute-force string replace.** Misses non-`localhost:<port>` patterns (Docker hostnames, env-var-driven URLs, service discovery). Symptom: service can't reach neighbor. Fix per-service: locate config key, add explicit override mechanism in `projects.yaml`.
- **DB schema isolation** not implemented. Worktree services share dev DB with main. Risk if both write to same records. The test DB is shared too: if your tests clean tables when they start, two concurrent `dotnet test` runs (main + worktree, or two worktrees) corrupt each other — run them one at a time. **A worktree isolates the source and the ports. It does not isolate any database.**
- **Migration on startup** by any service runs against shared DB. Add `disable_migrations` env override per service if it becomes a problem.
- **Build time**: N services × ~30–60s. First setup ~5 min cold; warm ~30s.
- **Resource use**: measured 2026-08-26 on an 8-service .NET stack, the earlier "0.5–1 GB each" guess was ~2.5x too high. 8 idle services = 2832 MB total (~354 MB avg); the largest API service alone was 859 MB / 132 threads, the rest 172–416 MB. **RAM is rarely the ceiling — the shared local Postgres is.** Its default `max_connections = 100`, while those 8 services were configured to allow ~850 pooled connections together (one set `Maximum Pool Size=150`, the others took Npgsql's default of 100). Idle use hides this at ~13 connections per stack; under load, two stacks plus a test run can exhaust it. Before running stacks in parallel, lower `Maximum Pool Size` per service or raise `max_connections`.
- **Private NuGet feeds** require PAT. Skill surfaces NU1301 errors with guidance but cannot configure auth on user's behalf.
