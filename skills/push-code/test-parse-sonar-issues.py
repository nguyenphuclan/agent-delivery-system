#!/usr/bin/env python3
"""Red-first test for parse-sonar-issues.py rule-id gating.  Run: python test-parse-sonar-issues.py

Exists because the gate once printed "0 issues on new lines" over two real CS1573 that CI then
raised (PROJ-11247, 2026-08-05). The cause was a PREFIX WHITELIST: the parser kept S#### and
CA#### and dropped everything else in silence, so a rule shape nobody had listed was invisible.

Proven red first: against the pre-fix parser case 1 returns 0 (a false green); against the current
one it returns 1. Re-run this after ANY edit to the rule-id filter.

Builds a throwaway git repo + a hand-written SARIF, then asserts the exit code.
  case 1  CS1573 on an ADDED line       -> expect 1 (RED)
  case 2  CS1573 on a PRE-EXISTING line -> expect 0 (green, listed as context)
  case 3  IDE0051 on an ADDED line      -> expect 0, but PRINTED on the UNGATED line
  case 4  S1118 on an ADDED line        -> expect 1 (no regression on SonarC#)
"""
import json, os, shutil, subprocess, sys, tempfile, time

PARSER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parse-sonar-issues.py")

BASE_FILE = """namespace Demo
{
    public class Thing
    {
        private int _n;
    }
}
"""

# 3 lines appended -> added lines are 6,7,8 (1-indexed) in the new file
HEAD_FILE = """namespace Demo
{
    public class Thing
    {
        private int _n;
        public void Added(int a)
        {
        }
    }
}
"""


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout


def build_repo(tmp):
    repo = os.path.join(tmp, "repo")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "master")
    git(repo, "config", "user.email", "t@t.t")
    git(repo, "config", "user.name", "t")
    src = os.path.join(repo, "Thing.cs")
    open(src, "w").write(BASE_FILE)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "feature")
    open(src, "w").write(HEAD_FILE)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "head")
    return repo


def write_sarif(repo, rule, line):
    out = os.path.join(repo, ".sonarqube", "out", "0")
    os.makedirs(out, exist_ok=True)
    uri = "file:///" + os.path.join(repo, "Thing.cs").replace("\\", "/")
    doc = {"runs": [{"results": [{
        "ruleId": rule,
        "level": "warning",
        "message": f"seeded {rule}",
        "locations": [{"resultFile": {"uri": uri, "region": {"startLine": line}}}],
    }]}]}
    json.dump(doc, open(os.path.join(out, "Issues.json"), "w"))


def run_case(name, rule, line, expect_exit, expect_ungated=False,
             dirty=False, stale=False):
    tmp = tempfile.mkdtemp()
    try:
        repo = build_repo(tmp)
        write_sarif(repo, rule, line)
        if dirty:
            # a tracked file edited but not committed: the diff reads HEAD, the analyzers read the tree
            with open(os.path.join(repo, "Thing.cs"), "a") as f:
                f.write("// uncommitted" + chr(10))
        if stale:
            # make the source newer than the SARIF, i.e. at least one Issues.json is from a past build
            os.utime(os.path.join(repo, "Thing.cs"), (time.time() + 60, time.time() + 60))
        p = subprocess.run([sys.executable, PARSER, repo, "master"],
                           capture_output=True, text=True)
        ok = p.returncode == expect_exit
        ung = "UNGATED RULE SHAPES" in p.stdout
        if expect_ungated and not ung:
            ok = False
        if not expect_ungated and ung:
            ok = False
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: exit {p.returncode} (want {expect_exit}), "
              f"ungated-line={ung} (want {expect_ungated})")
        if not ok:
            print("--- stdout ---")
            print(p.stdout)
            print(p.stderr)
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


results = [
    run_case("CS1573 on ADDED line -> RED", "CS1573", 6, 1),
    run_case("CS1573 on PRE-EXISTING line -> green", "CS1573", 4, 0),
    run_case("IDE0051 on ADDED line -> green but VISIBLE", "IDE0051", 6, 0, expect_ungated=True),
    run_case("S1118 on ADDED line -> RED (no regression)", "S1118", 6, 1),

    # class-scoped: the anchor sits on a PRE-EXISTING line and the diff only adds members below it.
    # An anchor-line check calls that green; CI calls it new. This is the S6960 / S6934 shape.
    run_case("S6960 anchored on a PRE-EXISTING class line, members added -> RED", "S6960", 4, 1),
    run_case("S6960 anchored BELOW every added line -> green", "S6960", 99, 0),

    # the two measurement preconditions: BLOCKED (2), never a finding and never green
    run_case("dirty tree -> BLOCKED", "CS1573", 6, 2, dirty=True),
    run_case("stale Issues.json -> BLOCKED", "CS1573", 6, 2, stale=True),
]
print()
print("ALL PASS" if all(results) else "SOME FAILED")
sys.exit(0 if all(results) else 1)
