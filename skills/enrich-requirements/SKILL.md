---
name: enrich-requirements
description: PO-proxy phase. Reads raw Jira requirements (requirements.md) and enriches them into a detailed product spec — user flows, acceptance criteria in Given/When/Then form, edge cases a domain-aware PO would catch, and open questions to escalate. Reads project docs (domain index, flows, concepts, lifecycle, incidents) — NEVER reads source code. Output: requirements-enriched.md, consumed by analyze-requirements as the new input baseline.
---

## Trigger

User runs: `enrich-requirements <TICKET_ID>`

If `<TICKET_ID>` is missing → ask: *"Which ticket ID? (e.g. PROJECT-1234)"*

Auto-invoked by do-ticket as Phase 5.5 between `requirements` (5) and `analyze` (6).

---

## Purpose — read this first

This skill exists to fix a specific gap: Jira tickets from external POs are usually **thin** — they describe intent but skip flows, acceptance criteria, and edge cases. Without enrichment, the BA step (`analyze-requirements`) absorbs two different jobs: "fill in what PO didn't write" + "map to domain/code". Splitting them gives the user a clean checkpoint to review *product completeness* before technical analysis kicks in.

**You are playing PO-proxy.** Your job is to turn a thin ticket into the spec a careful PO would have written, using only product-level knowledge (domain docs), never source code.

**Two distinct jobs — keep them separate.** Enrichment is really two independent things:
1. **Structuring** — turning thin intent into ordered flows + testable acceptance criteria. A *thin* ticket needs this.
2. **Domain-grounding** — adding the edge cases and cascade behavior the project's domain docs / incidents / lifecycle know about, and resolving open questions against those docs. **Even an already-well-structured ticket needs this**, because whoever authored it (a PO, or an upstream ticket-authoring step) did not have the project's domain index.

Some upstream processes produce **spec-grade input**: requirements that already arrive with structured acceptance criteria, explicit scope, and explicit open questions parked for downstream resolution. For spec-grade input your value is **domain-grounding + open-question triage, NOT re-structuring** — do not rewrite ACs that are already clean; spend your effort where the author could not reach (the domain docs). Detect this from the *shape* of the input (structured ACs + scope + pre-existing open questions present) and downshift accordingly.

---

## Hard boundary — what you CAN and CANNOT read

### CAN read (product-layer knowledge)
- `{ticket_dir}/requirements.md` — the raw Jira extract
- `{project_docs}/_quickref.yaml` — entity index summary
- `{project_docs}/domain/<Entity>.yaml` — entity fields, states, business rules
- `{project_docs}/domain/_glossary.yaml` — terminology, overloaded terms
- `{project_docs}/flows/flow_index.yaml` + `{project_docs}/flows/*.md` — existing user flows
- `{project_docs}/concepts/*.md` — business concept docs (overloaded terms, subtypes, neighbors, see_also)
- `{project_docs}/lifecycle/*.md` — state machines, cascade rules, valid transitions
- `{project_docs}/incidents/incidents.yaml` (tier-1 entries only) — "what edge cases have bitten us here"
- `{project_docs}/conventions.md` — business naming, terminology rules
- `{output}/tickets/<OTHER_TICKET>/requirements-enriched.md` — only when a sibling/similar feature exists and is explicitly referenced in `requirements.md`

### CANNOT read (these are BA's / plan's job)
- Any source code file (`.cs`, `.ts`, `.py`, `.go`, etc.)
- DB migration files / raw schema files
- Test source files
- `{project_docs}/code/*.yaml` shards (BA reads these to map requirements to code — not your job)
- `{project_docs}/db/db_index.yaml` (BA reads this for column types — not your job)

**The principle:** anything written for a human-as-PO to understand business behavior → allowed. Anything written for a compiler/runner → BA's job. If you find yourself wanting to grep source code to answer a question, that question goes into the "Open Questions" section for PO or gets deferred to BA.

---

## Files to read — exact order

### Required
- `{ticket_dir}/requirements.md`

**If missing** → stop: *"requirements.md not found. Run `jira-to-requirements <TICKET_ID>` first."*

### Required (resolve via _index.yaml)
- `{project_docs}/_index.yaml` — resolve `{project_docs}` path per `_shared/agent-docs-layout.md`. Use the `artifacts` block to find the actual paths for domain, flows, concepts, lifecycle, incidents.

**If `{project_docs}` cannot be resolved** → continue but flag: *"project_docs path not resolved — enrichment will rely only on requirements.md and general domain knowledge."*

### Conditionally read (based on requirements content)
- If requirements mention an **entity name** → read `{project_docs}/domain/<Entity>.yaml` (one file per entity)
- If requirements mention a **flow keyword** (e.g. "reassignment", "flagging", "sync") → read matching entry from `{project_docs}/flows/flow_index.yaml` + the flow's detail .md
- If requirements use **vague parity language** ("similar to", "same as", "consistent with X") → read the entity shard for X
- If requirements touch a **lifecycle** (state transitions, status changes) → read `{project_docs}/lifecycle/*.md` for the relevant entity

**Do NOT do a full project_docs scan.** Read only what the ticket actually references.

---

## Steps

### 1. Inventory raw requirements

Read `requirements.md` and list each requirement with a stable ID (`R1`, `R2`, …). Note any open questions already flagged by jira-to-requirements.

### 2. Classify enrichment need (two independent decisions)

Score each requirement on three axes (1–5 each), but read them as **two separate decisions** — structuring and domain-grounding are decided independently:

- **Flow clarity** (structural): does the requirement describe what the user does, in order?
- **Criteria clarity** (structural): are there testable acceptance criteria, or just intent?
- **Edge-case coverage** (domain): does it state what happens off the happy path (empty, invalid, permission denied, state mismatch, concurrent edit)?

**Decision 1 — structuring** (from flow + criteria, score 2–10):

| Structural score | Structuring action |
|---|---|
| 9–10 | **Skip structuring** — copy flow + ACs through verbatim; do NOT rewrite them |
| 5–8  | Standard — fill in missing flow / criteria from domain docs |
| 2–4  | Deep — intent-only; produce a full Given/When/Then spec from scratch |

**Decision 2 — domain-grounding** (independent of Decision 1): **always run it when `{project_docs}` resolved**, even for a requirement that skipped structuring. Structural completeness ≠ domain-grounded — a clean set of ACs can still miss an incident-proven edge case or a lifecycle cascade the author never saw. Domain-grounding = incoming open-question triage (step 3-pre), the edge-case probe (3c), and PO open questions (3d). Skip it only when `{project_docs}` could not be resolved, or the requirement has no entity / lifecycle / flow surface at all.

> **Pass-through is a structuring verdict, not a license to skip everything.** A requirement can "skip structuring" yet still receive domain-grounding. Inventing structure for an already-clean AC is as wrong as skipping a known edge case — do the part the author could not, skip the part they already did.

**Overall enrichment verdict (top of output):**
- A requirement counts as pass-through only if it contributed **nothing**: structure complete AND domain docs surfaced no new edge case AND no open question was touched.
- All requirements pass-through → `PASS_THROUGH`. Any requirement that received structuring OR domain-grounding → `ENRICHED`.

### 2.5. Ambiguity & coverage scan (Spec Kit `clarify` taxonomy)

Before drafting per-requirement enrichment, scan the **whole ticket for under-specification** using the team's Spec Kit `clarify` taxonomy. We do NOT run the `/speckit.clarify` slash command (the render contract forbids it) — we apply its *discipline*. For each category, mark **Clear / Partial / Missing** as an **internal coverage map** (do NOT emit it as a new output section — it changes the spec structure; it only *feeds* the existing Edge Cases / Acceptance Criteria / Open Questions sections, exactly as `/speckit.clarify` keeps its map internal):

- **Functional scope & behavior** — core goal, success criteria, explicit out-of-scope, role/persona differences
- **Domain & data model** — entities, attributes, identity/uniqueness, lifecycle/state transitions, scale assumptions
- **Interaction & UX flow** — critical journeys, and the three states: **empty / loading / error**
- **Non-functional** — performance, reliability, security/permission, observability, compliance (only where the feature plausibly hits them)
- **Integration & external deps** — external services + failure modes, import/export formats, versioning
- **Edge cases & failure handling** — negative scenarios, throttling, concurrent-edit conflict (the Step 3c checklist feeds this category)
- **Constraints & tradeoffs** — hard business constraints, explicitly rejected alternatives
- **Terminology & consistency** — one canonical glossary term used throughout; flag synonyms / deprecated terms (cross-check `domain/_glossary.yaml`)
- **Completion signals** — is every AC **binary and testable**? is "done" measurable?
- **Placeholders / vague language** — `TODO`s, and **un-quantified adjectives** ("robust", "fast", "intuitive", "easy", "as needed") that no test can be written against

A `Partial`/`Missing` category becomes a candidate open question (Step 3d) **unless** a project doc resolves it (→ record it resolved, with citation, like an edge-case) or it is better deferred to BA/plan (surface as `[defer to BA / repo]`). Prioritise candidates by **Impact × Uncertainty** and carry at most **5** into PO open questions (Step 3d); the rest become `[assumed default — PO confirm]` or are deferred.

> **This scan is the lever that makes the spec QC-derivable and FE-fillable.** A spec that is Clear across the taxonomy is one QC can turn into an end-to-end test case and FE can dress with UI specifics without guessing — the direct fix for "spec too BE / QC can't write e2e".

### 3-pre. Ingest & triage incoming open questions

Some inputs arrive with **open questions already parked by the upstream author** — a PO note, or a ticket-authoring step that deliberately deferred repo/domain-answerable unknowns. Do not ignore them, and do not blindly re-ask them.

For each open question already present in `requirements.md`, sort it into exactly one bucket:

1. **A project doc answers it** (domain shard rule, lifecycle transition, flow, incident) → **resolve it**; record the answer with its source, exactly like an edge-case citation. It leaves the open-questions list.
2. **Docs can't answer, but a PO could decide it** → keep it as a PO open question (carried into Step 3d).
3. **Needs source code / repo to answer** → carry it forward verbatim, tagged `[defer to BA / repo]` — it is not a PO question and not yours to resolve.

This is the inverse of Step 3d: there you *raise* questions the docs can't answer; here you *retire* questions the docs *can*. An upstream author without the project's domain index parks exactly the questions you are positioned to close — closing them is the highest-value thing you do for spec-grade input.

### 3. For each requirement that needs enrichment

Fill in the following, drawing ONLY from raw requirements + project docs (no code):

**3a. User flow** — happy path + obvious alternates. Steps from the actor's perspective ("PO opens X, sees Y, clicks Z").

**3b. Acceptance criteria (Given/When/Then)**
- Given: precondition (state, role, data)
- When: trigger (user action, scheduled event, message)
- Then: observable outcome (state change, UI feedback, downstream event)
- Each AC is testable and binary (pass/fail, no judgment).

**3c. Edge cases the PO didn't mention**
Use this checklist — only include items the requirement plausibly hits:
- Null / empty input
- Maximum length / value
- Permission denied (which roles cannot do this?)
- State mismatch (operating on entity in wrong state)
- Concurrent edit (two actors changing same entity)
- Duplicate request (idempotency)
- Partial failure (downstream call fails mid-flow)
- Cascade behavior (does this trigger anything downstream that's in scope?)

For each edge case, propose the **expected behavior** based on:
- Domain shard rules (e.g. `<Entity>.yaml` lists valid state transitions)
- Lifecycle docs (cascade rules)
- Incidents (have we seen this edge case before? what was the fix?)
- General sensible defaults if no doc covers it (mark these as `[assumed default — PO confirm]`)

**3d. Open questions for PO**
Anything you can't reasonably answer from project docs. Format each as:
- **Q:** [question]
- **Why it matters:** [which AC or edge case depends on this]
- **PO action:** [what kind of answer unblocks this]

Keep this section TIGHT — every open question costs a real PO conversation. If domain docs give a sensible default, propose it as `[assumed default — PO confirm]` rather than escalating.

### 4. Scope-completeness probe (light version of BA's sibling check)

Read `_quickref.yaml` and entity family clusters. For each primary entity touched:
- List sibling entities in the same family (e.g. `INBOUND_ORDER` siblings: `OUTBOUND_ORDER`, `SERVICE_ORDER`).
- For each sibling, check if `requirements.md` includes or excludes it.
- If not mentioned → add row to **Sibling Coverage Table** asking PO to confirm scope.

> **Note:** This duplicates a small slice of analyze-requirements' Scope Decision Table by design — catching scope ambiguity at PO-level is cheaper than at BA-level. BA will still run its own deeper check including code-level siblings; enrich's check is product-level only.

### 5. Write output

Write to `{ticket_dir}/requirements-enriched.md` (create or overwrite). Update `ticket-context.yaml` with:
- `fingerprints.requirements_enriched_sha`
- `enrichment_verdict`: `PASS_THROUGH` or `ENRICHED`
- `enrichment_open_questions_count`: int

---

## Output format

```markdown
# Requirements Enriched — <TICKET_ID>
**Enriched at:** <ISO datetime>
**Verdict:** PASS_THROUGH | ENRICHED
**Source:** requirements.md (Jira fetched at <ts>)
**Docs consulted:** [list of project_docs files actually read]

---

## Summary
<2-3 sentences: what this ticket asks for, in PO language, after enrichment>

---

## Sibling Coverage Table
> Siblings detected at PO level. Resolve before proceeding to BA analysis.
> If empty, all siblings are explicit in original requirements.

| # | Sibling Entity / Operation | Family | Mentioned in original? | PO decision needed |
|---|---|---|---|---|
| 1 | `<SiblingEntity>` | task_category | No | **(a) Include** / **(b) Exclude — reason: ___** |

*(Skip this section entirely if no unresolved siblings.)*

---

## Enriched Requirements

### R1 — <short label>

**Original (verbatim from requirements.md):**
> [exact text]

**Enrichment score:** <3-15> → <pass-through | standard | deep>

**User flow:**
1. [Actor action 1]
2. [System response 1]
3. [Actor action 2]
4. [System response 2]
5. [Outcome]

*Alternate flow — <when X>:*
1. ...

**Acceptance criteria:**
- [ ] **AC1.1** — Given <pre>, when <trigger>, then <outcome>
- [ ] **AC1.2** — Given <pre>, when <trigger>, then <outcome>

**Edge cases:**
- **EC1.1 (empty input):** Given <pre>, when <user submits empty X>, then <outcome>. *Source:* `<Entity>.yaml` field validation rule.
- **EC1.2 (permission denied):** Given <role without perm>, when <attempts action>, then <outcome>. *Source:* `[assumed default — PO confirm]`.
- **EC1.3 (state mismatch):** Given <entity in invalid state>, when <action>, then <outcome>. *Source:* `lifecycle/<entity>.md` — transition table.

**Open questions for PO:**
- **Q1.1:** [question]
  **Why:** Blocks AC1.2 — cannot determine outcome without this.
  **PO action:** Confirm whether <X> or <Y>.

---

### R2 — ...

---

## Pass-through requirements
<List of R-IDs where original was complete — no enrichment, just listed for visibility>

- **R5** — original was complete (score 14/15): "...".

---

## All open questions (consolidated)

| # | Question | Origin | Impacts | PO action / disposition |
|---|---|---|---|---|
| 1 | [Q from R1] | raised here | AC1.2 | Confirm X or Y |
| 2 | [Q carried from input] | from input | EC3.1 | **defer to BA / repo** — needs source code |

*Incoming open questions that a project doc answered are NOT listed here — they appear resolved under their requirement's edge cases with the doc cited. List here only what still needs a PO decision or is deferred to BA/repo.*

*(If zero open questions, write: "All requirements resolved from domain docs — no PO escalation needed.")*

---

## Docs consulted
- `_quickref.yaml`
- `domain/<Entity>.yaml`
- `flows/flow_<name>.md`
- ...

## Out of scope (carried over from requirements.md)
- ...
```

---

## Human gate

**Trigger:** Block after writing `requirements-enriched.md` if ANY of:
1. **Sibling Coverage Table has unresolved rows**
2. **Open Questions section is non-empty** AND any question is marked `blocking: true` (where the AC cannot be inferred without the answer)
3. **Verdict is `ENRICHED` and the user has not yet acknowledged the enriched spec** (always require a confirmation pass — this is the user's chance to spot enrichment errors or push back to the real PO)

**What to show:**
- Print: *"Enriched requirements written to `requirements-enriched.md`. Verdict: `<PASS_THROUGH | ENRICHED>`. Open questions: `<N>`. Sibling decisions pending: `<N>`."*
- If `PASS_THROUGH` and zero open questions → still ask: *"Original requirements were complete (score >=12 on all). Proceed to BA analysis? (y/n)"*
- If `ENRICHED` → ask: *"Review the enriched spec — does it match PO's actual intent? Any open questions to escalate to PO via Jira comment before BA? (y/n/edit)"*
  - `y` → proceed
  - `n` → ask which sections to revise; user can also choose to post open questions to Jira (use `jira_add_comment` MCP if user confirms)
  - `edit` → user edits `requirements-enriched.md` directly; re-read after they signal done

**After user responds:**
- If user posts open questions to Jira → log the comment IDs to `ticket-context.po_escalation[]` and offer to mark `phase: blocked, blocked_reason: "awaiting PO answers on N questions"`.
- Otherwise → mark phase complete, proceed.

Save state (if called from `do-ticket`): `phase: blocked` with `blocked_reason: "enrichment pending user review"` while waiting; `phase: enrich` when complete.

---

## Update cycle

If invoked with `update` mode (PO added Jira comments after enrich already ran):
1. Re-run jira-to-requirements first to refresh `requirements.md`.
2. Diff new vs old `requirements.md` — surface the delta.
3. Re-enrich ONLY the changed requirements; keep unchanged ones from the prior `requirements-enriched.md`.
4. Write `requirements-enriched-v<N>-diff.md` showing what changed in the enriched spec.
5. Confirm delta with user before proceeding to analyze.

---

## Rules

- **No source code reads.** If you need code to answer something, it's a question for PO or a BA concern — escalate, don't grep.
- **Cite every edge case source.** Each EC must point to either a project_docs file or `[assumed default — PO confirm]`. Untraceable edge cases are noise.
- **Pass-through is not lazy.** If requirements are already complete, marking `PASS_THROUGH` and skipping enrichment is the correct behavior. Do not invent edge cases to look busy.
- **Open questions are expensive.** Every one costs a real PO conversation. Default to "assumed default — PO confirm" with a sensible value when domain docs support it. Only escalate when the default would be a guess. Cap PO questions at **5**, prioritised by Impact × Uncertainty (Spec Kit `clarify` discipline).
- **No un-quantified vague adjectives in ACs / Success Criteria.** "fast", "robust", "intuitive", "user-friendly", "as needed" are not testable. Replace each with a measurable target (e.g. "under 2s", "≤ 5 items", "within the same shift") or escalate it as an open question. An AC that QC cannot mark pass/fail is a defect — this is the completion-signals category of the Step 2.5 scan.
- **Carry `[NEEDS CLARIFICATION: …]` markers for blocking ambiguities.** When a Partial/Missing item has no sensible default, leave an inline `[NEEDS CLARIFICATION: <what>]` marker on the affected AC/FR (Spec Kit convention) AND list it in open questions — so it survives into the rendered `spec.md` and is visible to the whole team, not buried. These markers MUST be resolved (removed + logged in the spec's `## Clarifications`) before the spec advances past `Draft` to `Reviewed`/`Final`.
- **Output language: English** regardless of input language.
- **Do not write test cases.** That's `write-test-cases`' job. ACs are the source of truth that write-test-cases will turn into test cases.
- **Do not plan implementation.** Even if you spot an obvious technical approach, it goes in BA's analysis, not here.
- **Skip structuring, never skip grounding.** A structurally-complete requirement still gets the domain-grounding probe (incoming-OQ triage + edge cases) whenever project docs exist. Pass-through means "the author already structured it well," not "there is nothing to add."
- **Retire incoming open questions you can close.** Open questions already in the input that a project doc answers must be resolved (with citation), not re-escalated. Carry forward only the genuinely doc-unanswerable ones — PO decisions to Step 3d, code/repo questions tagged `[defer to BA / repo]`.
