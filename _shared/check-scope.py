#!/usr/bin/env python3
"""Runnable preflight for measurement integrity — `_shared/measurement-integrity-protocol.md`.

Prose gates ("state the scope", "an empty result is BLOCKED") are principle-rules: they never
visibly clash and never die, so nobody finds out when one stops being applied. This script turns
the mechanical half of each into a checkable-rule that dies loudly.

Every mode answers one question: **is the thing about to be measured actually non-empty, and does
its size match what was declared?** It never inspects quality — only that a measurement can happen.

Modes
  diff <repo> <base_ref>                 changed files + added lines vs base_ref
  glob <root> <pattern> [pattern...]     files matching at least one pattern (** supported)
  files <path> [path...]                 every path exists and is non-empty
  reconcile <declared> <observed> [label]  declared count equals observed count

Exit codes
  0  scope is non-empty (and reconciled) — the gate may proceed and must print the SCOPE line below
  2  BLOCKED — nothing to measure, or a count mismatch. Never a pass, never a failure of the subject.

Exit 1 is deliberately unused: this script never judges the subject, only the measurement.
"""
import glob as globmod
import os
import subprocess
import sys

BS = chr(92)
BLOCKED = 2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def blocked(reason, fix):
    print(f"BLOCKED — nothing to measure: {reason}")
    print(f"  fix: {fix}")
    print("  A gate whose input is empty reports no problems quite honestly. Do not record a pass.")
    sys.exit(BLOCKED)


def ok(scope_line, not_examined=None):
    print(f"SCOPE  {scope_line}")
    if not_examined:
        print(f"NOT EXAMINED  {not_examined}")
    sys.exit(0)


def mode_diff(argv):
    repo = os.path.abspath(argv[0] if argv else ".")
    base = argv[1] if len(argv) > 1 else "origin/master"
    if not os.path.exists(os.path.join(repo, ".git")):
        blocked(f"{repo} is not a git repository", "pass the repo root")
    p = subprocess.run(["git", "-C", repo, "diff", "--numstat", f"{base}...HEAD"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        blocked(f"git diff {base}...HEAD failed (exit {p.returncode}): {(p.stderr or '').strip()[:200]}",
                f"check that '{base}' exists — git fetch, or correct the base branch")
    rows = [r for r in (p.stdout or "").splitlines() if r.strip()]
    if not rows:
        blocked(f"git diff {base}...HEAD is empty — 0 changed files",
                "wrong base ref, wrong repo dir, unstaged work, or the branch is already merged")
    add = dele = 0
    for r in rows:
        parts = r.split("\t")
        if len(parts) >= 2:
            add += int(parts[0]) if parts[0].isdigit() else 0
            dele += int(parts[1]) if parts[1].isdigit() else 0
    if add == 0:
        # Deletion-only diffs are real work, but a gate that only inspects ADDED lines has no
        # input. Say which it is rather than printing "0 findings".
        blocked(f"{len(rows)} changed file(s) but 0 added lines (deletion-only diff)",
                "a gate scoped to added lines has nothing to inspect — review the deletions by hand")
    ok(f"{len(rows)} changed file(s), +{add}/-{dele} lines vs {base}")


def mode_glob(argv):
    if len(argv) < 2:
        blocked("glob mode needs <root> and at least one pattern", "see the usage block")
    root, pats = argv[0], argv[1:]
    hits = []
    for pat in pats:
        hits.extend(globmod.glob(os.path.join(root, pat), recursive=True))
    hits = sorted({h for h in hits if os.path.isfile(h)})
    if not hits:
        blocked(f"no files match {pats} under {root}",
                "wrong root, wrong pattern, or an exclusion rule swallowed the tree — "
                "a walk that matched nothing yields 0/0, which prints as 100%")
    ok(f"{len(hits)} file(s) matched {len(pats)} pattern(s) under {root}")


def mode_files(argv):
    if not argv:
        blocked("files mode needs at least one path", "see the usage block")
    missing = [p for p in argv if not os.path.isfile(p)]
    empty = [p for p in argv if os.path.isfile(p) and os.path.getsize(p) == 0]
    if missing:
        blocked(f"{len(missing)} of {len(argv)} required artefact(s) absent: "
                f"{', '.join(os.path.basename(m) for m in missing[:5])}",
                "the step that produces them did not run — do not report on evidence you do not have")
    if empty:
        blocked(f"{len(empty)} of {len(argv)} artefact(s) are 0 bytes: "
                f"{', '.join(os.path.basename(e) for e in empty[:5])}",
                "the producing step ran but wrote nothing")
    total = sum(os.path.getsize(p) for p in argv)
    ok(f"{len(argv)} artefact(s) present, {total} bytes total")


def mode_reconcile(argv):
    if len(argv) < 2:
        blocked("reconcile mode needs <declared> <observed>", "see the usage block")
    try:
        declared, observed = int(argv[0]), int(argv[1])
    except ValueError:
        blocked(f"non-numeric counts: declared={argv[0]!r} observed={argv[1]!r}",
                "pass integers — a count you cannot parse is a count you did not make")
    label = argv[2] if len(argv) > 2 else "items"
    if declared == 0:
        blocked(f"declared 0 {label} — the denominator is zero",
                "a partial or failed parse looks identical to an empty input; re-read the source")
    if declared != observed:
        blocked(f"declared {declared} {label} but accounted for {observed} "
                f"({declared - observed:+d} unaccounted)",
                "a partial read (wrong delimiter, newline inside a quoted cell, extra header row) "
                "silently shrinks the set — re-parse before reporting")
    ok(f"{observed}/{declared} {label} accounted for")


MODES = {"diff": mode_diff, "glob": mode_glob, "files": mode_files, "reconcile": mode_reconcile}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        print(__doc__)
        print(f"error: first argument must be one of {', '.join(MODES)}")
        sys.exit(BLOCKED)
    MODES[sys.argv[1]](sys.argv[2:])
