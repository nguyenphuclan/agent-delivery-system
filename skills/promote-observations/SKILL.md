---
name: promote-observations
description: >
  Promotes entries from observations.md (temporary staging buffer) to permanent long-term storage
  in the correct skill SKILL.md or public-project-docs location. Use this skill whenever the user wants to
  "promote observations", "graduate observations to long-term", or calls /promote-observations.
  Also runs as do-ticket Phase 22.5 (promote-knowledge) when a ticket completes — see do-ticket/promote-knowledge.md.
  Never auto-triggered in manual mode; ticket-tail mode is invoked by do-ticket.
---

# promote-observations

`observations.md` is a **staging buffer** — a temporary log written during tasks. This skill
graduates mature entries to their permanent homes so the assistant doesn't load irrelevant
knowledge every session.

This skill also runs at the **tail of do-ticket** (Phase 22.5 = promote-knowledge). There its
sources grow beyond `observations.md` to the ticket's `implement-summary.md`, `plan.md`,
`requirements-analysis.md`, and the merge commit's git diff. Same UX, broader scope.

---

## Modes

| Mode | Trigger | Sources | Destinations |
|---|---|---|---|
| **manual** (default) | User invokes `/promote-observations` | `observations.md` only | skill SKILL.md files, `_quickref.yaml`, `knowledge_<topic>.md` |
| **ticket-tail** | do-ticket Phase 22.5 invokes `/promote-observations --mode=ticket-tail --ticket=<ID>` | + `tickets/<ID>/{implement-summary,plan,requirements-analysis}.md`, git diff, `invariants_encoded.yaml` | + `domain/<entity>.yaml`, `concepts/<topic>.md`, `patterns/<name>.md`, `runbooks/<name>.md`, `tickets/<ID>/promoted.md` |

Step UX is the same in both modes: load → categorize → show plan → confirm → write → clean → report.
Ticket-tail mode adds detection in STEP 2, more destinations in STEP 4, and an audit log in STEP 6.

**Spec for ticket-tail mode:** `do-ticket/promote-knowledge.md`. It owns the detection signals,
filters, classification table, topic/entity selection, bundling rule, `promoted.md` format, gating
rules and failure-mode codes. This file says how to *run* them; it does not repeat them.

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

**Ticket-tail mode:** load everything above, plus the inputs listed in
`do-ticket/promote-knowledge.md` → Inputs. Keep only observations dated on or after the ticket
branch was created and tied to this ticket — older lines are other work.

---

## STEP 2 — Categorize

Map each entry to a destination using the `task type` field:

| task type prefix | Destination file | Section |
|------------------|------------------|---------|
| `api-test` | your API-test skill's `SKILL.md` | `## Known Gotchas` |
| `gui-task` | your GUI-test skill's `SKILL.md` | `## Known Gotchas` |
| `speed` | your GUI-test skill's `SKILL.md` | `## Performance Notes` |
| `do-ticket`, `implement`, `plan` | `~/.claude/skills/do-ticket/SKILL.md` | `## Known Gotchas` |
| `first-run` | DELETE only — no destination |
| `T3 FAIL`, `T6 FAIL`, orchestration gaps | DELETE — already reflected in the router skill's rules |
| project-specific, **1-liner hot-path** (account name, enum value, selector, single API path, single rule) | `{output}/_quickref.yaml` | matching `# ─── <category> ───` section |
| project-specific, **detail/multi-line** (table, SQL block, propagation chain, dialog flow) | `{output}/knowledge_<topic>.md` | matching section (route via root `knowledge.md` INDEX) |
| project-specific, has both essence + detail | **both** — `_quickref.yaml` entry with `ref:` pointing to `knowledge_<topic>.md` section |
| cross-cutting (applies to all tasks/skills) | your always-loaded router skill (e.g. `~/.claude/skills/assistant/SKILL.md`) | `## Shared Rules` |

**Ambiguous entries** (task type not in table, or observation could fit multiple destinations):
→ Flag them separately. Show to user and ask to confirm destination before writing.

**Tip for categorization:** read the observation text, not just the task type label.
An `api-test` entry about project-specific credentials belongs in public-project-docs, not the
API-test skill. A `gui-task` entry about a general Windows shell quirk belongs in the GUI-test
skill as a gotcha. Use judgment.

### Ticket-tail mode — detection, routing, dedupe

1. **Detect.** Scan the ticket artifacts with the signal table in
   `do-ticket/promote-knowledge.md` → Detection rules. Each hit is a candidate; STEP 3 lets the user
   approve, skip or reclassify it.
2. **Filter.** Drop generic lines, findings already in `invariants_encoded.yaml`, and claims in
   `implement-summary.md` that no git-diff change backs up. A dropped candidate never reaches STEP 3.
3. **Route.** One destination per finding, per the spec's Classification table
   (invariant → `domain/<entity>.yaml`, concept → `concepts/<topic>.md`, pattern → `patterns/<name>.md`,
   operational fix → `runbooks/<name>.md`, 1-liner → `_quickref.yaml`, plain observation → count bump
   in `observations.md`).
4. **Dedupe (mandatory, before any write).**
   - Grep `{output}/INDEX.md` for the finding's keywords → list candidate files.
   - Read each candidate. ≥70% phrase overlap = duplicate.
   - Duplicate found → the STEP 3 row's action becomes `EDIT` (append a `source_ticket` reference)
     instead of `NEW`.
   - If the dedupe step itself fails (grep error, missing file), stop with
     FM-PROMOTE-DUP-CONFLICT. Never write blind.

**Duplicate found in `domain-problem-solver/`.** Investigation files there
(`domain-problem-solver/<topic>-investigation.md`) are concept docs in the wrong folder. When the
duplicate sits in one, the STEP 3 row offers three actions:

| Row action | When | Effect |
|---|---|---|
| `EDIT-IN-PLACE` | Investigation still active or has open questions | Append the finding to the investigation doc; no move |
| `MIGRATE` (default) | Investigation closed: header `Status: resolved` / `closed`, or no edit for > 30 days | Move the content → `{output}/concepts/<topic>.md`, leave a one-line pointer in the investigation doc, then append the finding to the moved file |
| `NEW-ANYWAY` | User judges the topics really differ | Create a new file; investigation stays untouched. Never the default — the user must pick it |

Show `MIGRATE` clearly in STEP 3 so the user can keep, change, or skip it.

---

## STEP 3 — Show plan

Present a table to the user before writing anything.

**Manual mode:**

```
| # | Date | Task type | Observation (truncated)        | Proposed destination                      |
|---|------|-----------|--------------------------------|-------------------------------------------|
| 1 | ...  | api-test  | Portal pagination params...    | <api-test skill>/SKILL.md → Known Gotchas |
| 2 | ...  | gui-task  | Browser extension not connected... | <gui-test skill>/SKILL.md → Known Gotchas |
| 3 | ...  | first-run | first-run welcome shown        | DELETE                                    |
```

**Ticket-tail mode** (extra columns: source artifact, class, action NEW / EDIT / KEEP / MIGRATE):

```
| # | Finding (truncated)                                  | Source            | Class       | Destination                              | Action |
|---|------------------------------------------------------|-------------------|-------------|------------------------------------------|--------|
| 1 | Order rejected if a conflicting open order exists    | implement-summary | invariant   | domain/order.yaml                        | NEW    |
| 2 | Always bump shared-lib version on multi-repo commits | observations.md   | runbook     | runbooks/shared-lib-multi-repo-commit.md | EDIT   |
| 3 | Validator pattern for optional foreign-key field     | plan + diff       | pattern     | patterns/nullable-fk-validator.md        | NEW    |
| 4 | Build fails with MSB3027 if service still running    | observations.md   | observation | observations.md (count bump)             | KEEP   |
```

Then ask:
> "Proceed with this plan? You can adjust any row:
>   - skip a row (`skip 3`)
>   - reclassify (`row 2 → concept/multi-repo-coordination`)
>   - merge into existing (`row 1 merge into existing order.yaml#denied-states`)
>   - bundle related rows into one file (`bundle 1+5+10 → concepts/order-rules.md`)
>   - rename (`row 3 rename to validator-conditional-required`)
>   - approve all (`y`)"

**Bundling (ticket-tail):** before showing the table, apply the bundling rule in
`do-ticket/promote-knowledge.md` → User gate. When ≥3 rows target `concepts/<prefix>-*.md` for the
same prefix, put a `SUGGESTION: bundle into concepts/<prefix>.md? (y/n/keep-split)` line above the
table.

Wait for confirmation. Do NOT write anything until the user says yes (or adjusts and confirms).
STEP 3 is mandatory in **both** modes. Never skip it, even when ticket-tail mode found 0
candidates — STEP 6 still writes an empty `promoted.md`.

---

## STEP 4 — Write

**`observations.md` is a shared file.** Several sessions may append to it while this one runs.
A read-modify-write from the copy you read at STEP 1 silently deletes whatever landed in between,
and the report then shows a smaller number as if it were true. So every write goes through the lock in
`_shared/tools/shared_store.py`:

```python
import sys
sys.path.insert(0, "_shared/tools")   # this repo's _shared/tools folder
from shared_store import append_lines, rewrite

append_lines(DEST, [line, ...], label="promote-observations")   # add
rewrite(OBS, drain_fn, label="promote-observations")             # drain (STEP 5)
```

`rewrite` hands `drain_fn` the file as it is **inside** the lock (the CURRENT text), never the copy you
read at STEP 1. Re-derive which lines to drop from that text — do not carry a line list across the lock
boundary. `append_lines` skips a line already present, so a retry cannot double-write. If the module cannot
be imported, follow the same rules by hand:

- To **add**, append. Never rewrite the whole file to add a line.
- To **rewrite** (STEP 5 drain), re-read the file at the moment of writing and decide which lines to
  drop from *that* text. Never carry a line list or line numbers over from an earlier read.
- Never use positional ids (`#3`, line numbers) to match an entry across reads. Match by content.

The same holds for any other file that more than one session writes (`_quickref.yaml`, `INDEX.md`).

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

For public-project-docs `knowledge_<topic>.md` (detailed entries): read root `knowledge.md` INDEX → match topic → append to the leaf section. If the leaf file is already ≥ 200 lines, split it by section first, then append.

If the leaf file does not exist yet, create it with a single `## <section>` header, then append. Add a new INDEX row in `knowledge.md` with the new file's keyword set.

### Ticket-tail mode — extra destination writes

**`domain/<entity>.yaml`** (single-entity invariant):

1. Read the entity shard. If absent, stop with FM-PROMOTE-NO-ENTITY (reclassify as concept, ask
   the user for a topic name).
2. Append to `invariants[]`:
   ```yaml
   - id: <entity>-<short-slug>
     statement: "<finding text, normalized to a single sentence>"
     source_ticket: <TICKET_ID>
     source_evidence: implement-summary | plan | git-diff
     added: <iso-date>
   ```
3. Keep all existing entries; never reorder.

**`concepts/<topic>.md`** (cross-entity concept):

1. If missing, create:
   ```markdown
   # <Topic Title>

   <1-paragraph summary>

   ## Findings

   - <finding> *(<TICKET_ID>, <date>)*
   ```
2. If present, append the bullet under `## Findings` (or the matching subsection).
3. Add an INDEX row in `{output}/INDEX.md` under `## Concepts` with the topic keywords.

**`patterns/<name>.md`** (reusable pattern):

1. If missing, create:
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
2. If present, append a `## Source tickets` bullet only — the body is treated as canonical.
3. Add an INDEX row in `{output}/INDEX.md` under `## Patterns`.

**`runbooks/<name>.md`** (operational fix):

1. If missing, create:
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
2. If present, append a `## Source` bullet.
3. Update `{output}/runbooks/INDEX.md` with the new entry.

**Fingerprint refresh.** After **all** ticket-tail writes succeed, update `{output}/_index.yaml` for
every artifact you touched: set `last_updated` to now and recompute its `fingerprint` the same way
scan-init computes it for that artifact (scan-init → the artifact's Fingerprint section). A stale
fingerprint makes every later skill trust or distrust the wrong file. If this write fails, stop
with FM-PROMOTE-INDEX-WRITE-FAIL — a hard stop.

---

## STEP 5 — Clean staging

After all writes succeed, remove promoted entries from `observations.md`.

**Keep** in `observations.md`:
- Comment lines (lines starting with `<!--`)
- Entries with `count=1` that were NOT promoted (still watching)
- The `# Observations Log` header

**Remove**: every entry that was just written to a destination (including DELETE-only entries).

Do it with `rewrite(OBS, drain_fn, label="promote-observations")` (STEP 4): `drain_fn` receives the
current file text and returns it minus the promoted entries, matched by content. By hand: re-read the file
now, drop the promoted entries from that fresh text by matching their content, and write the result. Lines
that other sessions added since STEP 1 must survive.

---

## STEP 6 — Report

Show a concise summary:
```
Promoted: X entries → Y destinations
  - <skill>/SKILL.md: N entries (per skill)
  - public-project-docs/{project}/_quickref.yaml: N entries
  - public-project-docs/{project}/knowledge_<topic>.md: N entries (per file)
  - Deleted (no destination needed): N entries

Remaining in staging: Z entries (count=1, still watching)
```

### Ticket-tail mode — audit log

After STEP 5, write `{output}/tickets/<ID>/promoted.md` in the format given in
`do-ticket/promote-knowledge.md` → Ticket-folder log (Promoted / Skipped / Telemetry), with one
extra header line `Mode: ticket-tail`. Write it even when nothing was promoted, with the reason.

Then update `ticket-context.yaml`, so do-ticket telemetry can track the flywheel over time:
```yaml
promote_knowledge:
  promoted_count: <K>
  new_files_created: [<paths>]
  skipped_count: <M>
```

---

## Rules

- **Manual mode never auto-runs.** Only execute when the user explicitly calls `/promote-observations`.
- **Ticket-tail mode is invoked by do-ticket Phase 22.5**, not by the user directly. The same UX gates apply.
- **STEP 3 (show plan + confirm) is mandatory in both modes.** Never skip it.
- **Write before delete.** Do not remove from `observations.md` until the destination write succeeds.
- **One write failure = stop and report.** Don't continue writing other entries if a write fails.
- **Respect user edits at STEP 3.** If the user changes a destination or skips an entry, honor it exactly.
- **Never rewrite a shared file from an old snapshot.** Re-read inside the write; match entries by content.
- **Dedupe is mandatory in ticket-tail mode.** Never write blind — propose `EDIT` over `NEW` when overlap is ≥70%.
- **Hard stop on `_index.yaml` write failure** (ticket-tail mode) — every skill relies on fingerprint integrity.

Failure-mode codes (FM-PROMOTE-DUP-CONFLICT, -FINGERPRINT-DRIFT, -INDEX-WRITE-FAIL, -NO-ENTITY,
-OVER-EAGER) and their recovery are defined in `do-ticket/promote-knowledge.md` → Failure modes.
