---
name: promote-observations
description: >
  Promotes entries from observations.md (temporary staging buffer) to permanent long-term storage
  in the correct skill SKILL.md or public-project-docs location. Use this skill whenever the user wants to
  "promote observations", "graduate observations to long-term", or calls /promote-observations.

  Never auto-triggered — only runs when explicitly requested.
---

# promote-observations

`observations.md` is a **staging buffer** — a temporary log written during tasks. This skill
graduates mature entries to their permanent homes so the assistant doesn't load irrelevant
knowledge every session.

---

## STEP 1 — Load

Read `~/.claude/skills/assistant/observations.md`.

Parse every non-comment, non-empty line. Expected format:
```
date | task type | observation | count
```

Also read `~/.claude/skills/assistant/projects.md` to get `active` project name and `output` path
(needed for public-project-docs destination).

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

---

## STEP 3 — Show plan

Present a table to the user before writing anything:

```
| # | Date | Task type | Observation (truncated) | Proposed destination |
|---|------|-----------|-------------------------|----------------------|
| 1 | ...  | api-test  | Portal pagination params... | learn-crud/SKILL.md → Known Gotchas |
| 2 | ...  | gui-task  | Chrome MCP not connected... | learn-crud-gui/SKILL.md → Known Gotchas |
| 3 | ...  | first-run | first-run welcome shown | DELETE |
...
```

Then ask:
> "Proceed with this plan? You can adjust any row — change destination, skip an entry, or
> reclassify ambiguous ones."

Wait for confirmation. Do NOT write anything until the user says yes (or adjusts and confirms).

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

---

## Rules

- **Never auto-run.** Only execute when the user explicitly calls this skill.
- **Step 3 (show plan + confirm) is mandatory.** Never skip it.
- **Write before delete.** Do not remove from `observations.md` until destination write succeeds.
- **One write failure = stop and report.** Don't continue writing other entries if a write fails.
- **Respect user edits at Step 3.** If the user changes a destination or skips an entry, honor it exactly.
