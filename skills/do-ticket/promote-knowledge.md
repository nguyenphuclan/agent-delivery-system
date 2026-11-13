# promote-knowledge — knowledge checkpoints: catch business gaps and fix the docs at once

Owner rule: *a gap found and left for later is a gap missed. Fix the docs now; if a human is needed, say so
now. But check at chosen points, not after every action.*

## Checkpoints — when

Not after every tool call. Only where business knowledge enters the run, plus the moments context dies.

| Id | When | Why here |
|---|---|---|
| **K1** | End of Phase 6 `analyze`, before `test-cases` / `plan` | Docs and code are read; every open business question is now known. Asking here is early — nothing is built on a guess yet |
| **K2** | The turn the owner answers a **durable** business question (see Question sort) | The fact is in hand. Write it before the next step — this is the "do it now" rule. Event, not a sweep |
| **K3** | Step **16-0** of Phase 16 `commit`, before the pre-commit gate | Code reads in `implement` and live runs in `api-test` taught things the design did not know |
| **STOP** | Before any session end (S1 / S2 / S3 / SZ) and before parking a blocked run | The next session does not have this context. What is not written now is lost |
| **K4** | Phase 23 `done` | Catch-up for CI, review and QC findings after commit |

A checkpoint with nothing new since the last one prints one line and moves on. Cost is a look back, not
a re-read of the ticket.

## At each checkpoint — what

1. **Look back since the last checkpoint only:** owner answers and corrections, questions the agent asked
   or is about to ask, plan changes, failed live runs, review/QC comments.
2. **Question sort** — each question asked or pending, about the business or the system:

   | Sort | Test | Then |
   |---|---|---|
   | `gap` — missing business knowledge | The answer would still be true for the NEXT ticket in this area (how the business or a service works), and docs + code do not hold it | It is a `knowledge_miss`. Code answers it → settle, write the doc now, drop the question. Only a human knows → ask the owner **now**, then write the doc at K2 |
   | `confirm` — asking what could be found | A grep, a file read, a test run or `{project_docs}` answers it (or it is a "shall I…?" with an obvious answer) | A defect. Do not ask; settle it. If the docs had it and the run missed it → `knowledge_miss` with `docs_had_it: yes-not-found` (fix INDEX.md keywords) |
   | `decision` — the owner must choose | Intent, priority, scope or a trade-off for THIS ticket (a `Q-CHOICE`, a permission) | Normal. Ask with options. Nothing to fix in the docs |

   Tag the question in the ledger with `durable: true` for `gap`, `false` otherwise.

   **A `gap` is never `[AI-decided]`, also in AI-first.** Typical `gap`s: a unit (calendar or working days),
   a counting rule (is the start day "day 1"?), a time of day (start or end of the hours, before / after them),
   the value stored when a setting is empty. First read the project's fixed-rule docs for the area (`INDEX.md`
   keywords). They do not answer → ask the owner now (step 4), build the rest, and mark the default you build
   on `[asked owner <date>]`. "Settled by code" means the code shows how the business works today (e.g. the
   only units in an enum). An AC example, the ticket's arithmetic or one reading of the AC text does not
   settle a `gap`. (PROJ-11685: four such defaults — calendar days, a `created_at` fallback, a requested-date
   clock time, an after-hours time — were each built, tested, proved and then reversed by the owner.)
3. **Fix now.** Every new `knowledge_miss` is promoted in this checkpoint (sections below), not at the end.
4. **Human needed → tell the owner now**, in one batched message: the `gap` questions only, each with what
   docs and code were checked and a default if no answer. Do not hold them for a later gate.
5. **Record** one line in `run-telemetry.yaml.knowledge_checkpoints[]` and print it:
   ```
   [knowledge K1] misses 3 (written 2 · indexed 1) · questions 5: gap 1 · confirm 1 (defect) · decision 3 · asked owner 1
   ```
   `check_artifacts.py` needs K1 (types that run `analyze`) and K3 at pre-commit, and K4 at `done`.

## Why checkpoints, not one tail phase

The old version was Phase 22.5, after `pr-review`. It **never ran**: 0 `promoted.md` across 11 tickets with
telemetry. Three causes, each fixed below:

| Old cause | Fix |
|---|---|
| Sat after `pr-review`, which often happens days later in another session, or never in-session | Runs at K1–K4 while the facts are fresh, and before every session end. K1, K3, K4 are gated, so they run |
| Had to detect findings by regex over `implement-summary.md` — heavy and noisy | Main input is `knowledge_misses[]`: facts the run already paid for, already named |
| Waited for the owner to approve a table | AI-first: write, then list the writes in the final summary. The docs folder is under git, so every write is a diff the owner can revert |

Nothing was gated on it, so nothing made it happen. Now `check_artifacts.py` blocks commit, push and
`done` while any `knowledge_misses` entry has no `promoted` result.

## Input

`run-telemetry.yaml` → `knowledge_misses[]` (schema: `run-telemetry-schema.md`). At each checkpoint, make
the list complete for the stretch since the last one. Walk `owner_answers`, plan changes, and failed live
runs. Each one that gave a **system** fact (business rule, cross-service call, external service behaviour,
data, frontend, config) is an entry. Local machine and tool problems are not — they go to `unknown_failures`.

Optional, only if cheap: other durable facts in `implement-summary.md` (a new error code, a new
constraint, a rule the code now enforces). Log them as entries too, so the gate sees them.

## Per entry — by `docs_had_it`

| `docs_had_it` | Action | `promoted` value |
|---|---|---|
| `no` | Write the fact into its home (table below) | `written <file>` |
| `wrong` | Fix the doc at `where`. Code wins; cite the evidence | `fixed <file>` |
| `yes-not-found` | Do NOT copy the fact. Add the words you searched with to that file's line in `INDEX.md` (and a `_quickref.yaml` hint if it is a hot question), so the next grep hits | `indexed <file>` |
| any | Not worth a doc (one-off, a particular) | `skipped: <reason>` |

Then set `promoted:` on the entry in `run-telemetry.yaml`. That field is what the gate reads.

## Where a fact lives — by `area`

First grep `{project_docs}/INDEX.md` for the fact's keywords. **The file INDEX.md already points to wins.**
Use the table only when nothing matches. Default names shown; your project uses its own INDEX.md.

| `area` | Default home |
|---|---|
| `business` | `domain/<entity>.yaml` → `invariants[]` for one entity; `knowledge_<topic>.md` for a rule across entities |
| `cross-service` | `domain/_relationships.yaml` or `topology/topology.yaml` (who calls whom, who owns the data); the topic's `knowledge_*.md` if it is a flow |
| `external` | `knowledge_<partner>.md`. How OUR endpoint behaves → `api/entities/<entity>.yaml` |
| `data` | `knowledge_db.md` or `db/` |
| `frontend` | `knowledge_ui.md` |
| `config` | `knowledge_code.md`, or `runbooks/` for a multi-step fix |

A new file only when no home exists. Then add its line to `INDEX.md` in the same step.

## Rules for the write

- **Durable only.** Write the feature, the owner, the boundary. Not values, class names, line numbers or
  field lists that a grep finds in seconds — those go stale and the doc starts to lie.
- **Evidence on the line** — `(PROJ-XXXXX: owner answer 2026-11-03)` or `(code: <repo>/<area>)` or
  `(live run: test-evidence/...)`. A fact with no source is not written.
- **One home.** Grep before writing; if the fact is already there, it was `yes-not-found`, not `no`.
- **Plain English**, short lines, like the rest of the docs.
- **Never** edit `_index.yaml` fingerprints by hand; never touch prod data.

## Output

- The doc writes in `{project_docs}`.
- `promoted:` on every `knowledge_misses` entry.
- One `knowledge_checkpoints[]` line per checkpoint (schema: `run-telemetry-schema.md`).
- One block in the Phase 23 summary: `Docs updated: N written · N fixed · N indexed · N skipped`, each
  with its file. The owner reads this instead of approving a table first.

## Skip

`doc-only` only. Hotfix runs it too — hotfixes learn the most about external services and shared envs.
A spike has its own flow (`spike` skill) and its own telemetry.

## How we know it works

`run-telemetry-schema.md` §8 counts entries by `area` and `docs_had_it`. If the same area keeps showing
`no` after promotes, the writes go to the wrong home. If `yes-not-found` rises, the docs have it but the
structure hides it — that is when a structure fix (fewer entry indexes) is due.
`knowledge_checkpoints[].questions.confirm` above 0 in many tickets means the agent asks what it could
look up — a behaviour fix, not a docs fix. `gap` falling over time in one area means the docs there are
getting better.
