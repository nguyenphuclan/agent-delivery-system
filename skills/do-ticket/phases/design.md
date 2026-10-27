# do-ticket — design part

Phase procedure for phases 7 `invariant-scope`, 8 `test-cases`, 8.7 `blast-radius`, 9 `plan`, 9.5 `fe-impact-check`, 9.7 `triage`, 9.8 `legacy-contract`. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here (`blast-radius.md`, `triage-scoring.md`, …) is a do-ticket companion file in
`~/.claude/skills/do-ticket/`.

## Phase 7 — `invariant-scope`
Skipped when `ticket_type ∈ {doc-only, hotfix, refactor}` or no entity has a domain shard.

## Phase 8 — `test-cases`
Show count + offer edit → user picks proceed/edit. **Error-path coverage check:** every `must not / cannot / reject when` constraint in analysis must have ≥1 negative test case → otherwise G1.

## Phase 8.7 — `blast-radius`

Counts the legacy surfaces the change touches, inventories the extension points that already exist, and
**arms the gates**. Counting only — **no design**. Full spec, commands and artifact shape in
`blast-radius.md`.

**Why it exists:** on PROJ-11332 four design shapes died one after another, each on a fact a grep produces
in seconds (a status field assigned in 183 places · an updater that turned out to be an upsert · a flow
that did not exist). The design ran before the read.

**Step 0 is a cheap probe:** if nothing shared is touched, write 5 lines with `armed_gates: none` and stop.
That is the intended path for most tickets — do not manufacture surfaces to look thorough.

**Output:** `{ticket_dir}/blast-radius.md` + `ticket-context.blast_radius.*` + `ticket-context.armed_gates[]`.

**Gate:** `plan` (9) may not be written until this artifact exists. Any count in `plan.md` absent from
`blast-radius.md` is a defect. *"Rather than adding infrastructure"* is not a valid reason until the
extension-point inventory is on disk **and empty**.

**Skip:** `doc-only`, `spike`. **Lite** (touched-method counts only, no inventory): `hotfix`.

## Phase 9 — `plan`
- Save `plan_written_at: <now>`.
- **Read `blast-radius.md` first.** Every count in the plan must come from it; never re-derive or estimate.
  With `armed_gates: none`, plan at normal depth and skip the legacy-contract machinery entirely.
- **DPS handoff mode:** pre-set `strategies_picked.implement = <dps_suggested_strategy>` before strategy selection runs (treat as user-provided override). Surface any `dps_open_assumptions` not yet acknowledged as G1 items here.
- Pattern injection: load `do-ticket-patterns.md` → match registry → if match found: inject as decision card. If no match → run **auto-induction** (sample 3-5 sibling files) per `do-ticket-patterns.md` "Auto-induction" section → inject + **write-back**: append discovered pattern to `{project_docs}/patterns/_index.yaml` (create file if missing) + update `_index.yaml` artifacts.patterns. This is how `patterns/_index.yaml` is bootstrapped — it does not exist until first plan run, and grows ticket-by-ticket.
- Every non-trivial decision logged per `_shared/decision-confidence-protocol.md` with confidence tag (high/medium/low) + evidence cards.
- **Every decision also carries `mode`** (router § Decision modes) → write `ticket-context.decisions[]` per
  `ticket-context-schema.md`: `M1` (+ the command that settled it) · `M2-open` (+ `options_count`) ·
  `M2-absolute` (+ `source`, `revisit_when`) · `M3` (+ `rounds` that carried a **new code fact**). The mode
  is a router, not a label — it records what was owed. Checked at Phase 9 exit and again at G-T0.
- **Structural-quality gate (per `code-quality-review.md` §A):** fold a `structural_quality` decision group into the plan — answer the 5 plan-time-knowable questions (layer placement · new-vs-extend-fat-method · improve-vs-mirror (do not copy a weak nearby pattern just because it exists) · duplication-of-existing-logic · base-value-impact via `_field_impact.yaml` lookup). Record under a `## Structural quality` heading in `plan.md` + `ticket-context.structural_quality_decisions[]`. These ride the confidence-gated review below — a flagged/`low`-confidence answer surfaces in the ≤5 CRITICAL items; all-clean auto-proceeds with no extra prompt. Skipped for `doc-only`, `spike`, `hotfix`; `migration-only` runs the layer-placement + base-value-impact questions.
- Lite mode for `bugfix-small` and `hotfix`: ≤1-page plan.

**Confidence-gated review (Q6):**
After plan.md written, compute summary:
- avg_confidence = average of all decision confidences
- low_count = count of decisions with confidence=low
- critical_mappings = count from `mapping-integrity-protocol.md` Tier 4/5 if relevant

Decision tree:

| Condition | Action |
|-----------|--------|
| **Any armed gate from Phase 8.7** — `>20` write sites · `>1` write path · any upsert on a creation path · a field whose meaning moves · `no_marker: true` | **Auto-proceed DISABLED.** Show the options table. A self-scored confidence on an unchallenged single design is exactly the number that cannot be trusted here — *loose threshold = blind threshold* |
| `avg_confidence > 0.85` AND `low_count == 0` AND `critical_mappings == 0` AND no flagged risks AND `armed_gates: none` | **Auto-proceed** to next phase. Print 1-line summary: *"Plan written. Confidence: high (12 decisions, 0 low). Proceeding."* |
| Any low-confidence decision OR any CRITICAL mapping OR `risk_profile == critical` OR plan flagged a risk | **G1 surface CRITICAL items only** (per `risk-prioritization-protocol.md`). Show ≤5 items, each with quick-verify action. Do NOT show full plan. User chooses per item: confirm / change / G1-block-and-edit. |
| User passes `do-ticket <ID> plan` (force-restart from plan) | Always show full plan for review (manual override) |

Goal: stop interrupting user when nothing's worth interrupting for. Surface only what matters.

## Phase 9.5 — `fe-impact-check`

Lazy FE compatibility check using the just-written plan as scope. Catches FE-BE contract drift, cardinality mismatches, and missing i18n BEFORE implement — the place mid-implementation surprises usually surface.

**Skip if:** `ticket_type ∈ {fe-only, doc-only, hotfix, refactor, spike}` OR plan touches no public API endpoint OR all affected endpoints are admin/internal (no FE caller).

**Algorithm:**
1. Extract `affected_endpoints[]` + proposed response shape / cardinality / status codes from `plan.md`.
2. Quick FE-consumer probe: grep FE repo for each endpoint URL. None consumed → write `fe-impact-check.md` with verdict `SKIPPED` and continue.
3. Otherwise spawn a narrow Explore sub-agent. Prompt carries the BE plan context (proposed shape, cardinality, status codes) + targeted FE grep scope (only the affected endpoints). Sub-agent reports conflicts (file:line + nature) and a verdict.

**Verdict gate:**

| Verdict | Action |
|---------|--------|
| `SAFE` | Continue to Phase 10. |
| `NEEDS_FE_CHANGE` | G1 surface to user: file follow-up FE ticket OR ack as known gap and continue. |
| `NEEDS_BE_ADJUST` | Loop back to Phase 9 `plan` to reconcile. |

**Output:** `tickets/{ID}/fe-impact-check.md` (small, ticket-scoped — NOT a scan-init artifact).

**Rationale:** Pre-scanning FE module structure is low-ROI for BE engineers. The only FE knowledge a BE engineer actually needs is contract compatibility per touched endpoint — and that is cheapest to derive at plan-time, scoped by the actual BE proposal, with always-fresh greps. Slip files pre-built into scan-init would go stale; an upfront full FE scan would over-collect FE wizard/i18n/state detail that the BE engineer never uses.

## Phase 9.7 — `triage`

Prices the ticket for the **human**: one page saying how much of the user's own review attention this
ticket deserves, and whether the ticket text is lying about that. Full rubric, cap/veto rules and the
output template live in `triage-scoring.md`.

**Output:** `{ticket_dir}/ticket-triage.md` — read by the user, consumed by no skill. Hard cap 60 lines,
service/repo granularity, no file lists, no snippets.

**Algorithm:**
1. Score six axes 1–5 from artifacts already on disk (`plan.md`, `requirements-analysis.md`,
   `ticket-context.yaml`, `fe-impact-check.md`, `{project_docs}/**`): `spread` · `volume` ·
   `difficulty` · `ambiguity` · `risk` · `verifiability`. **No source reads** — the no-inline-code-reads rule
   applies here too; an unsupported score is a *confidence* finding, not a reason to grep.
2. `CLEAR = max(0, 100 − Σ wᵢ·(axisᵢ−1))`, then apply the **lowest** applicable cap. The worst axis sets
   the ceiling — a mean would let one catastrophic axis average into "fine".
3. Evaluate the VETO list → any hit forces mode **RED** (`CLEAR ≤ 20`).
4. Report `confidence` (high/medium/low) **separately**, never folded into `CLEAR`. `low` caps `CLEAR` at
   55, so a shaky estimate can never read GREEN.
5. Trap flag: compare `ctx.triage_prior` (written at Phase 2 from ticket text alone) against `CLEAR`.
   `easy` + `CLEAR < 60` → **⚠ TRAP**, and name the axis responsible.
6. Write `triage` block to `run-telemetry.yaml` (schema in `run-telemetry-schema.md`).

**Then print 3 lines and continue — do not block.** No user gate: this phase asks nothing. It hands the
user a price list; whether they spend less at the gates that follow is their call, not the agent's.

**Skipped for:** `doc-only`, `spike`, `hotfix` (no plan to price; hotfix is critical by definition).
**Confidence capped at `medium`** for `bugfix-small` and `refactor` — a lite plan cannot support `high`.

**The agent's own behaviour is unchanged by the score.** Every gate fires as it would have, with the same
wording and the same evidence. If a future run reads `GREEN` and quietly softens a gate, that is a defect
in the run — the whole value of this file is that the human can trust it without the agent acting on it.

## Phase 9.8 — `legacy-contract` (T0)

**Skipped entirely when `ticket-context.armed_gates` is empty.** Most tickets skip. Full spec, gates and
artifact shape in `legacy-contract.md`.

Assembles **one** file the user approves — `{ticket_dir}/legacy-contract.md` — from `blast-radius.md`
(the counts + the extension-point inventory) and `plan.md` (the shape + options). The user approves a
**predicate**, not a plan, so Phase 12.7 can re-check it by machine.

**This phase RUNS the frozen tests, before any code changes.** Do not edit a repo while its baseline suite
is still running. A baseline is not a promise:

- Print the command, the pass/fail counts, and **the name of every failure**.
- **Record the preconditions.** A baseline captured with Docker down is blind to every DB integration test
  while still printing a comfortable *"147 passed"* — that is what happened on PROJ-11350.
- A baseline whose failures are unnamed hides which capabilities were never exercised at all.

**Gate (G-T0):** print the self-check block, then ask once. Blocking conditions:
`agent_owned_open != 0` · any open choice in the plan with no options · `extension_point: EDIT` while the
inventory has an unexplained "fits: yes" row · frozen baseline missing or its failures unnamed.

**Mode gate** — walk `ticket-context.decisions[]`. Each is a **defect**, not a warning:

| Defect | Meaning |
|---|---|
| `M1` with an open question | it was settleable — settle it, do not ask |
| `M2-open` / `M3` with `options_count < 2` | a bare choice handed to the user |
| `M2-absolute` with no `source` | an outside constraint becomes permanent by accident |
| `M3` with `rounds == 0` | co-solve claimed, never run — **the PROJ-11350 failure exactly** |

**Anti-gaming:** never lower the count by **downgrading a mode**. Relabelling an `M3` as `M2-open` to dodge
the rounds check is the severest defect here — worse than the missing round.

**Phase 11 `implement` may not start** while `armed_gates` is non-empty and `contract_approved_at` is unset.
