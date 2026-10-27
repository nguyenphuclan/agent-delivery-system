#!/usr/bin/env python3
"""Refuse to pass a gate when a declared artifact is not on disk.

Why this is a script and not another paragraph in a SKILL.md
------------------------------------------------------------
2026-08-21: three gates were already written as prose, in three places, and all
three were walked past in one session. Writing the rule a fourth time would not
bind either. A rule that keeps being skipped has to be enforced by the thing that
runs.

On 2026-08-27 the same shape repeated: `code-quality-review.md` was missing at
commit-ready, `implement-summary.md` was missing when the PR description asked for
it, and `run-telemetry.yaml` was never written at all. The first fix attempted
was, again, prose. This file is the fix that can actually fail.

Known limits -- read a PASS as "the record exists", not "the work was done"
---------------------------------------------------------------------------
This checker has failed OPEN three times, in three different ways. Each one was
patched, but the shape of the risk remains:
  1. An artifact was only tested for "parses", so a run-telemetry.yaml with empty
     phases and a null end time printed `ok`. (Now: telemetry must hold phases.)
  2. The scope check took the largest number near the top of the file, so a number
     quoted from another section counted as scope. (Now: it prefers the file's own
     Scope section.)
  3. It cannot tell WHICH change a review covered. A second change on the same
     ticket could inherit the first one's tick. (Now: it reads the LAST Scope
     section, but it still cannot match that section to the diff.)
Each time, the miss was caught by reading the artifact. So after a PASS, open the
artifact and check it describes the change in front of you.

Exit codes, matching the other gate tools in this folder:
    0  every required artifact is present and non-empty
    2  BLOCKED -- something declared is missing, or present but measured nothing

There is no exit 1. This tool never judges the CONTENT of your work, only
whether the record of it exists.

Usage
-----
    python check_artifacts.py <ticket_dir> <gate> [--type <ticket_type>]

    gates:  pre-commit | pre-push | pr | done
    types:  crud-feature (default) | bugfix-small | bugfix-investigated
            | bugfix-regression | hotfix | refactor | spike | doc-only
            | migration-only | fe-only        (see do-ticket/ticket-types.md)

Stdlib only (PyYAML is used when present). No install step, so nothing stands
between the gate and running it.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# The manifest. Data, not code, so a phase owner can edit it without reading
# Python. Each entry: (filename, why it exists, scope_check).
#
# scope_check is the second half of the lesson. A file that exists but measured
# nothing prints the same tick as a real one -- an empty-diff review, a coverage
# report over zero lines. Where a file is supposed to carry a measurement, we
# look for a number in it and refuse a zero.
# --------------------------------------------------------------------------

SCOPE_RE = re.compile(r"(\d[\d,]*)\s*(?:added\s+line|file|test|line|case|row)", re.I)
SCOPE_HEADING_RE = re.compile(r"^#{1,4}\s*(?:\d+[.)]\s*)?scope\b.*$", re.I | re.M)
EXCLUDED_LINE_RE = re.compile(r"\b(?:excluded|generated|ignored|skipped|not\s+reviewed)\b", re.I)
BARE_NUM_RE = re.compile(r"(?<![A-Za-z0-9_])(\d[\d,]*)(?![A-Za-z0-9_])")
CODE_SPAN_RE = re.compile(r"`[^`]*`")

REQUIRED = {
    # PROJ-10837: this list held 2 files while phases/verify.md called 5 mandatory, so the
    # gate printed PASS over a run with no telemetry, no regression count and no evidence.
    "pre-commit": [
        ("code-quality-review.md", "the diff-scoped quality review (do-ticket 13.5)", True),
        ("plan.md", "what was going to be built, and the options rejected", False),
        ("run-telemetry.yaml", "phases/verify.md 16: must exist before the commit prompt", "telemetry"),
        ("implement-summary.md", "Phase 12: the runner's own 'Regression: N passed, 0 failed' line", "regression"),
        ("test-evidence", "Phase 15: a flow is verified only if its request/response is on disk", "evidence"),
        ("legacy-contract.md", "Phase 9.8: required while ticket-context armed_gates is non-empty", "if-armed"),
    ],
    "pre-push": [
        ("code-quality-review.md", "the quality review push-code asks for", True),
        ("run-telemetry.yaml", "the only input /learn D8 has; absent = no cross-ticket learning", "telemetry"),
    ],
    "pr": [
        ("plan.md", "implementation intent, read by pr-description", False),
        ("implement-summary.md", "what was actually changed, read by pr-description", False),
    ],
    "done": [
        ("run-telemetry.yaml", "phase outcomes + failure modes for /learn", "telemetry"),
        ("implement-summary.md", "the as-built record", False),
    ],
}

# Types that genuinely skip a phase, per do-ticket/ticket-types.md. Listed so a
# legitimate skip is a stated fact rather than a silent pass.
SKIPS = {
    "doc-only": {"code-quality-review.md", "implement-summary.md", "test-evidence"},
    "spike": {"code-quality-review.md", "implement-summary.md", "test-evidence"},
    "hotfix": {"code-quality-review.md", "test-evidence"},
    # these types do not run api-test (phases/verify.md, Phase 15 skip list)
    "refactor": {"test-evidence"},
    "bugfix-small": {"test-evidence"},
    "bugfix-regression": {"test-evidence"},   # ticket-types.md: same phases as bugfix-small
    "migration-only": {"test-evidence"},
    "fe-only": {"test-evidence"},
    "crud-feature": set(),
    "bugfix-investigated": set(),
}

REGRESSION_RE = re.compile(r"Regression:\s*([\d,]+)\s+passed,\s*([\d,]+)\s+failed", re.I)


def _yaml(path: Path):
    try:
        import yaml  # noqa: PLC0415 - optional
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - absent / unparsable reads as empty here; parses() reports it
        return {}


def regression_counted(path: Path) -> tuple[bool, str]:
    """Phase 12: a prose 'PASS' is not evidence -- the runner's count is. Every
    'Regression:' line must show passed > 0 and failed == 0."""
    lines = REGRESSION_RE.findall(path.read_text(encoding="utf-8", errors="replace"))
    if not lines:
        return False, "no 'Regression: N passed, M failed' line -- prose PASS is not a count"
    counts = [(int(p.replace(",", "")), int(f.replace(",", ""))) for p, f in lines]
    bad = [c for c in counts if c[0] == 0 or c[1] > 0]
    if bad:
        return False, f"regression line(s) not green or measured nothing: {bad}"
    return True, f"{len(counts)} regression line(s), passed {[c[0] for c in counts]}"


def evidence_on_disk(path: Path) -> tuple[bool, str]:
    """Phase 15: at least one flow folder with a 02_response.txt that states what was observed."""
    responses = [p for p in path.rglob("02_response.txt")
                 if "Observed:" in p.read_text(encoding="utf-8", errors="replace")]
    if not responses:
        return False, "no flow folder with a 02_response.txt carrying an 'Observed:' line"
    return True, f"{len(responses)} flow(s) with observed responses"


def phase_skipped(d: Path, phase: str) -> bool:
    """The user may defer a phase explicitly; that skip is logged in run-telemetry skipped_phases."""
    skipped = _yaml(d / "run-telemetry.yaml").get("skipped_phases") or []
    return any((s.get("phase") if isinstance(s, dict) else s) == phase for s in skipped)


def gates_armed(d: Path) -> bool:
    return bool(_yaml(d / "ticket-context.yaml").get("armed_gates"))


def telemetry_filled(path: Path) -> tuple[bool, str]:
    """run-telemetry.yaml is pure measurement, so `parses` proves nothing about it.
    A file with phases: [] is the exact failure this tool exists for -- present,
    well-formed, and recording nothing. Observed on PROJ-11417, which passed this
    gate with every list empty, ticket_type null and ended_at null."""
    try:
        import yaml  # noqa: PLC0415 - optional; absent means we simply skip the check
    except ImportError:
        return True, "(pyyaml absent, fill not checked)"
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - any parse failure is the same verdict
        return False, f"does not parse: {str(e).strip().splitlines()[0][:90]}"
    phases = loaded.get("phases") or []
    if not phases:
        return False, "phases: [] -- the run recorded no phase, so /learn D8 has no input"
    # PROJ-11212: 5 entries in 3 tickets used `fm:` / `mode:` instead of the schema's `id:`, so the
    # cross-ticket failure-mode statistics silently skipped them.
    bad = [f for f in (loaded.get("failure_modes_hit") or [])
           if not (isinstance(f, dict) and str(f.get("id") or "").startswith("FM-"))]
    if bad:
        return False, (f"{len(bad)} failure_modes_hit entr{'y' if len(bad) == 1 else 'ies'} without `id: FM-...` "
                       "(schema key is `id`, not `fm`/`mode`)")
    note = f"{len(phases)} phase(s)"
    if not loaded.get("ticket_type"):
        note += ", ticket_type still null"
    return True, note


def parses(path: Path) -> tuple[bool, str]:
    """A structured artifact that cannot be parsed is as useless as an absent one --
    every consumer of it will fail. Caught the first time this tool ran: it passed a
    run-telemetry.yaml whose YAML was malformed, because existence and size were the
    only things being checked."""
    if path.suffix not in (".yaml", ".yml"):
        return True, ""
    try:
        import yaml  # noqa: PLC0415 - optional; absent means we simply skip the check
    except ImportError:
        return True, "(pyyaml absent, parse not checked)"
    try:
        yaml.safe_load(path.read_text(encoding="utf-8"))
        return True, "parses"
    except Exception as e:  # noqa: BLE001 - any parse failure is the same verdict
        first = str(e).strip().splitlines()[0][:90]
        return False, f"does not parse: {first}"


def _scope_window(text: str) -> tuple[str, str]:
    """Prefer the document's own Scope section over the first 4 KB. Scanning the whole
    head is how a GENERATED file's line count once became the proof that a review had
    measured something real: the biggest number in a document is rarely the one that
    describes the document.

    Takes the LAST Scope section, not the first. These artifacts are append-only: a second
    change on one ticket adds a dated pass at the BOTTOM. Reading the first section let the
    opening pass green-light every later change on the same ticket, and the newest pass --
    the only one describing the diff about to be pushed -- was never read at all. Observed
    2026-09-29: a review whose sixth pass measured one repo passed on the first pass's
    "2 repos, 384 lines"."""
    matches = list(SCOPE_HEADING_RE.finditer(text))
    if not matches:
        return text[:4000], "head"
    m = matches[-1]
    start = m.end()
    nxt = re.search(r"^#{1,4}\s", text[start:], re.M)
    where = "scope section" if len(matches) == 1 else f"scope section {len(matches)} of {len(matches)}"
    return text[start:start + (nxt.start() if nxt else 2000)], where


# A scope line often carries its own exclusion note: "77 files, 6225 lines (of these, 5267 are a
# generated designer file)". Dropping the whole line threw the real scope away with the note, and the
# gate then called a real review HOLLOW (PROJ-11212). So drop the smallest part that holds the keyword:
# a (parenthesised) aside first, then a clause between separators, and the whole line only when the
# keyword is in its only clause.
PAREN_RE = re.compile(r"\([^()]*\)")
CLAUSE_SPLIT_RE = re.compile(r"\s*(?:;|·|\|| - | -- )\s*")


def _drop_excluded(line: str) -> str:
    if not EXCLUDED_LINE_RE.search(line):
        return line
    line = PAREN_RE.sub(lambda m: " " if EXCLUDED_LINE_RE.search(m.group(0)) else m.group(0), line)
    if not EXCLUDED_LINE_RE.search(line):
        return line
    clauses = CLAUSE_SPLIT_RE.split(line)
    if len(clauses) == 1:
        return ""
    return " ; ".join(c for c in clauses if not EXCLUDED_LINE_RE.search(c))


def scope_of(path: Path) -> tuple[bool, str]:
    """Return (measured_something, evidence). A file whose numbers are all zero
    measured nothing, whatever its verdict line says."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return False, f"unreadable: {e}"
    window, where = _scope_window(text)
    # Identifiers are not measurements: a commit hash, a ticket id in a path and a
    # migration file name all live in `code spans`, so drop those spans first.
    window = CODE_SPAN_RE.sub(" ", window)
    # A figure the document itself labels generated or excluded is not its scope.
    kept = chr(10).join(_drop_excluded(ln) for ln in window.splitlines())
    # Inside a section the document itself calls Scope, ANY standalone number is a
    # scope figure -- these sections are usually tables, whose cells carry no unit
    # word for SCOPE_RE to anchor on.
    rx = BARE_NUM_RE if where == "scope section" else SCOPE_RE
    nums = [int(m.group(1).replace(",", "")) for m in rx.finditer(kept)]
    if not nums:
        return False, f"no scope figure found in the {where}"
    if max(nums) == 0:
        return False, f"every scope figure is zero {nums[:5]}"
    # Print the figures, not just the largest -- a wrong pick has to stay visible.
    return True, f"{where} figures {nums[:6]}"


def main() -> int:
    # Windows consoles default to cp1252, which turns the separators below into
    # replacement chars.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ticket_dir", type=Path)
    ap.add_argument("gate", choices=sorted(REQUIRED))
    ap.add_argument("--type", dest="ticket_type", default="crud-feature")
    args = ap.parse_args()

    d: Path = args.ticket_dir
    if not d.is_dir():
        print(f"BLOCKED  ticket dir does not exist: {d}", file=sys.stderr)
        return 2

    skipped = SKIPS.get(args.ticket_type, set())
    missing, hollow, ok, waived = [], [], [], []

    for name, why, measure in REQUIRED[args.gate]:
        if name in skipped:
            waived.append((name, f"skipped by ticket type '{args.ticket_type}'"))
            continue
        if measure == "evidence" and phase_skipped(d, "api-test"):
            waived.append((name, "api-test skipped by the user (run-telemetry skipped_phases)"))
            continue
        if measure == "if-armed" and not gates_armed(d):
            waived.append((name, "no armed gates in ticket-context.yaml"))
            continue
        p = d / name
        if not p.exists() or (p.is_file() and p.stat().st_size == 0):
            missing.append((name, why))
            continue
        readable, parse_note = parses(p)
        if not readable:
            hollow.append((name, parse_note))
            continue
        if measure == "if-armed":
            measure = False
        if measure == "telemetry":
            measured, evidence = telemetry_filled(p)
        elif measure == "regression":
            measured, evidence = regression_counted(p)
        elif measure == "evidence":
            measured, evidence = evidence_on_disk(p)
        elif measure:
            measured, evidence = scope_of(p)
        else:
            ok.append((name, parse_note or f"{p.stat().st_size} bytes"))
            continue
        if not measured:
            hollow.append((name, evidence))
            continue
        ok.append((name, evidence))

    print(f"ARTIFACT GATE  {args.gate}  ·  {d}  ·  type={args.ticket_type}")
    for name, ev in ok:
        print(f"  ok       {name:<28} {ev}")
    for name, reason in waived:
        print(f"  waived   {name:<28} {reason}")
    for name, ev in hollow:
        print(f"  HOLLOW   {name:<28} {ev}")
    for name, why in missing:
        print(f"  MISSING  {name:<28} {why}")

    if missing or hollow:
        print()
        print("BLOCKED — a declared artifact is absent or measured nothing.")
        print("Write it before passing this gate. Prose in a SKILL.md is not the record;")
        print("the file is. (See this tool's docstring for why.)")
        return 2

    print(f"\nPASS — {len(ok)} artifact(s) present with real scope"
          + (f", {len(waived)} waived by type" if waived else ""))
    print("Note: PASS means the record exists. Open it and check it describes THIS change.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
