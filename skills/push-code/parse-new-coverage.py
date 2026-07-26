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
Exit 1 if below min_pct (default 80).
"""
import xml.etree.ElementTree as ET, subprocess, re, os, sys, collections

repo = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
base = sys.argv[2] if len(sys.argv) > 2 else "origin/master"
cov  = sys.argv[3] if len(sys.argv) > 3 else os.path.join(repo, "coverage.xml")
minp = float(sys.argv[4]) if len(sys.argv) > 4 else 80.0
testmark = (sys.argv[5] if len(sys.argv) > 5 else ".mstest").lower()

# added lines for changed PRODUCTION .cs files (exclude test projects)
diff = subprocess.run(["git", "-C", repo, "diff", "-U0", f"{base}...HEAD"],
                      capture_output=True, text=True, encoding="utf-8", errors="replace").stdout or ""
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
    print("No changed production .cs files in the diff — new-code coverage is vacuously N/A.")
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

overall = (100.0 * tot_cv / tot_ex) if tot_ex else 100.0
print(f"\nNEW-CODE COVERAGE: {tot_cv}/{tot_ex} = {overall:.1f}%   (gate >= {minp:.0f}%)")
sys.exit(0 if (tot_ex == 0 or overall >= minp) else 1)
