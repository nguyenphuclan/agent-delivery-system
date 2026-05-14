---
name: promote-observations
description: >
  Promotes knowledge from staging sources (observations.md, ticket artifacts) to permanent long-term storage
  in the correct skill SKILL.md or public-project-docs location. Use this skill whenever the user wants to
  "promote observations", "graduate observations to long-term", "lưu observations vào skill",
  "bỏ kiến thức vào đúng chỗ", or calls /promote-observations.
  Also runs as do-ticket Phase 22.5 (promote-knowledge) when a ticket completes — see do-ticket/promote-knowledge.md.
  Never auto-triggered in manual mode; ticket-tail mode is invoked by do-ticket.
---

# promote-observations

`observations.md` is a **staging buffer** — a temporary log written during tasks. This skill
graduates mature entries to their permanent homes so the assistant doesn't load irrelevant
knowledge every session.

This skill also runs at the **tail of do-ticket** (Phase 22.5 = promote-knowledge), where its
sources expand beyond `observations.md` to include the ticket's `implement-summary.md`, `plan.md`,
`requirements-analysis.md`, and the merge commit's git diff. Same UX, broader scope.

---

## Modes

The skill operates in one of two modes:

| Mode | Trigger | Sources | Destinations |
|---|---|---|---|
| **manual** (default) | User invokes `/promote-observations` | `observations.md` only | skill SKILL.md files, `_quickref.yaml`, `knowledge_<topic>.md` |
| **ticket-tail** | do-ticket Phase 22.5 invokes via `/promote-observations --mode=ticket-tail --ticket=<ID>` | + `tickets/<ID>/{implement-summary,plan,requirements-analysis}.md`, git diff, `invariants_encoded.yaml` | + `domain/<entity>.yaml`, `concepts/<topic>.md`, `patterns/<name>.md`, `runbooks/<name>.md`, `tickets/<ID>/promoted.md` |

Step UX is identical (load → categorize → show plan → confirm → write → clean → report).
Ticket-tail mode adds detection rules in STEP 2 and audit-log output in STEP 6.

Spec for ticket-tail mode: `do-ticket/promote-knowledge.md`.

---

## STEP 1 — Load

**Manual mode:**

Read `~/.claude/skills/assistant/observations.md`. Parse every non-comment, non-empty line.
Expected format:
```
date | task type | observation | count
```

Also read `~/.claude/skills/assistant/projects.md` to get `active` project name and `output` path
(needed for public-project-docs destination).

**Ticket-tail mode (additional reads):**

Given `--ticket=<ID>`, also read:
- `{output}/tickets/<ID>/implement-summary.md` — primary detection source
- `{output}/tickets/<ID>/plan.md` — distinguishes "we already knew" from "discovered"
- `{output}/tickets/<ID>/requirements-analysis.md` — entities in scope
- `{output}/tickets/<ID>/invariants_encoded.yaml` (optional) — already-known invariants to exclude
- Git diff of the merge commit (`git show <merge-sha> --stat`) — confirms code actually changed
- `{output}/_index.yaml` + `{output}/domain/_index.yaml` + `{output}/INDEX.md` — duplicate detection
- `~/.claude/skills/assistant/observations.md` filtered to entries with
  `date >= ticket.branch_created_at` (read `ticket-context.yaml` for branch_created_at)

Reject and abort with FM-PROMOTE-NO-ENTITY if `requirements-analysis.md` lacks
`domain_entities_in_scope`. Cannot route invariants without entity context.

---

## STEP 2 — Categorize

Map each entry to a destination using the `task type` field:

| task type prefix | Destination file | Section |
|------------------|------------------|---------|
| `api-test`, `learn-crud` | `~/.claude/skills/learn-crud/SKILL.md` | `## Known Gotchas` |
| `gui-task` | `~/.claude/skills/learn-crud-gui/SKILL.md` | `## Known Gotchas` |
| `speed` | `~/.claude/skills/learn-crud-gui/SKILL.md` | `## Performance Notes` |
| `do-ticket`, `implement`, `plan` | `~/.claude/skills/do-ticket/SKILL.md` | `## Known Gotchas` |
| `first-run` | DELETE only — no destination |
| `T3 FAIL`, `T6 FAIL`, orchestration gaps | DELETE — already reflected in assistant SKILL.md rules |
| project-specific, **1-liner hot-path** (account name, enum value, selector, single API path, single rule) | `{output}/_quickref.yaml` | matching `# ─── <category> ───` section |
| project-specific, **detail/multi-line** (table, SQL block, propagation chain, dialog flow) | `{output}/knowledge_<topic>.md` | matching section (route via root `knowledge.md` INDEX) |
| project-specific, has both essence + detail | **both** — `_quickref.yaml` entry with `ref:` pointing to `knowledge_<topic>.md` section |
| cross-cutting (applies to all tasks/skills) | `~/.claude/skills/assistant/SKILL.md` | `## Shared Rules` |

**Ambiguous entries** (task type not in table, or observation could fit multiple destinations):
→ Flag them separately. Show to user and ask to confirm destination before writing.

**Tip for categorization:** read the observation text, not just the task type label.
An `api-test` entry about project-specific credentials belongs in public-project-docs, not learn-crud.
A `gui-task` entry about a general Windows shell quirk belongs in learn-crud-gui as a gotcha.
Use judgment.

### Ticket-tail mode — detection rules (additional)

In ticket-tail mode, scan the ticket artifacts for promotable findings using these signals.
Each detected finding is a candidate; STEP 3 lets the user approve / skip / reclassify.

| Signal pattern | Likely class |
|---|---|
| Sentences with "always", "never", "must", "cannot", "denies", "rejects", "precondition" | invariant |
| State-transition phrases ("when X → Y", "transitions to", "becomes <STATUS>") | invariant or concept |
| Sentence references ≥2 entities from `domain_entities_in_scope` | concept |
| "to add a new X, you need to..." / "the pattern for Y is..." | pattern |
| "if you see error X, run Y" / "to recover from..." | runbook |
| "watch out for", "surprised that", "expected X but got Y" | observation (count bump) |
| Git diff adds enum value or error code constant | invariant (entity) |
| Git diff adds NOT NULL / CHECK / UNIQUE / FK | invariant (entity) |

**Filters (drop the candidate, do not present in STEP 3):**

- Generic statements ("we wrote tests", "code compiled", "ran build")
- Already covered by `invariants_encoded.yaml` (re-encoded, not new)
- Already in target store (duplicate detection — see below)
- Pure speculation in implement-summary with no git-diff backing

**Classification routing (ticket-tail mode):**

| Class | Destination | Format |
|---|---|---|
| Single-entity invariant | `{output}/domain/<entity>.yaml` → `invariants[]` append | `{ id, statement, source_ticket, source_evidence }` |
| Cross-entity concept | `{output}/concepts/<topic>.md` (create if missing) | markdown section |
| Reusable code pattern | `{output}/patterns/<name>.md` (create if missing) | markdown with code example |
| Operational fix | `{output}/runbooks/<name>.md` (create if missing) + update `runbooks/INDEX.md` | runbook template |
| 1-liner quick fact | `{output}/_quickref.yaml` (existing manual-mode rules) | yaml entry |
| Plain observation | `~/.claude/skills/assistant/observations.md` (count bump) | one-line append |

**Topic / entity selection:**

- Entity for invariant: first entity in `requirements-analysis.md` →
  `domain_entities_in_scope` whose name appears in the finding's text.
- Topic for concept: derive from finding noun phrase. Show user the proposed
  filename in STEP 3; user can rename or merge into an existing concept.
- Pattern name: imperative phrase (e.g. `add-error-key.md`, `wire-endpoint.md`).

**Mandatory duplicate detection (before any write, ticket-tail mode):**

1. Grep `{output}/INDEX.md` for finding's keywords → list candidate files.
2. Read each candidate; semantic-match (≥70% phrase overlap = duplicate).
3. Duplicate found → propose **EDIT existing** (append `source_ticket` reference)
   instead of creating a new entry. STEP 3 row shows action `EDIT` instead of `NEW`.

If duplicate detection itself fails (grep error, file missing), abort with
FM-PROMOTE-DUP-CONFLICT — never write blindly.

**Special case — duplicate found in `domain-problem-solver/`:**

Investigation files (e.g. `domain-problem-solver/<topic>-investigation.md`) are
*de facto* concept docs in the wrong folder. When the duplicate has overlap ≥70%
in such a file, STEP 3 row offers three actions instead of two:

| Row action | When | Effect |
|---|---|---|
| `EDIT-IN-PLACE` | Investigation still active or has open questions | Append finding to investigation doc; no migration |
| `MIGRATE` (default) | Investigation closed (header `Status: resolved`/`closed`, or mtime > 30 days) | Move content → `{output}/concepts/<topic>.md`, leave one-line pointer in investigation doc, append finding to migrated file |
| `NEW-ANYWAY` | User judges topics genuinely differ | Create new file; investigation stays untouched. STEP 3 must require user override (cannot pick by default) |

Default action when investigation is closed: `MIGRATE`. STEP 3 surfaces this
prominently so the user can keep, change, or skip.

---

## STEP 3 — Show plan

Present a table to the user before writing anything.

**Manual mode:**

```
| # | Date | Task type | Observation (truncated) | Proposed destination |
|---|------|-----------|-------------------------|----------------------|
| 1 | ...  | api-test  | Portal pagination params... | learn-crud/SKILL.md → Known Gotchas |
| 2 | ...  | gui-task  | Chrome MCP not connected... | learn-crud-gui/SKILL.md → Known Gotchas |
| 3 | ...  | first-run | first-run welcome shown | DELETE |
```

**Ticket-tail mode** (extra columns: source artifact, class, action NEW/EDIT/KEEP):

```
| # | Finding (truncated)                                       | Source            | Class      | Destination                                      | Action |
|---|-----------------------------------------------------------|-------------------|------------|--------------------------------------------------|--------|
| 1 | Order rejected if a conflicting open order already exists | implement-summary | invariant  | domain/order.yaml                                | NEW    |
| 2 | Always bump shared-lib version on multi-repo commits      | observations.md   | runbook    | runbooks/shared-lib-multi-repo-commit.md         | EDIT   |
| 3 | Validator pattern for optional foreign-key field          | plan + diff       | pattern    | patterns/nullable-fk-validator.md                | NEW    |
| 4 | Build fails with MSB3027 if service still running         | observations.md   | observation| observations.md (count bump)                     | KEEP   |
```

Then ask:
> "Proceed with this plan? You can adjust any row:
>   - skip a row (`skip 3`)
>   - reclassify (`row 2 → concept/multi-repo-coordination`)
>   - merge into existing (`row 1 merge into existing order.yaml#denied-states`)
>   - **bundle related rows into one file** (`bundle 1+5+10 → concepts/order-rules.md`)
>   - rename (`row 3 rename to validator-conditional-required`)
>   - approve all (`y`)"

**Bundling rule (rule-dense tickets):** before showing the table, scan candidate
destinations. If ≥3 candidates target sibling concept files matching
`concepts/<prefix>-*.md` for the same `<prefix>` (e.g. `sla-extension-rules.md`,
`sla-stop-codes.md`, `sla-state-machine.md`), the table must surface a
`bundle suggestion` row above the candidates:

```
SUGGESTION: rows 1, 5, 10 all target concepts/sla-*.md
            → bundle into concepts/sla.md? (y/n/keep-split)
```

Without this, one rule-dense ticket can spawn 4+ adjacent concept files that
later need consolidation. User can accept, override the filename, or keep them
split.

Wait for confirmation. Do NOT write anything until the user says yes (or adjusts and confirms).
Step 3 is mandatory in **both** modes — never skip even if ticket-tail mode found 0 candidates
(in that case, STEP 6 still runs to write an empty `promoted.md` audit log).

---

## STEP 4 — Write

After confirmation, for each entry (in order):

1. Read the destination file.
2. Find the target section header (e.g., `## Known Gotchas`). If it doesn't exist, append it at
   the end of the file.
3. Append the observation under that section:
   ```
   - {observation text}  *(learned {date})*
   ```
4. Write the updated file.

If the destination file doesn't exist at all (e.g., a skill has no SKILL.md yet), create a
minimal file with just the section header before appending.

For public-project-docs `_quickref.yaml`: append a structured YAML entry, not a bullet:
1. Read `{output}/_quickref.yaml` (create with a single header comment if absent).
2. Locate the `# ─── <category> ───` section comment matching the fact (operations, accounts, DB/enums, code gotchas, task chain, status, UI). Add a new section header if none fits.
3. Before writing, scan existing entries for keyword overlap. If `>50%` overlap with an existing entry → edit that entry instead of duplicating.
4. Append:
   ```yaml
   - keywords: [<3-6 keywords incl. synonyms>]
     a: "<answer in ≤2 lines>"
     ref: knowledge_<topic>.md#<section>   # only if a leaf section also exists
   ```

For public-project-docs `knowledge_<topic>.md` (detailed entries): use the same structured-write path as `learn` Step 5.5 — read root `knowledge.md` INDEX → match topic → append to leaf section. If leaf file >= 200 lines, split first per the auto-split rule.

If the leaf file does not exist yet, create it with a single `## <section>` header, then append. Add a new INDEX row in `knowledge.md` with the new file's keyword set.

### Ticket-tail mode — additional destination writes

For `domain/<entity>.yaml` (single-entity invariant):

1. Read the entity shard. If absent, abort with FM-PROMOTE-NO-ENTITY.
2. Append to `invariants[]`:
   ```yaml
   - id: <entity>-<short-slug>
     statement: "<finding text, normalized to a single sentence>"
     source_ticket: <TICKET_ID>
     source_evidence: implement-summary | plan | git-diff
     added: <iso-date>
   ```
3. Preserve all existing entries; never reorder.

For `concepts/<topic>.md` (cross-entity concept):

1. If file missing, create with template:
   ```markdown
   # <Topic Title>

   <1-paragraph summary>

   ## Findings

   - <finding> *(<TICKET_ID>, <date>)*
   ```
2. If file exists, append the bullet under `## Findings` (or matching subsection).
3. Add INDEX row in `{output}/INDEX.md` under `## Concepts` with topic keywords.

For `patterns/<name>.md` (reusable pattern):

1. If file missing, create with template:
   ```markdown
   # <Pattern Name>

   ## When to use
   <context>

   ## Recipe
   <steps>

   ## Example
   <code excerpt or file:line reference>

   ## Source tickets
   - <TICKET_ID>
   ```
2. If exists, append a new `## Source tickets` bullet only — body assumed canonical.
3. Add INDEX row in `{output}/INDEX.md` under `## Patterns`.

For `runbooks/<name>.md` (operational fix):

1. If file missing, create with template:
   ```markdown
   # <Runbook Title>

   ## Symptom
   <when does this trigger>

   ## Steps
   1. ...
   2. ...

   ## Source
   - <TICKET_ID> (<date>)
   ```
2. If exists, append a `## Source` bullet.
3. Update `{output}/runbooks/INDEX.md` with the new entry.

After **all** ticket-tail writes succeed, refresh fingerprints in `{output}/_index.yaml`
for every artifact touched (`fingerprint-rebase` op equivalent — see `knowledge-audit/SKILL.md`).
Failure to refresh fingerprints = FM-PROMOTE-INDEX-WRITE-FAIL = hard stop.

---

## STEP 5 — Clean staging

After all writes succeed, remove promoted entries from `observations.md`.

**Keep** in `observations.md`:
- Comment lines (lines starting with `<!--`)
- Entries with `count=1` that were NOT promoted (still watching)
- The `# Observations Log` header

**Remove**: every entry that was just written to a destination (including DELETE-only entries).

Rewrite the file with only the kept lines.

---

## STEP 6 — Report

Show a concise summary:
```
Promoted: X entries → Y destinations
  - learn-crud/SKILL.md: N entries
  - learn-crud-gui/SKILL.md: N entries
  - public-project-docs/{project}/_quickref.yaml: N entries
  - public-project-docs/{project}/knowledge_<topic>.md: N entries (per file)
  - Deleted (no destination needed): N entries

Remaining in staging: Z entries (count=1, still watching)
```

### Ticket-tail mode — additional audit log

After STEP 5, write `{output}/tickets/<ID>/promoted.md`:

```markdown
# Promoted Knowledge — <TICKET_ID>

Generated: <iso>
Mode: ticket-tail

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

This log is the audit trail. `knowledge-audit` reads it to verify promotions
stuck and to catch missed promotions (implement-summary contains promotable
content but `promoted.md` is empty).

Also update `ticket-context.yaml` with:
```yaml
promote_knowledge:
  promoted_count: <K>
  new_files_created: [<paths>]
  skipped_count: <M>
```

So do-ticket telemetry can aggregate flywheel health over time.

---

## Rules

- **Manual mode never auto-runs.** Only execute when the user explicitly calls `/promote-observations`.
- **Ticket-tail mode is invoked by do-ticket Phase 22.5**, not by the user directly. Same UX gates apply.
- **Step 3 (show plan + confirm) is mandatory in both modes.** Never skip it.
- **Write before delete.** Do not remove from `observations.md` until destination write succeeds.
- **One write failure = stop and report.** Don't continue writing other entries if a write fails.
- **Respect user edits at Step 3.** If the user changes a destination or skips an entry, honor it exactly.
- **Duplicate detection in ticket-tail mode is mandatory.** Never write blindly — propose EDIT over NEW when keyword overlap ≥70%.
- **Hard stop on `_index.yaml` write failure** (ticket-tail mode) — fingerprint integrity is load-bearing for all skills.

---

## Failure modes (ticket-tail mode)

| Code | Trigger | Recovery |
|---|---|---|
| FM-PROMOTE-DUP-CONFLICT | Same finding text exists in 2+ stores | flag for `knowledge-audit`, do not auto-merge |
| FM-PROMOTE-FINGERPRINT-DRIFT | Target file mtime changed since session opened it | re-read target, re-show user the gate |
| FM-PROMOTE-INDEX-WRITE-FAIL | `_index.yaml` write rejected | hard stop; do-ticket blocks at this phase |
| FM-PROMOTE-NO-ENTITY | Invariant detected but no entity in scope matches | reclassify as concept; ask user for topic name |
| FM-PROMOTE-OVER-EAGER | >10 findings in one ticket | likely too-aggressive detection; user reviews & culls in gate |
