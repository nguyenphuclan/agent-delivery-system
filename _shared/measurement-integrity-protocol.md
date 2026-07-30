---
name: measurement-integrity-protocol
description: Every gate, review, and test run must report the SIZE of what it measured and what it deliberately did not look at — not just its verdict. An absent or empty measurement is N/A/BLOCKED, never PASS. Canonical home for the empty-measurement class of false green. Used by push-code, do-ticket (code-quality-review + FM-EMPTY-MEASUREMENT), scan-init verify, and any skill that emits a verdict.
---

# Measurement Integrity Protocol

## Purpose

A check gives you one visible signal — the verdict. It quietly depends on a second thing that stays
invisible: **whether the measurement happened at all.** Both end up as the same green tick, and there
is no natural place where the difference shows up.

None of the shapes below are bugs. They are correct behaviour, which is exactly why they survive:
there is nothing to fix, only something to notice.

| Shape | Why it reads as success |
|---|---|
| A test filter that matches nothing | The runner exits 0 — every test in the set passed. The set was empty. (`dotnet test --filter`, `jest -t`, `pytest -k`) |
| Coverage measured over zero lines | 0 uncovered / 0 total = 100% |
| A diff-scoped review whose base ref resolves to nothing | It found no problems, quite honestly |
| A verification query returning 0 rows | Cannot distinguish *"the write failed"* from *"my WHERE clause is wrong"* — and the second one looks clean |
| A verdict derived from the agent's own prose, with no artefact on disk | It reads exactly like a verdict derived from a tool |
| A gate that has never once gone red | Never shown to work, only shown to be quiet |

**This class cannot be closed, only made smaller.** The obvious fix — add a check that the first check
ran — buys you two things to own and moves the same question up a level. So this protocol does not try
to close it. It makes the empty case *look different from the real one at a glance*.

## The two invariants

### I1 — A verdict never ships without its scope

Not `passed` — **`passed, 214 of an expected 214`**.
Not `clean` — **`clean, 14 files, +312/−87`**.
Not `PASS` — **`PASS — 1 row where external_id='X', expected 1`**.

A verdict on its own can come from a check that did nothing. **A number can't.**

### I2 — Absent input is N/A or BLOCKED, never PASS and never FAIL

`BLOCKED` is a verdict **on the measurement, not on the code**. It counts against the run and blocks
progression exactly like a failure, but it must never be reported as evidence about the subject. Fix
the measurement — filter, base ref, repo dir, credentials, missing artefact — and re-run. Only once
the gate reports a **non-zero scope** may its verdict be believed.

## The denominator rule

**Declare the expected count BEFORE measuring; reconcile after.**

```
Expected: 14 test cases parsed from <csv>, 1 row in <table> where external_id='X'
Observed: 14 accounted for, 1 row
```

A count you compute only after the fact cannot detect a partial read. A partial read is easy — wrong
delimiter, a newline inside a quoted cell, a filter typo, a shard that failed to load — and every
number downstream inherits it silently. **If declared ≠ observed, stop and re-measure.** Do not report
a result set you cannot account for.

## Report what you did NOT look at

The scope number says how much was measured. It does not say what was **deliberately excluded**, and
exclusions are where the honest gaps live. Every consumer emits a short `not examined` line:

```
Not examined: duplication-on-new-code (needs server upload — deferred to CI)
              pre-existing lines in changed files (not new code, reported for context only)
              6 GUI test cases (delegated to manual QC)
```

This is not a disclaimer. It is the part a human uses to decide where to spend their own attention —
the one thing automation cannot hand back. A reviewer who knows the gate skipped X can look at X. A
reviewer told only "green" cannot.

**Silent truncation is the failure this prevents.** Any cap — top-N findings, sampled files, one
retry, a lens skipped for cost — is stated. An unstated cap reads as full coverage.

## Prove the gate

A gate that has never gone red has not been shown to work. Before trusting a newly written or newly
wired gate, **inject a violation you know is real** and confirm it goes RED:

| Gate | Injected violation |
|---|---|
| Static-analysis rule scan | a deliberately over-complex method (cognitive-complexity rule) |
| Coverage on new code | ~30 untested new lines |
| Secrets / auth scan | a removed authorisation attribute |
| DB verification | assert the row count on a flow you did not run |
| Review skill | a swallowed exception in the diff |

Record that it went red once. A gate proven once is worth more than three gates never exercised.

### `check-scope.py` — the runnable half

A gate written only as prose is a **principle-rule**: it never visibly clashes and never dies, so
nobody finds out when it stops being applied. `_shared/check-scope.py` turns the mechanical half of
each gate into a **checkable-rule** — one command, exit 0 or exit **2 = BLOCKED**, no exit 1 because
it never judges the subject, only the measurement.

```
python _shared/check-scope.py diff <repo> <base_ref>            # changed files + added lines
python _shared/check-scope.py glob <root> <pattern> [pattern…]  # walk matched >0 files
python _shared/check-scope.py files <path> [path…]              # artefacts exist and are non-empty
python _shared/check-scope.py reconcile <declared> <observed> [label]
```

Run it **before** the gate, not after. Exit 2 means stop and fix the measurement; its stdout `SCOPE`
line is the one you paste into your own report, so the number a reader sees came from a tool rather
than from the agent's recollection.

**Proven red 2026-07-30** — 11 injected violations, all exit 2: bogus base ref · empty diff ·
not-a-git-repo · deletion-only diff · pattern matching nothing · wrong root · missing artefact ·
declared 0 · declared 14 vs accounted 9 · non-numeric counts · unknown mode. 4 pass cases exit 0 with
a `SCOPE` line. The fixtures are a `git init`, two commits, and four numbers — re-derive in a minute.

## How each consumer applies it

| Consumer | Its scope line | Its N/A case |
|---|---|---|
| `push-code` | issues scanned on `N` new lines across `M` files; coverage `P%` of `K` new lines | 0 new lines resolved / no analyzer issues file / no coverage file → BLOCKED, not green |
| `do-ticket` code-quality-review | `N files, +X/−Y lines`, dimensions run | diff resolves to 0 files → BLOCKED, not CLEAN |
| `do-ticket` FM-EMPTY-MEASUREMENT | (failure-mode entry — the pivots are `report-na-not-pass` + `prove-the-gate`) | — |
| `scan-init verify` | coverage % **with its denominator** | 0 files in the source walk → `n/a`, never `100%` |
| Any env-verification skill | `parsed: N — accounted for: N` | 0-row query, empty body, connection error → BLOCKED |
| Any test-evidence skill | `N cases → M mapped to code, K manual-only` | a case with no runnable test → manual, never an empty passing test |
| Any review skill | files reviewed + which checklist sections ran | 0 files, or missing acceptance evidence → cannot PASS |

A skill may tighten this. **No skill may report a bare verdict.**

## Anti-patterns

- ❌ `passed` / `clean` / `✅` with no count. This is the whole problem, in its shortest form.
- ❌ Folding BLOCKED into MANUAL or SKIP so the run looks complete.
- ❌ Reporting `100%` coverage without stating the line count it was computed over.
- ❌ "No issues found" from a scan whose input list was empty.
- ❌ Treating *"the tool exited 0"* as *"the property holds"*.
- ❌ Adding a meta-check that the check ran, and declaring the class closed. It moved up one level.
- ❌ Green-with-exceptions without an explicit, logged user override.
- ❌ Presenting the agent's own summary sentence as the measurement. Show the raw tool output —
  runner summary, file listing, row count — above the interpretation.

## Telemetry

```yaml
measurement_integrity:
  gates_run: 5
  gates_with_scope_reported: 5        # must equal gates_run
  blocked_on_empty_measurement: 1     # I2 fired — a false green was prevented
  declared_vs_observed_mismatch: 0    # denominator rule fired
  gates_never_red_ever: ["duplication"]   # unproven — candidates for prove-the-gate
```

`/learn` insights:
- `gates_with_scope_reported < gates_run` → a consumer is still emitting bare verdicts; wire it here.
- `blocked_on_empty_measurement ≥ 1` → the protocol paid for itself this session; keep the case as a
  regression example.
- A gate in `gates_never_red_ever` for > 3 sessions → run **Prove the gate** on it or drop it. An
  unproven gate is worse than no gate: it consumes trust without producing evidence.

## Why this is not a per-skill nicety

The moment one skill reports scope and its neighbours don't, a reader learns to read *"green"* as
*"green"* again — and the habit is what the protocol is actually protecting. Scope-reporting only
works if it is uniform: anywhere there is AI in the loop, the output says what it looked at and what
it didn't. That is the reason this lives in `_shared/` and not in the skill that discovered it.
