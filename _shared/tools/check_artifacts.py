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

    gates:  pre-commit | pre-push | pr | done | e2e
            (e2e = G-MATRIX + G-E2E alone, local: run when Phase 15.1 ends)
    types:  crud-feature (default) | bugfix-small | bugfix-investigated
            | bugfix-regression | hotfix | refactor | spike | doc-only
            | migration-only | fe-only        (see do-ticket/ticket-types.md)
            | no-ticket                       (a push-code run with no ticket dir)

Stdlib only (PyYAML is used when present). No install step, so nothing stands
between the gate and running it.
"""

from __future__ import annotations

import argparse
import re
import subprocess
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

# PROJ-11685: every AC was "proven" through shortcuts, the full flow never ran on any env, and one
# type had no case. G-MATRIX + G-E2E (do-ticket SKILL.md phase list) were prose; these entries are the gate.
E2E_RESULTS = "test-evidence/e2e/e2e-results.md"
_MATRIX = ("test-cases.md", "G-MATRIX: '## Variant matrix' with no empty cell + '## E2E track' with an [E2E] case "
           "(do-ticket phases/design.md Phase 8)", "matrix")
E2E_LOCAL = [
    _MATRIX,
    (E2E_RESULTS, "G-E2E: every E2E case PASS or owner-approved SKIP on local (do-ticket 15.1)", "e2e-local"),
]
E2E_DONE = [
    _MATRIX,
    (E2E_RESULTS, "G-E2E: every E2E case PASS or owner-approved SKIP on local AND test (do-ticket 15.1 / 23)", "e2e-done"),
]
# Track B: every case in test-cases.md is RUN, not only the ACs. PROJ-11685: [API] cases were tied
# to no run, [GUI] cases ran nowhere, nothing mapped TC -> run -> result.
TC_RESULTS = "test-evidence/tc-results.md"
_TC = (TC_RESULTS, "G-TC: every TC of test-cases.md has a row; none FAIL / PARTIAL / stale / unapproved SKIP "
       "(do-ticket 15b, Track B)", "tc-results")

REQUIRED = {
    # PROJ-10837: this list held 2 files while phases/verify.md called 5 mandatory, so the
    # gate printed PASS over a run with no telemetry, no regression count and no evidence.
    "pre-commit": [
        ("code-quality-review.md", "the diff-scoped quality review (do-ticket 13.5)", True),
        ("plan.md", "what was going to be built, and the options rejected", False),
        ("run-telemetry.yaml", "phases/verify.md 16: must exist before the commit prompt", "telemetry"),
        # Business gaps are fixed at chosen checkpoints, not left for the end.
        ("run-telemetry.yaml", "knowledge checkpoints K1 (after analyze) + K3 (16-0), do-ticket/promote-knowledge.md", "kcheck-commit"),
        ("implement-summary.md", "Phase 12: the runner's own 'Regression: N passed, 0 failed' line", "regression"),
        ("test-evidence", "Phase 15: a flow is verified only if its request/response is on disk", "evidence"),
        ("legacy-contract.md", "Phase 9.8: required while ticket-context armed_gates is non-empty", "if-armed"),
        # A project got its business flows in flows/business_flows.yaml, and 6c still read only
        # flow_index.yaml (the procedure list), so no ticket could see them. The record names the file read.
        ("ticket-context.yaml", "Phase 6c flow gate: flow_gate.decision on record, naming the business-flows file read", "flow-gate"),
        *E2E_LOCAL,
        _TC,
    ],
    "pre-push": [
        ("code-quality-review.md", "the quality review push-code asks for", True),
        ("run-telemetry.yaml", "the only input /learn D8 has; absent = no cross-ticket learning", "telemetry"),
        *E2E_LOCAL,
        _TC,
    ],
    "pr": [
        ("plan.md", "implementation intent, read by pr-description", False),
        ("implement-summary.md", "what was actually changed, read by pr-description", False),
        *E2E_LOCAL,
        _TC,
    ],
    # Phase 15.1 end: G-E2E alone, so the full-flow run is checked before anything is built on it.
    "e2e": E2E_LOCAL,
    "done": [
        *E2E_DONE,
        _TC,
        ("run-telemetry.yaml", "phase outcomes + failure modes for /learn", "telemetry"),
        ("run-telemetry.yaml", "knowledge checkpoint K4 (catch-up after CI / review / QC)", "kcheck-done"),
        ("implement-summary.md", "the as-built record", False),
    ],
}

# Types whose phase list has no `test-cases` (ticket-types.md), so no matrix and no 15.1 `e2e`.
NO_TEST_CASES = {"test-cases.md", E2E_RESULTS, TC_RESULTS}

# Types that genuinely skip a phase, per do-ticket/ticket-types.md. Listed so a
# legitimate skip is a stated fact rather than a silent pass.
SKIPS = {
    "doc-only": {"code-quality-review.md", "implement-summary.md", "test-evidence", *NO_TEST_CASES},
    "spike": {"code-quality-review.md", "implement-summary.md", "test-evidence", *NO_TEST_CASES},
    "hotfix": {"code-quality-review.md", "test-evidence", *NO_TEST_CASES},
    # these types do not run api-test (phases/verify.md, Phase 15 skip list)
    "refactor": {"test-evidence", *NO_TEST_CASES},
    "bugfix-small": {"test-evidence", *NO_TEST_CASES},
    "bugfix-regression": {"test-evidence", *NO_TEST_CASES},   # ticket-types.md: same phases as bugfix-small
    "migration-only": {"test-evidence", *NO_TEST_CASES},
    "fe-only": {"test-evidence"},
    "crud-feature": set(),
    "bugfix-investigated": set(),
    # a push with no ticket has no do-ticket run, so no telemetry can exist
    "no-ticket": {"run-telemetry.yaml", *NO_TEST_CASES},
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


PROJECTS_YAML = Path(__file__).resolve().parents[2] / "_config" / "projects.yaml"


def _project() -> dict:
    """The active project block of _config/projects.yaml, or {}. Accepts both config shapes: a
    top-level `active: <name>`, or a project block with `active: true`."""
    cfg = _yaml(PROJECTS_YAML) if PROJECTS_YAML.exists() else {}
    projects = (cfg.get("projects") or {}) if isinstance(cfg, dict) else {}
    proj = projects.get(cfg.get("active")) if isinstance(cfg.get("active"), str) else None
    if proj is None:
        proj = next((p for p in projects.values() if isinstance(p, dict) and p.get("active") is True), None)
    return proj if isinstance(proj, dict) else {}


def _project_path(key: str) -> str | None:
    proj = _project()
    return (proj.get("paths") or {}).get(key) or (proj.get("output_dir") if key == "output_root" else None)


# phases/analyze.md 6c: only these types run `analyze`, so only they owe a flow-gate record.
FLOW_GATE_TYPES = {"crud-feature", "bugfix-investigated", "fe-only"}
FLOW_GATE_DECISIONS = {"passthrough", "routed_to_dps", "bypassed", "blocked", "skipped", "not_available"}


def project_business_flows(ticket: Path) -> Path | None:
    """The project's business-flow file (via flow_index.yaml business_flows_ref:), or None.
    The docs store is the configured output root, else <store>/tickets/<ID> -> <store>."""
    from check_flow_registries import business_flows_path  # noqa: PLC0415 - sibling gate owns the pointer rule
    root = _project_path("output_root")
    stores = ([Path(root)] if root else []) + [ticket.parent.parent]
    for store in stores:
        bf = business_flows_path(store)
        if bf and bf.exists():
            return bf
    return None


def flow_gate_recorded(path: Path) -> tuple[bool, str]:
    """ticket-context.yaml flow_gate.decision is set, and when the project has business flows the
    record names that file -- a gate that read only the procedure list saw no flows at all."""
    fg = _yaml(path).get("flow_gate") or {}
    if not isinstance(fg, dict):
        fg = {"decision": fg}
    decision = str(fg.get("decision") or "").strip()
    if decision not in FLOW_GATE_DECISIONS:
        return False, (f"flow_gate.decision is '{decision or 'unset'}' - run do-ticket 6c (phases/analyze.md "
                       "FG-1..FG-10) and record it")
    bf = project_business_flows(path.parent)
    if bf is None or decision == "skipped":
        return True, f"flow gate {decision}" + ("" if bf else " (project has no business flows)")
    read = str(fg.get("business_flows") or "").replace("\\", "/")
    if not read or read == "absent" or not read.endswith(bf.name):
        return False, (f"flow_gate.business_flows is '{read or 'unset'}' but the project has {bf.name} - "
                       "6c read the wrong file; re-run it against the business flows")
    touched = fg.get("touched_flows") or []
    return True, f"flow gate {decision} on {bf.name}, {len(touched)} flow(s) touched"


# --------------------------------------------------------------------------
# G-MATRIX + G-E2E. The rules: do-ticket SKILL.md phase list (GATE G-E2E), phases/design.md
# Phase 8 (matrix format), phases/verify.md 15.1, phase-contracts.yaml `test-cases` / `e2e`.
# Every unknown shape reads as a block: a table this parser cannot read is not a passed gate.
# --------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)
FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.M | re.S)
RESULT_HEAD_RE = re.compile(r"^(PASS|SKIP|PARTIAL|FAIL)\b", re.I)
CASE_ID_RE = re.compile(r"\b(?:TC|E2E)-\d+[A-Za-z]?\b")
E2E_ID_RE = re.compile(r"\bE2E-\d+[A-Za-z]?\b")
PLACEHOLDER_RE = re.compile(r"<[^<>]*>|^\.{2,}$|^(?:tbd|todo|\?+|-+|—|–)$", re.I)
DASH = r"(?:—|–|--|\s-\s)"
OUT_OF_SCOPE_RE = re.compile(r"^out[\s-]of[\s-]scope\s*:\s*(\S.*?)\s*" + DASH + r"\s*(\S.*)$", re.I)
NA_RE = re.compile(r"^n/a\s*:\s*\S", re.I)
SKIP_APPROVED_RE = re.compile(r"^SKIP\s*" + DASH + r"\s*(\S.*?)\s*" + DASH + r"\s*approved\s+by\s+(\S.*)$", re.I)
BACKTICK_RE = re.compile(r"`([^`]+)`")


def _sections(text: str) -> list[tuple[int, str, str]]:
    """(level, title, body up to the next heading of the same or higher level). Fenced code is blanked
    first: a `# comment` in a bash block is not a heading."""
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    heads = list(HEADING_RE.finditer(text))
    out = []
    for i, h in enumerate(heads):
        level = len(h.group(1))
        end = len(text)
        for nxt in heads[i + 1:]:
            if len(nxt.group(1)) <= level:
                end = nxt.start()
                break
        out.append((level, h.group(2), text[h.end():end]))
    return out


def _cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Markdown tables in `text`: (header cells, data rows). A table needs a |---| separator line."""
    lines, tables, i = text.splitlines(), [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) \
                and re.fullmatch(r"\s*\|?[\s:|-]*-{3,}[\s:|-]*\|?\s*", lines[i + 1]):
            header, rows, j = _cells(lines[i]), [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(_cells(lines[j]))
                j += 1
            tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


def e2e_cases(text: str) -> set[str]:
    """E2E cases = every case heading whose id is E2E-.. or whose block carries the [E2E] tag."""
    found = set()
    for _level, title, body in _sections(text):
        m = CASE_ID_RE.match(title)
        if m and (m.group(0).startswith("E2E-") or "[E2E]" in body):
            found.add(m.group(0))
    return found


def _matrix_cell_ok(cell: str, e2e_column: bool) -> str | None:
    """None when the cell is filled per phases/design.md Phase 8, else why not."""
    c = cell.strip().strip("*_").strip()
    if not c:
        return "empty"
    if PLACEHOLDER_RE.search(c):
        return f"placeholder '{c[:40]}'"
    if OUT_OF_SCOPE_RE.match(c):
        return None
    if c.lower().startswith("out of scope"):
        return f"'{c[:50]}' lacks '<reason> — <who decided>'"
    if NA_RE.match(c):
        # The full flow exists for every type: an unchanged type still needs E2E or an owner's out-of-scope.
        return "n/a is not allowed in the E2E column" if e2e_column else None
    if c.lower().startswith("n/a"):
        return f"'{c[:40]}' lacks 'n/a: <reason>'"
    ids = CASE_ID_RE.findall(c)
    if not ids:
        return f"'{c[:40]}' is no case id, 'out of scope: <reason> — <who>' or 'n/a: <reason>'"
    if e2e_column and not E2E_ID_RE.search(c):
        return f"'{c[:40]}' names no E2E-.. case"
    return None


def matrix_and_track(path: Path) -> tuple[bool, str]:
    """G-MATRIX: `## Variant matrix` has rows and no empty cell; `## E2E track` exists and the file has at
    least one [E2E] case; every case id the matrix names has a heading in the file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    secs = _sections(text)
    matrix = [s for s in secs if re.match(r"variant\s+matrix\b", s[1], re.I)]
    if not matrix:
        return False, "no '## Variant matrix' section (do-ticket phases/design.md Phase 8)"
    tables = _tables(matrix[-1][2])
    if not tables or not tables[0][1]:
        return False, "'## Variant matrix' has no table with rows"
    header, rows = tables[0]
    e2e_col = next((i for i, h in enumerate(header) if re.search(r"\be2e\b", h, re.I)), None)
    if e2e_col is None or e2e_col == 0:
        return False, f"variant matrix has no 'E2E full flow' column (header: {header})"
    problems, named = [], set()
    for r in rows:
        row_name = r[0].strip() if r else ""
        if not row_name or PLACEHOLDER_RE.search(row_name):
            problems.append(f"row with no type name: {r[:3]}")
            continue
        cells = r + [""] * (len(header) - len(r))
        for i, h in enumerate(header[1:], start=1):
            why = _matrix_cell_ok(cells[i], i == e2e_col)
            if why:
                problems.append(f"{row_name} × {h or f'col {i}'}: {why}")
        named.update(CASE_ID_RE.findall(" ".join(cells[1:])))
    if problems:
        return False, f"{len(problems)} matrix cell(s) not filled: " + "; ".join(problems[:4])
    if not any(re.match(r"e2e\s+track\b", s[1], re.I) for s in secs):
        return False, "no '## E2E track' section (do-ticket phases/design.md Phase 8)"
    cases = e2e_cases(text)
    if not cases:
        return False, "'## E2E track' has no [E2E] case heading (E2E-01 — ...)"
    headed = {m.group(0) for _l, t, _b in secs for m in [CASE_ID_RE.match(t)] if m}
    ghosts = sorted(named - headed)
    if ghosts:
        return False, f"matrix names case id(s) with no heading in the file: {ghosts[:6]}"
    return True, f"matrix {len(rows)} row(s) × {len(header) - 1} col(s), 0 empty; {len(cases)} E2E case(s)"


def _result_state(result: str) -> tuple[str, str]:
    """('ok' | 'block', label) for one Result cell."""
    r = result.strip().strip("*_").strip()
    m = RESULT_HEAD_RE.match(r)
    head = m.group(1).upper() if m else ""
    if head == "PASS":
        return "ok", "PASS"
    if head == "SKIP":
        m = SKIP_APPROVED_RE.match(r)
        if m and not PLACEHOLDER_RE.search(m.group(1)) and not PLACEHOLDER_RE.search(m.group(2)):
            return "ok", "SKIP (approved)"
        return "block", "SKIP without '— <reason> — approved by <owner>'"
    if head in ("PARTIAL", "FAIL"):
        return "block", head
    return "block", f"unknown result '{r[:30] or 'empty'}'"


def e2e_results(path: Path, envs: tuple[str, ...]) -> tuple[bool, str]:
    """G-E2E: for every E2E case in test-cases.md, the LATEST row per env decides. Each env in `envs` needs a
    row that is PASS or an owner-approved SKIP; any env's latest PARTIAL / FAIL blocks at every stage."""
    tc = path.parents[2] / "test-cases.md"
    cases = e2e_cases(tc.read_text(encoding="utf-8", errors="replace")) if tc.is_file() else set()
    if not cases:
        return False, "test-cases.md has no E2E case, so there is nothing this file can prove"
    text = path.read_text(encoding="utf-8", errors="replace")
    latest: dict[tuple[str, str], tuple[str, str, list[str]]] = {}
    for header, rows in _tables(text):
        low = [h.lower() for h in header]
        try:
            ci, ei, ri = low.index("case"), low.index("env"), low.index("result")
        except ValueError:
            continue
        pi = next((i for i, h in enumerate(low) if h.startswith("entry")), None)
        vi = next((i for i, h in enumerate(low) if h.startswith("evidence")), None)
        for r in rows:
            r = r + [""] * (len(header) - len(r))
            m = CASE_ID_RE.search(r[ci])
            env = r[ei].strip("` *").lower()
            if not m or not env:
                continue
            state, label = _result_state(r[ri])
            gaps = []
            if label == "PASS":
                if pi is None or not r[pi].strip() or PLACEHOLDER_RE.search(r[pi].strip()):
                    gaps.append("no entry points named")
                if vi is None or not r[vi].strip():
                    gaps.append("no evidence")
                else:
                    base = path.parents[1]  # test-evidence/
                    for ref in BACKTICK_RE.findall(r[vi]):
                        if not any((b / ref).exists() for b in (base, path.parent, path.parents[2])):
                            gaps.append(f"evidence `{ref}` not on disk")
            latest[(m.group(0), env)] = (state, label, gaps)
    if not latest:
        return False, "no table with Case | Env | Result columns and a case row"
    problems = []
    for (case, env), (state, label, gaps) in sorted(latest.items()):
        if case in cases and state == "block":
            problems.append(f"{case}@{env}: {label}")
        elif case in cases and gaps:
            problems.append(f"{case}@{env}: PASS but {', '.join(gaps)}")
    for case in sorted(cases):
        for env in envs:
            if (case, env) not in latest:
                problems.append(f"{case}@{env}: no row")
    if problems:
        return False, f"{len(problems)} E2E gap(s): " + "; ".join(problems[:5])
    extra = sorted({c for c, _e in latest} - cases)
    return True, (f"{len(cases)} E2E case(s) PASS/approved SKIP on {'+'.join(envs)}"
                  + (f"; rows for unknown case(s) {extra[:4]}" if extra else ""))


REMOVED_RE = re.compile(r"\bremoved\b", re.I)


def tc_cases(text: str) -> set[str]:
    """Track B cases = every case heading (TC-.. / E2E-..) minus E2E cases (G-E2E owns those) and headings
    that say the case was removed (`## TC-18 — removed in v2`)."""
    e2e = e2e_cases(text)
    found = set()
    for _level, title, _body in _sections(text):
        m = CASE_ID_RE.match(title)
        if m and m.group(0) not in e2e and not REMOVED_RE.search(title):
            found.add(m.group(0))
    return found


# PROJ-11685: 9 rule changes were committed after the Track B run, and the old PASS rows still
# counted. A PASS row now names the code it ran on (`repo@sha`); a later code commit makes it stale.
COMMIT_TOKEN_RE = re.compile(r"([A-Za-z0-9._-]+)@([0-9a-fA-F]{7,40})(?![0-9a-zA-Z])")
NO_CODE_RE = re.compile(r"^n/?a\s*[—–-]+\s*\S", re.I)
STALE_GATES = {"pre-commit", "pre-push", "pr"}   # the ticket branch still exists; after a squash merge it may not
CODE_PATHSPEC = (".", ":(exclude)*.md")          # a doc-only commit does not make a test run stale


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, r.stdout.strip()


def _repo_dir(ticket: Path, repo: str) -> Path | None:
    """ticket-state worktree_paths first (by key or folder name), then <worktree_base>/<ID>/<repo>, then
    <repos_root>/<repo> of the active project."""
    cands = [Path(str(v)) for k, v in (_yaml(ticket / "ticket-state.yaml").get("worktree_paths") or {}).items()
             if v and (k == repo or Path(str(v)).name == repo)]
    if _project_path("worktree_base"):
        cands.append(Path(_project_path("worktree_base")) / ticket.name / repo)
    if _project_path("repos_root"):
        cands.append(Path(_project_path("repos_root")) / repo)
    return next((c for c in cands if (c / ".git").exists()), None)


def _stale(ticket: Path, repo: str, sha: str, cache: dict) -> str | None:
    """None when no code commit on the ticket branch (else HEAD) came after `sha`; else why the row is stale."""
    if (repo, sha) in cache:
        return cache[(repo, sha)]
    d = _repo_dir(ticket, repo)
    if d is None:
        msg = f"repo '{repo}' not found (ticket-state worktree_paths, worktree_base, repos_root), staleness not measured"
    else:
        branch = str(_yaml(ticket / "ticket-state.yaml").get("branch") or "")
        ref = branch if branch and _git(d, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")[0] == 0 else "HEAD"
        if _git(d, "cat-file", "-e", f"{sha}^{{commit}}")[0]:
            msg = f"commit {repo}@{sha} not found"
        elif _git(d, "merge-base", "--is-ancestor", sha, ref)[0]:
            msg = f"{repo}@{sha} is not in {ref}'s history (it ran on other code), run it again"
        else:
            rc, out = _git(d, "rev-list", "--count", f"{sha}..{ref}", "--", *CODE_PATHSPEC)
            n = int(out) if rc == 0 and out.isdigit() else -1
            msg = (None if n == 0 else f"git rev-list failed on {repo}" if n < 0
                   else f"stale: {n} code commit(s) on {repo} {ref} after {sha}, run it again")
    cache[(repo, sha)] = msg
    return msg


def tc_results(path: Path, check_stale: bool = False) -> tuple[bool, str]:
    """G-TC: every Track B case of test-cases.md has a row; the LATEST row per case and env decides. Any latest
    FAIL / PARTIAL / unapproved SKIP blocks. A PASS needs 'How it ran', and every backticked path in it on disk.
    A PASS also needs a Commit cell (`repo@sha`, or `n/a — <reason>` when no code ran); with `check_stale` a
    code commit after that sha on the ticket branch makes the row stale."""
    ticket = path.parents[1]
    tc = ticket / "test-cases.md"
    cases = tc_cases(tc.read_text(encoding="utf-8", errors="replace")) if tc.is_file() else set()
    if not cases:
        return False, "test-cases.md has no TC case heading (## TC-01 — ...), so there is nothing to match"
    text = path.read_text(encoding="utf-8", errors="replace")
    latest: dict[tuple[str, str], tuple[str, str, list[str]]] = {}
    stale_cache: dict = {}
    for header, rows in _tables(text):
        low = [h.lower() for h in header]
        ci = next((i for i, h in enumerate(low) if h in ("tc", "case")), None)
        ei = low.index("env") if "env" in low else None
        ri = low.index("result") if "result" in low else None
        hi = next((i for i, h in enumerate(low) if h.startswith("how")), None)
        ki = next((i for i, h in enumerate(low) if h.startswith("commit")), None)
        if None in (ci, ei, ri, hi):
            continue
        for r in rows:
            r = r + [""] * (len(header) - len(r))
            m = CASE_ID_RE.search(r[ci])
            env = r[ei].strip("` *").lower()
            if not m or not env:
                continue
            state, label = _result_state(r[ri])
            gaps = []
            if label == "PASS":
                how = r[hi].strip()
                if not how or PLACEHOLDER_RE.search(how):
                    gaps.append("no 'How it ran'")
                for ref in BACKTICK_RE.findall(how):
                    if "/" in ref and not any((b / ref).exists() for b in (path.parent, ticket)):
                        gaps.append(f"`{ref}` not on disk")
                commit = r[ki].strip().strip("`* ") if ki is not None else ""
                tokens = COMMIT_TOKEN_RE.findall(commit.replace("`", ""))
                if NO_CODE_RE.match(commit):
                    pass
                elif not tokens:
                    gaps.append("no Commit (`repo@sha`, or `n/a — <reason>`)")
                elif check_stale:
                    gaps += [s for repo, sha in tokens if (s := _stale(ticket, repo, sha, stale_cache))]
            latest[(m.group(0), env)] = (state, label, gaps)
    if not latest:
        return False, "no table with TC | How it ran | Env | Result columns and a case row"
    problems = []
    for (case, env), (state, label, gaps) in sorted(latest.items()):
        if state == "block" and case in cases:
            problems.append(f"{case}@{env}: {label}")
        elif gaps and case in cases:
            problems.append(f"{case}@{env}: PASS but {', '.join(gaps)}")
    ran = {c for c, _e in latest}
    problems += [f"{c}: no row" for c in sorted(cases - ran)]
    if problems:
        return False, f"{len(problems)} TC gap(s): " + "; ".join(problems[:6])
    extra = sorted(ran - cases)
    return True, (f"{len(cases)} TC(s) PASS / approved SKIP"
                  + (f"; rows for case(s) not in test-cases.md {extra[:4]}" if extra else ""))


KNOWLEDGE_MISS_VALUES = {"no", "yes-not-found", "wrong"}
KNOWLEDGE_AREAS = {"business", "cross-service", "external", "data", "frontend", "config"}
PROMOTED_RE = re.compile(r"^(?:(?:written|fixed|indexed)\s+\S+|skipped:\s*\S+)")


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
    # 15 tickets of telemetry could not say whether a miss came from the docs. Hand-sorting put ~10%
    # of 45 failures on system knowledge, and every one of those facts was absent from the docs.
    # Without this list the "is it the docs?" question stays a guess. [] is a real answer; absent is not.
    misses = loaded.get("knowledge_misses", None)
    if not isinstance(misses, list):
        return False, ("knowledge_misses missing -- write `knowledge_misses: []` if the run lacked no system "
                       "fact, else one entry per fact (run-telemetry-schema.md)")

    def verdict(m: dict):
        v = m.get("docs_had_it")
        return "no" if v is False else v  # bare `no` in YAML loads as False; the writer meant "no"

    bad = [m for m in misses
           if not (isinstance(m, dict) and m.get("fact") and verdict(m) in KNOWLEDGE_MISS_VALUES
                   and m.get("area") in KNOWLEDGE_AREAS)]
    if bad:
        return False, (f"{len(bad)} knowledge_misses entr{'y' if len(bad) == 1 else 'ies'} without `fact`, or with "
                       f"docs_had_it not in {sorted(KNOWLEDGE_MISS_VALUES)} or area not in {sorted(KNOWLEDGE_AREAS)}")
    # The old tail-phase promote never ran once in 11 tickets: nothing was gated on it. This is the gate.
    unpromoted = [m for m in misses if not PROMOTED_RE.match(str(m.get("promoted") or ""))]
    if unpromoted:
        return False, (f"{len(unpromoted)} knowledge_misses entr{'y' if len(unpromoted) == 1 else 'ies'} not promoted "
                       "-- run step 16-0 (do-ticket/promote-knowledge.md) and set `promoted: written|fixed|indexed "
                       "<file>` or `skipped: <reason>`")
    # A `promoted` line is a claim. Check the file it names is real, or "written X" costs nothing to fake.
    # Docs root = <docs>/tickets/<ID>/run-telemetry.yaml -> <docs>; only checked when it looks like one.
    docs = path.parent.parent.parent
    if (docs / "INDEX.md").is_file():
        ghost = [m["promoted"] for m in misses
                 if not str(m["promoted"]).startswith("skipped")
                 and not (docs / str(m["promoted"]).split(None, 1)[1].strip()).is_file()]
        if ghost:
            return False, f"knowledge_misses promoted to a file that does not exist under {docs.name}/: {ghost[:3]}"
    note = f"{len(phases)} phase(s), {len(misses)} knowledge miss(es)"
    if not loaded.get("ticket_type"):
        note += ", ticket_type still null"
    return True, note


def checkpoints_logged(path: Path, need: list[str]) -> tuple[bool, str]:
    """Knowledge checkpoints are prose until a line proves each one ran. The tail-phase promote that
    nobody gated ran 0 times in 11 tickets; a checkpoint with no record is the same promise."""
    try:
        import yaml  # noqa: PLC0415 - optional; absent means we simply skip the check
    except ImportError:
        return True, "(pyyaml absent, checkpoints not checked)"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    seen = {str(c.get("id")) for c in (loaded.get("knowledge_checkpoints") or []) if isinstance(c, dict)}
    lacking = [k for k in need if k not in seen]
    if lacking:
        return False, (f"knowledge_checkpoints lacks {', '.join(lacking)} -- run it (do-ticket/promote-knowledge.md) "
                       "and log its line")
    return True, f"knowledge checkpoints {', '.join(need)} logged"


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
        if measure == "flow-gate" and args.ticket_type not in FLOW_GATE_TYPES:
            waived.append((name, f"type '{args.ticket_type}' does not run analyze, so no 6c flow gate"))
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
        elif measure == "flow-gate":
            measured, evidence = flow_gate_recorded(p)
        elif measure == "kcheck-commit":
            need = ["K1", "K3"] if args.ticket_type in FLOW_GATE_TYPES else ["K3"]
            measured, evidence = checkpoints_logged(p, need)
        elif measure == "matrix":
            measured, evidence = matrix_and_track(p)
        elif measure == "e2e-local":
            measured, evidence = e2e_results(p, ("local",))
        elif measure == "e2e-done":
            measured, evidence = e2e_results(p, ("local", "test"))
        elif measure == "tc-results":
            measured, evidence = tc_results(p, check_stale=args.gate in STALE_GATES)
        elif measure == "kcheck-done":
            measured, evidence = checkpoints_logged(p, ["K4"])
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
