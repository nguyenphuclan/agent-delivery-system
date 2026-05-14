# promote-knowledge — do-ticket tail phase

Closes the flywheel gap: knowledge discovered during a ticket (new invariants,
new patterns, new gotchas) currently dies inside `tickets/<ID>/implement-summary.md`.
This phase extracts that knowledge and graduates it to permanent stores so the
next ticket on the same area starts from a richer baseline.

Status: **spec only** — not yet implemented. Implementation = wire as Phase 22.5
in `phase-contracts.yaml` + add child skill or extend `promote-observations`.

---

## Where it sits

```
... → pr-ready (21) → pr-review (22) → [PROMOTE-KNOWLEDGE 22.5] → done (23)
```

Runs after `pr-review` resolves (or directly after `pr-ready` if no review
loop). Reason: must run after the final implement-summary is written and the
PR description is settled — those two artifacts are the highest-density
sources of promotable content.

Skipped for ticket types: `doc-only`, `spike`. (No durable code change → no
new invariants.) Other types always run promote-knowledge unless user opts out.

---

## Inputs

| Input | Required | Used for |
|---|---|---|
| `tickets/<ID>/implement-summary.md` | yes | primary detection source |
| `tickets/<ID>/plan.md` | yes | distinguishes "we already knew this" from "discovered" |
| `tickets/<ID>/requirements-analysis.md` | yes | maps findings back to entities in scope |
| `tickets/<ID>/invariants_encoded.yaml` | optional | already-known invariants — exclude from "new" set |
| Git diff of merge commit | yes | confirms what code actually changed (filters claims-only findings) |
| `~/.claude/skills/assistant/observations.md` | yes | session observations from this ticket window |
| `{project_docs}/_index.yaml` | yes | fingerprint update target |
| `{project_docs}/domain/_index.yaml` | yes | duplicate detection in domain shards |
| `{project_docs}/INDEX.md` | yes | duplicate detection across all stores |

Filter for observations: only entries with `date >= ticket.branch_created_at`
AND ticket-related task type. Avoids promoting unrelated session noise.

---

## Detection rules — what counts as promotable

Scan input sources for content matching any of these signals:

| Signal | Pattern (regex-ish) | Likely class |
|---|---|---|
| Domain rule | "always", "never", "must", "cannot", "denies", "rejects", "precondition" | invariant |
| State transition | "when X → Y", "transitions to", "becomes <STATUS>" | invariant or concept |
| Cross-entity rule | sentence references ≥2 entities from `domain_entities_in_scope` | concept |
| Code recipe | "to add a new X, you need to..." / "the pattern for Y is..." | pattern |
| Operational fix | "if you see error X, run Y" / "to recover from..." | runbook |
| Gotcha | "watch out for", "surprised that", "expected X but got Y" | observation |
| New error key / enum | git diff adds enum value or error code constant | invariant (entity) |
| New constraint | git diff adds NOT NULL / CHECK / UNIQUE / FK | invariant (entity) |

**Filter out:**
- Generic statements ("we wrote tests", "code compiled")
- Already covered by `invariants_encoded.yaml` (re-encoded, not new)
- Already in target store (duplicate detection — see Classification)
- Single-occurrence implementation detail with no reuse signal

A finding is promotable only if **(detection signal AND not duplicate AND
backed by either git diff change OR explicit user statement)**. Pure
speculation in implement-summary doesn't promote.

---

## Classification

Each detected finding routes to exactly one destination:

| Class | Destination | Format |
|---|---|---|
| Single-entity invariant | `{project_docs}/domain/<entity>.yaml` → `invariants[]` append | yaml entry: `{ id, statement, source_ticket, source_evidence }` |
| Cross-entity concept | `{project_docs}/concepts/<topic>.md` (create if missing) | markdown section |
| Reusable code pattern | `{project_docs}/patterns/<name>.md` (create if missing) | markdown with code example |
| Operational fix | `{project_docs}/runbooks/<name>.md` (create if missing) | runbook template |
| Quick fact / 1-liner | `{project_docs}/_quickref.yaml` → matching section | yaml entry per `promote-observations` STEP 4 |
| Plain observation, count=1 | `~/.claude/skills/assistant/observations.md` (stays in staging) | one-line append |

**Topic / entity selection rules:**

- Entity for invariant: take first entity in `requirements-analysis.md` →
  `domain_entities_in_scope` that the finding's text mentions.
- Topic for concept: derive from finding noun phrase. Show user the proposed
  filename; user can rename or merge into an existing concept.
- Pattern name: imperative phrase ("add-error-key.md", "wire-portal-endpoint.md").

**Duplicate detection (mandatory before any write):**

1. Grep `INDEX.md` for finding's keywords → list candidate files.
2. Read each candidate; semantic-match (≥70% phrase overlap = duplicate).
3. Duplicate found → propose **edit existing** (append source_ticket reference)
   instead of new entry.

**Special case — duplicate found in `domain-problem-solver/`:**

Investigation files (e.g. `domain-problem-solver/<topic>-investigation.md`)
are *de facto* concept docs in the wrong folder. When duplicate detection finds an
investigation file with ≥70% overlap, STEP 3 must offer three actions instead of
the default two:

| Action | When to pick | Effect |
|---|---|---|
| `edit-in-place` | Investigation is still active / has open questions | Append finding to investigation doc; no migration |
| `migrate` (recommended) | Investigation is closed and finding is durable | Move investigation content → `concepts/<topic>.md`, leave one-line pointer in investigation doc, then append finding |
| `new-anyway` | User judges the topics genuinely differ | Create new file; investigation stays untouched (rare; user must justify) |

Default offered action: `migrate`. Investigation files that have been closed
(check for `Status: resolved` / `Status: closed` header, or no edits in >30 days)
are migration candidates regardless of finding overlap — the audit log can flag
them in batches.

---

## User gate

Promote-knowledge is **never silent**. Show this table before any write:

```
| # | Finding (truncated)                                       | Class      | Destination                              | Action |
|---|-----------------------------------------------------------|------------|------------------------------------------|--------|
| 1 | Order rejected if a conflicting open order already exists | invariant  | domain/order.yaml                        | NEW    |
| 2 | Always bump shared-lib version on multi-repo commits      | runbook    | runbooks/shared-lib-multi-repo-commit.md | EDIT   |
| 3 | Validator pattern for optional foreign-key field          | pattern    | patterns/nullable-fk-validator.md        | NEW    |
| 4 | Build fails with MSB3027 if service still running         | observation| observations.md (count bump)             | KEEP   |
```

Then prompt:

> Proceed? You can:
>   - skip a row (`skip 3`)
>   - reclassify (`row 2 → concept/multi-repo-coordination`)
>   - merge into existing (`row 1 merge into existing order.yaml#denied-states`)
>   - **bundle related rows into one file** (`bundle 1+5+10 → concepts/order-rules.md`)
>   - rename (`row 3 rename to validator-conditional-required`)
>   - approve all (`y`)

**Bundling rule (rule-dense tickets):** when ≥3 candidates target adjacent
concept files (e.g. `concepts/sla-extension-rules.md`, `concepts/sla-stop-codes.md`,
`concepts/sla-state-machine.md`), the gate must surface a `bundle` suggestion
proactively — without it, one ticket can spawn 4+ new concept files that later
need consolidation. Detection: count distinct destinations matching
`concepts/<prefix>-*.md` for the same `<prefix>`; if ≥3, propose
`bundle into concepts/<prefix>.md`. User can accept, override the filename, or
keep them split.

Wait for confirmation. No writes happen until user approves explicitly. This
mirrors `promote-observations` STEP 3 — same UX, broader inputs.

---

## Outputs

### File writes (after user approval)

| Target | Write rule |
|---|---|
| `domain/<entity>.yaml` | append to `invariants[]` array; preserve existing entries |
| `concepts/<topic>.md` | create with template if missing; append section if exists |
| `patterns/<name>.md` | create with template if missing; append section if exists |
| `runbooks/<name>.md` | create or append; update `runbooks/INDEX.md` |
| `_quickref.yaml` | per existing `promote-observations` STEP 4 rules |
| `INDEX.md` | regenerate keyword → path entries for any new file |
| `_index.yaml` | bump `last_updated` + recompute fingerprint for touched artifacts |

### Ticket-folder log

Write `tickets/<ID>/promoted.md`:

```markdown
# Promoted Knowledge — <TICKET_ID>

Generated: <iso>

## Promoted (N)
| Finding | Class | Destination | Mode |
|---|---|---|---|
| ... | invariant | domain/order.yaml | NEW |
| ... | runbook   | runbooks/shared-lib-multi-repo-commit.md | EDIT |

## Skipped (M)
| Finding | Reason |
|---|---|
| ... | duplicate of order.yaml#L42 |
| ... | user skipped |
| ... | generic — no detection signal |

## Telemetry
- detection_candidates: <N>
- promoted: <K>
- skipped_duplicates: <D>
- skipped_user: <U>
- new_files_created: <F>
```

This log is the audit trail — `knowledge-audit` reads it during the next sweep
to verify promotions stuck and weren't reverted.

---

## Gating rules

**Hard stops** — phase fails, do-ticket cannot reach `done`:

| Condition | Reason |
|---|---|
| `_index.yaml` write fails | breaks fingerprint integrity for all skills |
| Duplicate-detection grep fails | unsafe to write — could create real conflicts |
| User explicitly aborts | respect intent |

**Soft stops** — phase logs and proceeds:

| Condition | Action |
|---|---|
| 0 promotable findings | write empty `promoted.md` with reason; advance to `done` |
| User skips all rows | write `promoted.md` with all skipped; advance |
| Single destination write fails | log to `promoted.md`, continue with others |

**Skip conditions** — phase doesn't run at all:

| Ticket type | Why |
|---|---|
| `doc-only` | no code change → nothing to promote |
| `spike` | exploratory — explicit follow-up ticket carries learnings |
| `hotfix` | promote on the corresponding root-cause ticket, not the patch |

---

## Failure modes

| Code | Trigger | Recovery |
|---|---|---|
| FM-PROMOTE-DUP-CONFLICT | Same finding text exists in 2+ stores | flag for `knowledge-audit`, do not auto-merge |
| FM-PROMOTE-FINGERPRINT-DRIFT | Target file mtime changed since this session opened it | re-read target, re-show user the gate |
| FM-PROMOTE-INDEX-WRITE-FAIL | `_index.yaml` write rejected | hard stop; do-ticket blocks at this phase |
| FM-PROMOTE-NO-ENTITY | Invariant detected but no entity in scope matches | reclassify as concept; ask user for topic name |
| FM-PROMOTE-OVER-EAGER | >10 findings in one ticket | likely too-aggressive detection; user reviews & culls in gate |

---

## Telemetry (run-telemetry.yaml)

Append to `phase_results[]` on completion:

```yaml
- phase: promote-knowledge
  duration_ms: <n>
  detection_candidates: <n>
  promoted: <n>
  skipped_duplicates: <n>
  skipped_user: <n>
  new_files_created:
    - concepts/state-machine.md
    - patterns/nullable-fk-validator.md
  edited_files:
    - domain/order.yaml
  failure_modes_hit: []
```

Aggregated over time, this answers: "is the flywheel actually accelerating?"
Healthy signal = `promoted/detection_candidates` ratio stable, `new_files_created`
trends down (existing files absorb most findings), per-ticket `tokens_read` in
`plan` phase trends down for tickets in already-promoted areas.

---

## Phase-contracts.yaml entry (to add)

```yaml
  promote-knowledge:                    # Phase 22.5
    skill: promote-knowledge (new) OR promote-observations (extended)
    inputs:
      required:
        - "implement-summary.md"
        - "plan.md"
        - "requirements-analysis.md"
        - "git diff of merge commit"
        - "~/.claude/skills/assistant/observations.md"
        - "{project_docs}/_index.yaml"
        - "{project_docs}/domain/_index.yaml"
        - "{project_docs}/INDEX.md"
      optional:
        - "invariants_encoded.yaml"
    outputs:
      - "promoted.md"
      - "Updates to {project_docs}/domain/, concepts/, patterns/, runbooks/, _quickref.yaml, INDEX.md"
      - "_index.yaml fingerprint refresh"
      - "ticket-context.yaml (+ promoted_count, new_files_created[])"
    state_writes:
      phase: promote-knowledge
    user_gate:
      "Show detection table → wait for approve / skip / reclassify"
    skip_when:
      - "ticket_type ∈ {doc-only, spike, hotfix}"
      - "user opted out via --no-promote flag"
    failure_modes: [FM-PROMOTE-DUP-CONFLICT, FM-PROMOTE-FINGERPRINT-DRIFT,
                    FM-PROMOTE-INDEX-WRITE-FAIL, FM-PROMOTE-NO-ENTITY]
    hard_stops_on: [FM-PROMOTE-INDEX-WRITE-FAIL]
```

---

## Relationship to existing skills

| Existing | Overlap | Resolution |
|---|---|---|
| `promote-observations` | Reads observations.md, writes to skills + `_quickref.yaml` | **Extend it** — add new sources (implement-summary, plan, git diff) and new destinations (domain/, concepts/, patterns/). Rename to `promote-knowledge` OR keep name, expand scope. Avoid two near-identical skills. |
| `invariant-check --post` (Phase 19) | Updates `_maturity.yaml` for **already-known** invariants newly enforced in code | Stays as-is. invariant-check operates on `invariants_in_scope.yaml`. promote-knowledge discovers **new** invariants not in scope at plan time. Complementary, not duplicate. |
| `learn` skill | Session retrospective on routing/skill insights | Stays as-is. learn handles meta-skill insights (which skill to invoke when). promote-knowledge handles project-domain knowledge. Different audiences. |
| `knowledge-audit` | Cross-store coherence sweep | Reads `promoted.md` as audit input. Verifies promotions stuck. Catches missed promotions if implement-summary contains promotable content but `promoted.md` is empty. |

**Decision needed** (not blocking spec): extend `promote-observations` vs.
new skill. Recommend extend — same UX, similar steps, avoids two skills doing
adjacent jobs.

---

## Implementation order (when ready)

1. Add `promote-knowledge.md` (this file). ✓
2. Decide: extend `promote-observations` or new skill. **Recommend extend.**
3. Add `concepts/`, `patterns/` folders to `public-project-docs/<project>/`
   skeleton in `scan-init`.
4. Implement detection rules in the chosen skill (regex + entity-match heuristics).
5. Wire into `phase-contracts.yaml` between `pr-review` and `done`.
6. Add `--no-promote` flag to do-ticket.
7. First trial: re-run on 2 closed tickets in dry-run mode; verify detection
   matches manual classification.
8. Enable for live tickets.

---

## Anti-patterns

- ❌ **Auto-promote without user gate.** Silent writes to domain/ corrupt the
  shared knowledge base if detection is wrong even once. Always gate.
- ❌ **Promote everything from implement-summary.md.** Most lines are routine
  ("added validator", "wrote test"). Detection signals matter — without them,
  signal-to-noise drops and user starts skipping every row.
- ❌ **Write to multiple stores for the same finding.** Pick one canonical home.
  Cross-references in `INDEX.md` are how other stores find it.
- ❌ **Skip duplicate detection to "save time".** Duplicates are the #1 way
  knowledge stores rot. The grep is cheap (1s); skipping it is expensive
  (audit cleanup later).
- ❌ **Run on every ticket without skip rules.** doc-only and spike tickets
  produce noise; promote-knowledge on them dilutes signal.
