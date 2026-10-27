#!/usr/bin/env python3
"""push-code local gate — Sonar rule issues on NEW code.

Reads the SARIF the SonarAnalyzer Roslyn analyzers wrote during `dotnet build`
(after `sonarscanner begin`) at <repo>/.sonarqube/out/*/Issues.json, and reports
each Sonar issue that falls on a line ADDED by the diff (base...HEAD).

No server, no upload, no Java — this is the analyzer output the CI PR analysis
would surface, read straight off disk.

Usage:  python parse-sonar-issues.py <repo_dir> <base_ref> [--exclude=<glob>,<glob>]
        --exclude: the CI workflow's sonar.exclusions (Sonar-style globs)

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

import fnmatch
# --exclude=<glob>[,<glob>...]: the CI workflow's sonar.exclusions. The analyzers run in the BUILD, so
# Issues.json holds findings for files the server later drops (EF migrations, Startup.cs). Without this
# a generated migration turned a clean change red with 49 S1192 (PROJ-8665, 2026-10-07). Same glob
# handling as parse-new-coverage.py.
EXCLUDES = []
for _a in list(sys.argv[1:]):
    if _a.startswith("--exclude="):
        EXCLUDES += [g.strip() for g in _a.split("=", 1)[1].split(",") if g.strip()]
        sys.argv.remove(_a)

def excluded(path):
    p = path.replace("\\", "/").lower()
    for g in EXCLUDES:
        g = g.lower()
        for cand in (g, g.replace("**/", "*/"), g.replace("**/", "")):
            if fnmatch.fnmatch(p, cand):
                return True
    return False

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

# Rules that anchor on the CLASS declaration but are caused by its MEMBERS. Adding a method to a busy
# controller raises them while the `class X` line is untouched, so an anchor-line check drops them and
# CI reports them as new. Observed 2026-08-21: CI raised S6960 and S6934 right after this gate printed
# "0 issues on new lines", and both fixes were at class level (split the controller, lift [Route] up).
#   S6960 controller with too many responsibilities · S6934 [Route] missing on the controller
#   S1200 class coupling · S1448 too many methods · S1820 too many fields · S110 inheritance depth
# NOT YET PROVEN on real SARIF - .sonarqube was deleted before the anchor line could be re-read. The
# class-span logic itself is covered by test-parse-sonar-issues.py.
CLASS_SCOPED_RULES = {"S6960", "S6934", "S1200", "S1448", "S1820", "S110"}

# Which rule ids this gate enforces.
#   S####  SonarC#            — the profile's own rules
#   CA#### Roslyn analyzers   — imported by the profile (e.g. CA1822 "mark static")
#   CS#### C# compiler        — imported by Sonar's ROSLYN engine and shown in the PR issue list,
#                               so CI raises them exactly like the other two (e.g. CS1573 missing
#                               <param> tag). Added 2026-08-05 after CI reported two CS1573 the
#                               gate had printed "0 issues on new lines" over.
# A PREFIX WHITELIST IS BLIND TO PREFIXES NOBODY LISTED — that is how CS#### was missed for
# months. So anything not matched here is COUNTED AND PRINTED (see UNGATED below) instead of
# dropped in silence. A new prefix then shows up as a visible number, not as a clean scan.
GATED_RULE = re.compile(r"^(?:S|CA|CS)\d+$")

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
skipped_by_exclude = set()
cur = None
for ln in diff.splitlines():
    m = re.match(r"^\+\+\+ b/(.+)$", ln)
    if m:
        cur = m.group(1) if m.group(1).endswith(".cs") else None
        if cur and excluded(cur):
            skipped_by_exclude.add(cur)
            cur = None
        continue
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
    if m and cur:
        s = int(m.group(1)); c = int(m.group(2)) if m.group(2) else 1
        added[cur].update(range(s, s + c))

def rel(uri):
    p = uri.replace("file:///", "").replace("\\", "/")
    rp = os.path.relpath(p, repo).replace("\\", "/")
    return rp

# ── The two measurement preconditions, enforced instead of merely documented ──────────────────
# sonar-local-gate.md says both in prose; prose did not bind (2026-08-21). Each one silently makes the
# numbers describe a different tree than the one being judged, so each is BLOCKED, never a finding.
dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                       capture_output=True, text=True).stdout.strip()
dirty = [ln for ln in dirty.splitlines()
         if ".sonarqube" not in ln and "coverage.xml" not in ln]
if dirty:
    listed = "; ".join(ln.strip() for ln in dirty[:8])
    blocked(f"{len(dirty)} tracked file(s) modified but not committed - the diff is computed from "
            f"{base}...HEAD while the analyzers read the WORKING TREE, so the two sides describe "
            f"different files: {listed}",
            "commit (or stash) the changes, then re-run begin + build + this parser")

sarif_files = glob.glob(os.path.join(repo, ".sonarqube", "out", "*", "Issues.json"))

if sarif_files:
    # `begin` ADDS a directory per run and never prunes, so a stale Issues.json is read alongside the
    # fresh one — that is how a finding already fixed came back as live.
    # Timestamps come from the files IN THE DIFF, not from a walk of src/: those are exactly the files
    # the verdict speaks about, it costs nothing, and it does not assume a repo layout.
    newest_src = 0.0
    for rp in added:
        try:
            newest_src = max(newest_src, os.path.getmtime(os.path.join(repo, rp)))
        except OSError:
            pass
    oldest_sarif = min(os.path.getmtime(f) for f in sarif_files)
    if newest_src and newest_src > oldest_sarif + 1:
        blocked(f"a source file is NEWER than the oldest of {len(sarif_files)} Issues.json — at least "
                "one SARIF is stale, and stale findings read exactly like live ones",
                "rm -rf .sonarqube, then re-run begin + build --no-incremental")
if not sarif_files:
    blocked("no .sonarqube/out/*/Issues.json — the analyzers never wrote any output",
            "run `sonarscanner begin` then `dotnet build` (a cached/no-op build produces no SARIF)")

issues = []
sarif_ok = 0
sarif_results = 0
ungated = collections.Counter()   # rule-id shape -> count, for the UNGATED line
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
            for loc in r.get("locations", []):
                rf = loc.get("resultFile") or {}
                uri = rf.get("uri", "")
                line = (rf.get("region") or {}).get("startLine") or rf.get("startLine")
                rp = rel(uri)
                if rp in added:
                    if not GATED_RULE.match(rule):
                        # NOT silently skipped — counted so an unlisted prefix cannot hide behind a
                        # clean verdict (see GATED_RULE). Only inside changed files, i.e. the scope
                        # this gate speaks for.
                        ungated[re.sub(r"\d+$", "####", rule) or "(no ruleId)"] += 1
                        break
                    isnew = line in added[rp]
                    # method-scoped rule: also gate if the change touched the member BODY
                    via_body = via_class = False
                    if not isnew and line and rule in METHOD_SCOPED_RULES:
                        span = member_span(rp, line)
                        if span and any(span[0] <= a <= span[1] for a in added[rp]):
                            isnew = via_body = True
                    # class-scoped rule: the anchor is the class line, the cause is anywhere inside it.
                    # Any added line at or after the anchor counts - a class body runs to end of file in
                    # every one-class-per-file C# file this repo has.
                    if not isnew and line and rule in CLASS_SCOPED_RULES:
                        if any(a >= line for a in added[rp]):
                            isnew = via_class = True
                    msg = (r.get("message") or "").strip()
                    if via_body:
                        msg += "  [member body changed by this diff]"
                    if via_class:
                        msg += "  [class gained members in this diff]"
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
      "non-.cs files  ·  pre-existing lines (listed below for context, not gated)"
      + (f"  ·  {len(skipped_by_exclude)} file(s) excluded by --exclude (CI does not analyse them): "
         + ", ".join(sorted(skipped_by_exclude)) if skipped_by_exclude else ""))
# The blindness guard: name every rule shape this gate declined to judge, with counts. An empty
# line here means "nothing was dropped", which is a claim; a populated one is a to-do, because a
# rule Sonar imports but this gate ignores will surface for the first time in CI.
if ungated:
    shapes = ", ".join(f"{k}×{v}" for k, v in ungated.most_common(8))
    print(f"UNGATED RULE SHAPES in changed files (not judged — check none of these is CI-enforced): {shapes}")
print()

print(f"Sonar issues on NEW lines: {len(new)}")
for _, rule, rp, line, lvl, msg in new:
    print(f"  [{rule}] {rp}:{line} ({lvl}) {msg[:160]}")
print(f"\nSonar issues on pre-existing lines in changed files (not gated): {len(old)}")
for _, rule, rp, line, lvl, msg in old[:40]:
    print(f"  [{rule}] {rp}:{line} ({lvl}) {msg[:120]}")
if len(old) > 40:
    print(f"  ... +{len(old) - 40} more")

sys.exit(1 if new else 0)
