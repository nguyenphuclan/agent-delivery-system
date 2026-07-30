#!/usr/bin/env python3
"""push-code local gate — Sonar rule issues on NEW code.

Reads the SARIF the SonarAnalyzer Roslyn analyzers wrote during `dotnet build`
(after `sonarscanner begin`) at <repo>/.sonarqube/out/*/Issues.json, and reports
each Sonar issue that falls on a line ADDED by the diff (base...HEAD).

No server, no upload, no Java — this is the analyzer output the CI PR analysis
would surface, read straight off disk.

Usage:  python parse-sonar-issues.py <repo_dir> <base_ref>

Exit codes (see _shared/measurement-integrity-protocol.md):
  0  clean  — the scan ran over a non-zero scope and found no issue on new lines
  1  RED    — at least one issue lands on a new line
  2  BLOCKED — the measurement did not happen (bad base ref, no analyzer output,
               unreadable SARIF). NEVER reported as clean: a scan with an empty
               input finds no problems quite honestly, and that must not look
               like a pass. Fix the measurement and re-run.
"""
import json, glob, subprocess, re, os, sys, collections

# Windows consoles default to cp1252 and die on the ∩ / box characters below; an encoding
# crash exits 1, which the caller would read as "issues found" rather than "script broke".
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLOCKED = 2
def blocked(reason, fix):
    print(f"BLOCKED — measurement did not happen: {reason}")
    print(f"  fix: {fix}")
    print("  This is a verdict on the MEASUREMENT, not on the code. Do not push on it.")
    sys.exit(BLOCKED)

repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
base = sys.argv[2] if len(sys.argv) > 2 else "origin/master"

if not os.path.isdir(os.path.join(repo, ".git")) and not os.path.isfile(os.path.join(repo, ".git")):
    blocked(f"{repo} is not a git repository", "pass the repo root as <repo_dir>")

# Rules that anchor on a member DECLARATION line but are actually "caused by" the member
# BODY. A change that edits the body (raising complexity / length) without touching the
# declaration line leaves the anchor line unchanged, so a pure anchor-line check misses it
# even though CI attributes it to new code. For these, gate when any ADDED line falls inside
# the member's brace span, not only when the anchor line itself is added.
#   S3776 cognitive complexity · S1541 cyclomatic · S138 method length ·
#   S134 nesting depth · S1067 expression complexity · S103 line length (whole file)
METHOD_SCOPED_RULES = {"S3776", "S1541", "S138", "S134", "S1067"}

_file_cache = {}
def _file_lines(rp):
    if rp not in _file_cache:
        try:
            _file_cache[rp] = open(os.path.join(repo, rp), encoding="utf-8-sig").read().splitlines()
        except Exception:
            _file_cache[rp] = []
    return _file_cache[rp]

def _strip(line):
    # remove line comments + string/char literal contents so their braces are not counted
    line = re.sub(r"//.*$", "", line)
    line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
    line = re.sub(r"'(?:[^'\\]|\\.)*'", "''", line)
    return line

def member_span(rp, decl_line):
    """Brace-match from the declaration line to the member's closing brace → (start, end)."""
    lines = _file_lines(rp)
    n = len(lines)
    if not (1 <= decl_line <= n):
        return None
    depth, started, i = 0, False, decl_line
    while i <= n:
        for ch in _strip(lines[i - 1]):
            if ch == "{":
                depth += 1; started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return (decl_line, i)
        i += 1
    return (decl_line, n)

# changed .cs files + their added-line numbers (base...HEAD)
_p = subprocess.run(["git", "-C", repo, "diff", "-U0", f"{base}...HEAD"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
# A bad base ref is the #1 silent zero here: git exits non-zero, stdout is empty, and every
# downstream count becomes 0 — which prints as a clean scan.
if _p.returncode != 0:
    blocked(f"git diff {base}...HEAD failed (exit {_p.returncode}): {(_p.stderr or '').strip()[:200]}",
            f"check that '{base}' exists (git fetch, or correct base_branch in config)")
diff = _p.stdout or ""
if not diff.strip():
    blocked(f"git diff {base}...HEAD produced an empty diff",
            "wrong base ref, wrong repo dir, or the branch is already merged — there is nothing to scan")
added = collections.defaultdict(set)   # repo-rel path -> {line}
cur = None
for ln in diff.splitlines():
    m = re.match(r"^\+\+\+ b/(.+)$", ln)
    if m:
        cur = m.group(1) if m.group(1).endswith(".cs") else None
        continue
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
    if m and cur:
        s = int(m.group(1)); c = int(m.group(2)) if m.group(2) else 1
        added[cur].update(range(s, s + c))

def rel(uri):
    p = uri.replace("file:///", "").replace("\\", "/")
    rp = os.path.relpath(p, repo).replace("\\", "/")
    return rp

sarif_files = glob.glob(os.path.join(repo, ".sonarqube", "out", "*", "Issues.json"))
if not sarif_files:
    blocked("no .sonarqube/out/*/Issues.json — the analyzers never wrote any output",
            "run `sonarscanner begin` then `dotnet build` (a cached/no-op build produces no SARIF)")

issues = []
sarif_ok = 0
sarif_results = 0
for f in sarif_files:
    try:
        data = json.load(open(f, encoding="utf-8-sig"))
    except Exception as e:
        print(f"  warning: unreadable SARIF {os.path.basename(os.path.dirname(f))}/Issues.json — {e}")
        continue
    sarif_ok += 1
    for run in data.get("runs", []):
        sarif_results += len(run.get("results", []))
    for run in data.get("runs", []):
        for r in run.get("results", []):
            rule = r.get("ruleId", "")
            # Gate SonarC# (S####) AND external Roslyn analyzer rules (CA####) — both live in the
            # SonarQube quality profile, so CI's PR analysis enforces them (e.g. CA1822 "mark static").
            # Skip pure compiler diagnostics (CSxxxx) and anything else the profile does not gate.
            if not (rule.startswith("S") or rule.startswith("CA")):
                continue
            for loc in r.get("locations", []):
                rf = loc.get("resultFile") or {}
                uri = rf.get("uri", "")
                line = (rf.get("region") or {}).get("startLine") or rf.get("startLine")
                rp = rel(uri)
                if rp in added:
                    isnew = line in added[rp]
                    # method-scoped rule: also gate if the change touched the member BODY
                    via_body = False
                    if not isnew and line and rule in METHOD_SCOPED_RULES:
                        span = member_span(rp, line)
                        if span and any(span[0] <= a <= span[1] for a in added[rp]):
                            isnew = via_body = True
                    msg = (r.get("message") or "").strip()
                    if via_body:
                        msg += "  [member body changed by this diff]"
                    issues.append((isnew, rule, rp, line, r.get("level"), msg))
                    break

if sarif_ok == 0:
    blocked(f"all {len(sarif_files)} Issues.json file(s) were unreadable",
            "delete .sonarqube and re-run begin + build")

issues = sorted(set(issues), key=lambda x: (not x[0], x[2], x[3] or 0))
new = [i for i in issues if i[0]]
old = [i for i in issues if not i[0]]

# I1 — the verdict never ships without its scope. A bare "0 issues" is indistinguishable
# from a scan that opened nothing; these numbers are what make the empty case look different.
cs_files = len(added)
cs_lines = sum(len(v) for v in added.values())
print("SCOPE  " + f"{cs_files} changed .cs file(s), {cs_lines} added line(s) vs {base}  ·  "
      f"{sarif_ok}/{len(sarif_files)} SARIF file(s) read, {sarif_results} analyzer result(s) parsed")
if cs_files == 0:
    print("       no changed .cs files in this diff → nothing for SonarC# to gate (n/a, not a pass)")
print("NOT EXAMINED  duplication-on-new-code (needs the server upload — deferred to CI)  ·  "
      "non-.cs files  ·  pre-existing lines (listed below for context, not gated)\n")

print(f"Sonar issues on NEW lines: {len(new)}")
for _, rule, rp, line, lvl, msg in new:
    print(f"  [{rule}] {rp}:{line} ({lvl}) {msg[:160]}")
print(f"\nSonar issues on pre-existing lines in changed files (not gated): {len(old)}")
for _, rule, rp, line, lvl, msg in old[:40]:
    print(f"  [{rule}] {rp}:{line} ({lvl}) {msg[:120]}")
if len(old) > 40:
    print(f"  ... +{len(old) - 40} more")

sys.exit(1 if new else 0)
