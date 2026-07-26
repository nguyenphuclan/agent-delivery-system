# push-code — one-time local setup

Do this once per machine. Until it's done, `push-code` fails at the pre-flight prereq-check (G-TOOLCHAIN) and will not run — by design, so the Sonar gate is never silently skipped. **The user performs the credential steps** (obtaining and pasting the SonarQube token). The agent must never handle the token value.

## What / why

| Piece | Why it's needed | Known-good version |
|-------|-----------------|--------------------|
| **`dotnet-sonarscanner`** global tool | `begin` injects the SonarAnalyzer Roslyn analyzers into the build | 11.2.1 |
| **`dotnet-coverage`** global tool | Produces `coverage.xml` | 18.9.0 |
| **`python`** | Runs the two gate parsers (`parse-sonar-issues.py`, `parse-new-coverage.py`) | 3.14 |
| **Personal SonarQube user token** in `SONAR_TOKEN` | `begin` fetches the quality profile from the server (your own token, not the CI secret) | — (validate → `{"valid":true}`) |
| **Sonar server reachable** (`curl`) | Same — `begin`'s profile fetch; also the prereq smoke test | host from `projects.<active>.sonar.host` |
| `dotnet` SDK | Build/test | 10.0.301 |
| ~~JDK / Java~~ | Only the server-**upload** step (`end`) uses Java — **not part of this gate** | not required (and `end` is blocked on a sandboxed host — see §Blocked) |

## Steps

### 1. Install the scanner tools
```
dotnet tool install --global dotnet-sonarscanner
dotnet tool install --global dotnet-coverage
```
(These match the CI workflow's tools.)

### 2. Create a personal SonarQube token
On the Sonar server (host is in `projects.<active>.sonar.host`): **My Account → Security → Generate Token** (type: *User* or *Global Analysis*). Copy it once.

### 3. Store the token — as an env var, NOT in any committed file
Set the env var named by `projects.<active>.sonar.token_env` (default `SONAR_TOKEN`). Example (PowerShell, persistent for your user):
```
setx SONAR_TOKEN "<paste-your-token>"
```
Restart the shell so it's in the environment. The token never goes into `projects.yaml`, the skill, or any tracked file — only the **env-var name** is stored in config.

### 4. Verify
```
dotnet-sonarscanner --version && dotnet-coverage --version && python --version
# token + server smoke test (token NOT printed):
curl -s -u "$SONAR_TOKEN:" https://sonarqube.acme.com/api/authentication/validate   # → {"valid":true}
```
All green → `/push-code` runs the full local gate.

## §Blocked — why there is no server upload / Web-API read-back / MCP on a sandboxed host

> This section documents an environment limitation, not a design preference. On an unrestricted machine the upload path works and you can add the duplication gate; on a **managed/sandboxed workstation** (endpoint-management agent, restricted loopback) it does not, and this is the dead end to stop re-discovering.

The upload step (`sonarscanner end`) runs a Java "scanner engine" whose `HttpClient` opens an NIO selector loopback self-pipe (`Selector.open()` → `PipeImpl` → `UnixDomainSockets.connect0`). A sandbox that **blocks that loopback** fails it (`Invalid argument: connect`). Confirmed 2026-07-21 on such a host:
- Fails **identically with the Claude sandbox disabled** → it is the machine, not Claude.
- Fails at **every scanner version** — v11 (scanner engine) and the classic v9 CLI both upload through Java HTTP.
- The SonarQube **MCP server** (stdio) fails to launch for the same reason (Claude issue [#41432](https://github.com/anthropics/claude-code/issues/41432)); `-Djava.nio.preferPipe=false` etc. do not help.

Consequence: nothing is uploaded, so there is no server-side quality gate to read (over the Web API or the MCP). The gate is computed **from local files only** (`Issues.json` + `coverage.xml`). Duplication-on-new-code, which needs the server, is left to CI's PR analysis. **Do not reintroduce `end` / curl-read-back / the MCP as a required step on such a host** — they were tried and do not work. (On an unrestricted machine the upload path works and could add the duplication gate; keep it optional, never a prerequisite, so the gate still runs where the loopback is blocked.)
