---
name: triage-scoring
description: Scoring rubric, cap rules, veto list and output template for do-ticket Phase 9.7 `triage` — the one-page ticket overview that tells the human HOW MUCH REVIEW EFFORT this ticket deserves. Advisory to the human only; never changes agent behaviour.
---

# triage — how much review effort does this ticket deserve?

## Why this phase exists

Every other gate in do-ticket asks *"is the work correct?"*. This one asks a different question, and it
asks it on behalf of the **human**, not the agent:

> Reading the Jira ticket, how much of my own attention does this actually need — and is the ticket
> lying to me about that?

A ticket that reads like "add one field to the export" can be a 6-repo contract change; a ticket that
reads like a platform-wide migration can be three lines behind a feature flag. The human cannot see
which from the ticket text, so they either over-review everything (slow) or auto-accept everything
(risky). Triage prices the ticket in code terms, once, on one page, so the human can spend attention
where it buys something.

**Two failure modes this phase is built against:**

1. **The trap** — ticket looks easy, code is not. This is the expensive one. A high `CLEAR` on a ticket
   that deserved a low one converts directly into an un-reviewed defect.
2. **The average that hides the spike** — five benign axes and one catastrophic axis must NOT average
   into "fine". Hence the cap rules below: **the worst axis sets the ceiling, not the mean.**

## Hard constraints

- **Advisory to the human only.** The report NEVER changes what the agent does: no gate is auto-accepted,
  no phase is skipped, no rigor is reduced because `CLEAR` is high. The agent keeps asking exactly as it
  would have. Choosing to take the recommended/first option is the **user's** decision, made with this
  file open. Any drift toward "score was high so I skipped X" is a bug in the run, not an optimisation.
- **No source reads.** Triage is a do-ticket-internal phase and inherits the skill's no-inline-code-reads
  rule. Everything is derived from artifacts already on disk (`plan.md`, `requirements-analysis.md`,
  `ticket-context.yaml`, `fe-impact-check.md`, `{project_docs}/**`). If those don't support a score,
  that is a **confidence** finding, not a licence to go grep the repo.
- **One page, overview only.** Hard cap **60 lines**. Service/repo granularity — never a file list, never
  a code snippet, never a per-AC breakdown. Detail already lives in `plan.md` and
  `review-priorities.md`; this file exists to tell the human *whether to open them*.
- **Never leaves the local ticket dir.** Not attached to Jira, not rendered into `spec.md`, not quoted in
  a PR description. It is a note to whoever runs the ticket; published, its risk scores read as a verdict
  on the ticket (or on whoever wrote it).
- **The prior is recorded before the evidence.** `ctx.triage_prior` is written at Phase 2 (`classify`)
  from the ticket text alone. Computing it here, after reading the plan, would make the trap flag
  unfalsifiable hindsight.

---

## Inputs → what each one is allowed to score

| Source | Feeds axis |
|--------|-----------|
| `plan.md` — repos, layers, migration section, endpoint list, decision confidences, `## Structural quality` | spread, volume, difficulty, ambiguity |
| `requirements-analysis.md` — open questions, conflicts, edge cases | ambiguity |
| `ticket-context.yaml` — `ticket_type`, `risk_profile`, `risk_factors`, `po_escalation[]`, `enrichment_open_questions_count`, `dps_final_status` | ambiguity, risk |
| `fe-impact-check.md` — verdict | spread |
| `{project_docs}/incidents/incidents.yaml` | risk |
| `{project_docs}/_quickref.yaml`, `conventions.md`, `patterns/_index.yaml` | difficulty (a known pattern LOWERS difficulty) |
| `{project_docs}/code/domain_index.yaml` freshness, `_index.yaml` phase_readiness | confidence |
| `test-cases.md` — how each case is provable | verifiability |

---

## The six axes

Each scored **1–5** (1 = benign, 5 = severe). Score from observable signals, not vibes. Pick the
**highest** band whose signal is present.

### 1. `spread` — blast radius (weight 5)
| | Signal |
|-|--------|
| 1 | one repo, one layer, internal only |
| 2 | one repo, multiple layers |
| 3 | 2 repos, OR a public API response/request shape changes, OR FE consumes a touched endpoint |
| 4 | 3+ repos, OR shared library touched (version bump consumed by others), OR a message/event contract changes |
| 5 | cross-service contract + shared lib + DB schema together, OR a change every service reads (auth, config, base entity) |

### 2. `volume` — size of the change (weight 3)
Estimated from `plan.md` change list. State the estimate; it is checked later at Phase 12.
| | Signal |
|-|--------|
| 1 | ≤2 files, ≤50 added lines |
| 2 | ≤5 files, ≤150 |
| 3 | ≤12 files, ≤400 |
| 4 | ≤25 files, ≤900 |
| 5 | >25 files or >900 lines — also a split candidate |

### 3. `difficulty` — technical difficulty (weight 4)
| | Signal |
|-|--------|
| 1 | pure CRUD/mapping/config; an existing pattern covers it end to end |
| 2 | straight business rule in one service; sibling pattern exists |
| 3 | new query shape / EF migration / mapping across aggregates; no exact pattern |
| 4 | concurrency, async orchestration (workflow/queue/scheduler), date-time & timezone semantics, state-machine/lifecycle edits, bulk-performance work |
| 5 | any of the above **on a code path the project's `_quickref`/`incidents` marks as a known hard zone**, or an invariant has to be re-derived |

### 4. `ambiguity` — how open the requirement still is (weight 5)
| | Signal |
|-|--------|
| 1 | AC measurable, no open questions, no PO escalation |
| 2 | 1 open question, non-blocking; all plan decisions ≥ medium confidence |
| 3 | 2–3 open questions, OR ≥1 `low`-confidence plan decision, OR AC needs interpretation to test |
| 4 | blocking open question answered by assumption, OR `po_escalation[]` non-empty, OR speed-mode/self-detailing was used |
| 5 | expected behaviour genuinely undecided — the ticket is being specified while it is built |

### 5. `risk` — what breaks if it is wrong (weight 6)
| | Signal |
|-|--------|
| 1 | additive, feature-flagged or new-endpoint-only; nothing existing changes behaviour |
| 2 | changes behaviour of one existing flow, fully covered by tests |
| 3 | changes a shared/existing behaviour many callers rely on, OR touches an existing guard/validation |
| 4 | permission/auth surface, tenant/cluster-scoped config, deletes or loosens an existing guard or test, OR overlaps a recorded incident on the same path |
| 5 | writes/backfills existing production rows, money, irreversible one-way change |

### 6. `verifiability` — inverted (weight 4)
How provable is "it works" **before** merge? Low provability means human review has to carry the load.
| | Signal |
|-|--------|
| 1 | deterministic unit test proves the behaviour |
| 2 | unit + local integration test against a real DB |
| 3 | needs `api-test` against running services |
| 4 | needs GUI/manual, an external system, a timer/scheduled trigger |
| 5 | only observable on production data, or after elapsed real time (day-rollover, retention) |

---

## Score

```
penalty = 5·(spread−1) + 3·(volume−1) + 4·(difficulty−1) + 5·(ambiguity−1) + 6·(risk−1) + 4·(verifiability−1)
CLEAR   = max(0, 100 − penalty)
```

Then apply **caps** — take the **lowest** applicable ceiling. This is the anti-averaging teeth:

| Condition | `CLEAR` ceiling |
|-----------|-----------------|
| any axis = 5 | 35 |
| `risk` ≥ 4 OR `ambiguity` ≥ 4 | 45 |
| ≥2 axes ≥ 4 | 40 |
| any other single axis = 4 | 60 |
| `confidence` = low | 55 |
| any **VETO** present | 20 — and mode is forced **RED** |

### VETO list (forces RED regardless of score)
- Writes, moves or backfills **existing** rows in a real environment (a migration adding a nullable
  column is not a veto; one that rewrites data is).
- Auth / permission / token surface.
- Money, billing, invoicing.
- Shared-library version bump that other repos consume in this same ticket.
- An existing guard, validation or **passing test** is deleted or loosened.
- Exact overlap with a tier-1 entry in `incidents.yaml` on the same code path.
- Irreversible / one-way (data deletion, external system notified, published contract).

### Mode
| `CLEAR` | Mode | What it means for the user's own effort |
|---------|------|-----------------------------------------|
| 80–100 | **GREEN** | Recommended/first option is safe to take at most gates. Read summaries, not diffs. |
| 60–79 | **AMBER** | Read `review-priorities.md` + the diff of the 1–3 core files. Decide the rest quickly. |
| 40–59 | **ORANGE** | Read the plan and the whole logic diff. Do not auto-accept anything. |
| 0–39 or VETO | **RED** | Decide every gate yourself. Consider splitting the ticket. |

### Confidence (reported separately — never folded into `CLEAR`)
`high` — plan names concrete files/services, `domain_index.yaml` fresh, no unresolved open question,
`fe-impact-check` ran (or provably N/A).
`medium` — one of those is missing or stale.
`low` — plan is lite/abstract, or `domain_index` stale, or ≥2 unresolved open questions, or the ticket
type skipped `analyze`. Low confidence caps `CLEAR` at 55, so a shaky estimate can never read GREEN.

### Trap flag
Compare `ctx.triage_prior` (recorded at Phase 2 from ticket text only) with `CLEAR`:

| Prior | `CLEAR` | Flag |
|-------|---------|------|
| `easy` | < 60 | **⚠ TRAP — looks easy, the code is not.** Name the single axis that did it. |
| `hard` | ≥ 80 | **✔ Lighter than it looks** — ticket reads big, change is narrow. Say why. |
| otherwise | — | no flag |

`triage_prior` at Phase 2: `easy` = title ≤12 words, one entity, ≤3 AC, no cross-service/platform words ·
`hard` = multiple services or entities named, ≥8 AC, or words like *align / platform-wide / migrate /
all / every / entire* · else `normal`.

---

## Phase 12 recalibration (mandatory — the report is checked, not just written)

An estimate nobody scores is an estimate that drifts. At Phase 12 (`regression`), when a real diff
exists, append the `## Reality check` block:

1. `git diff --shortstat` **per repo** (each command with its own `cd` — a bare git command reuses the
   previous repo's cwd and succeeds with the wrong answer).
2. `error_ratio = actual_files / predicted_files`.
3. Downgrade one mode band, and print the warning line, if **any** holds:
   - `error_ratio ≥ 2` or `≤ 0.4`
   - a repo appears in the diff that triage did not list
   - a VETO condition became true during implement (guard removed, migration added)
4. A downgraded verdict is stated in one line, not rewritten silently — the original score stays
   visible so the miss is legible.

---

## Output template — `{ticket_dir}/ticket-triage.md`

Read by the user, not consumed by another skill. Hard cap 60 lines. Reason columns ≤ 12 words each.

On an update cycle (`plan` re-ran), overwrite the file but keep one line under the header:
`Previous round: <mode> · CLEAR <n>` — a ticket whose price climbs AMBER → ORANGE across rounds is itself
the signal, and it vanishes if each round silently replaces the last.

```markdown
# <TICKET_ID> — Ticket overview

**<GREEN|AMBER|ORANGE|RED>** · CLEAR **<0-100>**/100 · confidence **<high|medium|low>** · type `<ticket_type>`
> <One sentence: what this ticket really does in the code, and how much of your attention it needs.>

## Scores
| Axis | Score | Why |
|------|:-----:|-----|
| Spread | x/5 | <≤12 words> |
| Volume | x/5 | ~N files, ~L lines |
| Difficulty | x/5 | <≤12 words> |
| Ambiguity | x/5 | <≤12 words> |
| Risk | x/5 | <≤12 words> |
| Verifiability | x/5 | <≤12 words> |
<If a cap applied: one line "Cap: <reason> → CLEAR held at <n>.">

## Scope
- Repos/services: <names, no file paths>
- Layers: <api / application / domain / infra / FE>
- DB: <none | nullable column added | existing data changed>
- Contract: <unchanged | response shape | event/message>
- FE: <not involved | has a consumer, verdict from fe-impact-check>

## Red flags
- <VETO or trap, at most 4 lines — if none: "None.">

## How to review
- Mode: **<GREEN|AMBER|ORANGE|RED>** — <one sentence explaining it>
- Read closely: <2–4 named gates, e.g. "plan §Structural quality", "code-quality-review", "api-test">
- Safe to take the recommended option: <the remaining gates, on one line>

## Confidence of this report
<high|medium|low> — <what is missing, and what would change this score>

## Reality check
<Empty until Phase 12. Then: predicted N files / L lines → actual N' / L' (error ×r).
Verdict: keep <mode> | downgrade to <mode> because <reason>.>
```

### Worked example (illustration only — not a real ticket)

```markdown
# PROJ-1234 — Ticket overview

**AMBER** · CLEAR **60**/100 · confidence **high** · type `crud-feature`
> Adds 2 fields to the export + 1 field to the detail response; touches the shared lib, so 3 repos rebuild.

## Scores
| Axis | Score | Why |
|------|:-----:|-----|
| Spread | 4 | shared lib bump, 3 repos consume it |
| Volume | 2 | ~5 files, ~120 lines |
| Difficulty | 2 | plain mapping, sibling pattern exists |
| Ambiguity | 1 | AC measurable, no open questions |
| Risk | 1 | fields only added, no existing behaviour changes |
| Verifiability | 2 | unit + real-DB integration test is enough |
Cap: spread = 4 → raw 74, held at 60.

## Scope
- Repos/services: acme-shared, acme-api, a sibling service
- Layers: application + domain model
- DB: none
- Contract: response shape of 1 export endpoint
- FE: has a consumer — fe-impact-check verdict SAFE

## Red flags
- Shared lib bump: rebase + set version = base+1 before building the other 2 repos.
- ⚠ TRAP: ticket reads like "add a field" (prior = easy) but spreads across 3 repos.

## How to review
- Mode: **AMBER** — light logic; what deserves a look is the multi-repo build order.
- Read closely: plan §Structural quality (where the field lives), pre-push (shared lib version), ci-check.
- Safe to take the recommended option: test-cases, unit-tests, qa-checklist, pr-ready.

## Confidence of this report
high — plan lists the right files, domain_index is fresh, fe-impact ran.

## Reality check
Predicted 5 files / 120 lines → actual 7 files / 155 lines (error ×1.4). Verdict: keep AMBER.
```
