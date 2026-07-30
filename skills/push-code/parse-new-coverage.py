#!/usr/bin/env python3
"""push-code local gate — coverage on NEW code.

Computes coverage of the lines ADDED by the diff (base...HEAD) from the
dotnet-coverage XML report, for the changed PRODUCTION files (skips test
projects). "New code" is the git diff itself, so this needs no Sonar server and
no branch baseline.

A new line counts as:
  - executable  if any <range> touches it (comments/blank/braces have no range)
  - covered     if any touching range is covered="yes" or "partial"
new-code coverage = covered_new / executable_new.

Usage:  python parse-new-coverage.py <repo_dir> <base_ref> <coverage.xml> [min_pct] [test_marker]
        test_marker: path substring marking test projects to exclude (default ".MSTest")

Exit codes (see _shared/measurement-integrity-protocol.md):
  0  clean  — coverage measured over a non-zero denominator and met the gate
  1  RED    — new-code coverage below min_pct
  2  BLOCKED — the measurement did not happen (bad base ref, missing/unreadable
               coverage.xml, or a report that covers none of the changed files).
               Coverage over zero lines is 0/0 = 100%, which is the single most
               convincing false green in this pipeline. It is never reported as a pass.
"""
import xml.etree.ElementTree as ET, subprocess, re, os, sys, collections

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
cov  = sys.argv[3] if len(sys.argv) > 3 else os.path.join(repo, "coverage.xml")
minp = float(sys.argv[4]) if len(sys.argv) > 4 else 80.0
testmark = (sys.argv[5] if len(sys.argv) > 5 else ".mstest").lower()

if not os.path.isfile(cov):
    blocked(f"coverage report not found at {cov}",
            "run the dotnet-coverage step; a missing report is not 0% and not 100%")
if os.path.getsize(cov) == 0:
    blocked(f"coverage report is empty (0 bytes): {cov}",
            "the coverage run produced no output — re-run it before parsing")

# added lines for changed PRODUCTION .cs files (exclude test projects)
_p = subprocess.run(["git", "-C", repo, "diff", "-U0", f"{base}...HEAD"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace")
if _p.returncode != 0:
    blocked(f"git diff {base}...HEAD failed (exit {_p.returncode}): {(_p.stderr or '').strip()[:200]}",
            f"check that '{base}' exists (git fetch, or correct base_branch in config)")
diff = _p.stdout or ""
if not diff.strip():
    blocked(f"git diff {base}...HEAD produced an empty diff",
            "wrong base ref, wrong repo dir, or the branch is already merged")
added = collections.defaultdict(set)
cur = None
for ln in diff.splitlines():
    m = re.match(r"^\+\+\+ b/(.+)$", ln)
    if m:
        p = m.group(1)
        cur = p if (p.endswith(".cs") and testmark not in p.lower()) else None
        continue
    m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", ln)
    if m and cur:
        s = int(m.group(1)); c = int(m.group(2)) if m.group(2) else 1
        added[cur].update(range(s, s + c))

if not added:
    # Legitimate n/a: the diff is real but touches no production .cs (docs, yaml, tests only).
    # Reported as n/a with its scope, never as a percentage — there is no denominator to divide by.
    print(f"SCOPE  diff vs {base} is non-empty but contains 0 changed production .cs files "
          f"(test_marker='{testmark}')")
    print("NEW-CODE COVERAGE: n/a — nothing to measure. Not a pass, not a failure.")
    sys.exit(0)

def norm(p): return p.replace("\\", "/").lower()
want = {norm(os.path.join(repo, p)): p for p in added}

# PASS 1: (module_idx, source_id) -> repo-rel path, for our files only
targets = {}; mod = -1
for ev, el in ET.iterparse(cov, events=("start", "end")):
    if ev == "start" and el.tag == "module":
        mod += 1
    elif ev == "end" and el.tag == "source_file":
        p = norm(el.get("path", ""))
        if p in want:
            targets[(mod, el.get("id"))] = want[p]
        el.clear()

# The discriminator between "genuinely no executable new lines" and "this report never saw these
# files at all". Both end as 0/0; only the first is a real n/a. If the report knows none of the
# changed files, the coverage run targeted the wrong assemblies / ran no tests — measurement failure.
if not targets:
    blocked(f"coverage report covers NONE of the {len(added)} changed production file(s) — "
            f"no matching <source_file> in {os.path.basename(cov)}",
            "the coverage run targeted different assemblies, or no test touched these files; "
            "0/0 would print as 100%, so this is BLOCKED rather than a pass")

# PASS 2: executable / covered line sets per file
execu = collections.defaultdict(set); covered = collections.defaultdict(set); mod = -1
for ev, el in ET.iterparse(cov, events=("start", "end")):
    if ev == "start" and el.tag == "module":
        mod += 1
    elif ev == "end" and el.tag == "range":
        rp = targets.get((mod, el.get("source_id")))
        if rp:
            s = int(el.get("start_line")); e = int(el.get("end_line"))
            c = el.get("covered")
            for L in range(s, e + 1):
                execu[rp].add(L)
                if c in ("yes", "partial"):
                    covered[rp].add(L)
        el.clear()

tot_ex = tot_cv = 0
print(f"SCOPE  {len(added)} changed production .cs file(s), "
      f"{sum(len(v) for v in added.values())} added line(s) vs {base}  ·  "
      f"{len(targets)} file(s) found in {os.path.basename(cov)}")
print(f"NOT EXAMINED  test projects (marker '{testmark}')  ·  non-.cs files  ·  "
      f"non-executable added lines (comments, braces, usings)\n")
print("New-code coverage (from coverage.xml ∩ diff):\n")
for rp in sorted(added):
    a = added[rp]; ex = execu[rp] & a; cv = covered[rp] & a
    tot_ex += len(ex); tot_cv += len(cv)
    base_name = os.path.basename(rp)
    if ex:
        uncov = sorted(ex - cv)
        pct = 100.0 * len(cv) / len(ex)
        print(f"  {base_name}: {len(cv)}/{len(ex)} = {pct:.1f}%" +
              (f"   uncovered new lines: {uncov}" if uncov else "  (all covered)"))
    else:
        print(f"  {base_name}: no new executable lines")

if tot_ex == 0:
    # The report DOES know these files (targets is non-empty), so this is a real n/a: the added
    # lines carry no executable ranges. Print it as n/a — never as the 100% that 0/0 would yield.
    print(f"\nNEW-CODE COVERAGE: 0/0 = n/a — the {len(targets)} file(s) are in the report but none "
          f"of the added lines are executable (comments / usings / generated designer code).")
    print(f"       Not a pass and not a failure. Gate (>= {minp:.0f}%) does not apply.")
    sys.exit(0)

overall = 100.0 * tot_cv / tot_ex
print(f"\nNEW-CODE COVERAGE: {tot_cv}/{tot_ex} = {overall:.1f}%   (gate >= {minp:.0f}%)")
sys.exit(0 if overall >= minp else 1)
