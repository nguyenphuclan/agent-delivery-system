---
name: spike
description: Run a timeboxed investigation ticket (Jira "Question" / SPIKE / POC) end to end — take the ticket's OWN numbered questions, answer each one with evidence a second person can re-run, and ship one written answer plus a ready-to-raise draft per thing worth building. Writes NO product code and creates NO tickets — the PO raises those. Use when the user says "spike PROJ-XXXXX", "run the spike", "investigate this ticket", "answer the spike", "investigate <ticket>", or invokes /spike. Distinct from domain-problem-solver (open problem, no ticket) and do-ticket (builds code).
---

## Pre-flight

**Tier: A** (multi-step, persistent state, writes to Jira at the end).

Follow `~/.claude/skills/_shared/pre-flight-protocol.md` before anything else.

Skill-specific overrides:
- `requires_project_fields`: [active, output, repos, jira_prefix]
- `risk_signals`: **g7 always** — a spike normally reads production data. See G-PROD below.
- `skip_when`: invoked as `/spike <TICKET> resume` AND `question-ledger.yaml` exists (Tier D).

---

# spike — answer the ticket's questions, with evidence

## Role

A spike ticket already contains the questions. This skill does not invent an investigation.
It **turns each written question into an answer that carries its own proof**, then stops.

Three boundaries, all hard:

| Does | Does NOT |
|---|---|
| Read code, run read-only queries, call live APIs, read logs | Write product code, open a code PR |
| Write one answer doc + one Jira comment | Change the spike ticket's scope or its linked ticket's scope |
| Draft a follow-up ticket per recommendation | Build any of them in this session |

## Why it is a separate skill

`do-ticket` builds. `domain-problem-solver` investigates an open problem with no ticket.
A spike sits between: the questions are fixed and numbered, the output is prose plus tickets,
and the deadline is a timebox rather than a green build. A `spike` ticket type inside
`do-ticket` has no build phases to run, so `do-ticket/ticket-types.md` redirects that type here.

## Companion files — these are authoritative, not this file

| File | Owns |
|---|---|
| `phase-contracts.yaml` | The phase list, per-phase inputs / outputs / gates. **The phase enumeration comes from this file.** |
| `evidence-protocol.md` | Question kinds, what proves each one, the five evidence grades, the negative control |
| `failure-modes.yaml` | SPIKE-FM-XX registry with auto-pivots |

Shared: `_shared/measurement-integrity-protocol.md` (a query that returns 0 rows is not an answer),
`_shared/pre-flight-protocol.md`, `_shared/session-handoff-protocol.md`.

## Triggers

```
/spike <TICKET>                  → full run
/spike <TICKET> resume           → continue from question-ledger.yaml
/spike <TICKET> --question=Q-3   → answer one question only
/spike <TICKET> --publish        → ledger is complete; write the doc and post
/spike <TICKET> --status         → print the ledger, answer nothing
```

## The spine

Phases live in `phase-contracts.yaml`. Short form:

```
preflight → ticket → ledger → sources → answer* → crosscheck → recommend
  → spike-doc → publish → follow-ups → done
```

`answer*` loops once per question. Everything else runs once.

## Hard rules

These are the reason the skill exists. They are not advice.

1. **Count the questions from the ticket, never from memory.** The ledger is built by reading
   the ticket's `Q-` and `A-` lines verbatim. A ticket with 5 questions and a ledger with 4 rows
   is a defect, and the `crosscheck` phase fails on it.

2. **Every answer names its evidence and its grade.** Grades are `proven` / `observed` /
   `inferred` / `blocked` / `external` (`evidence-protocol.md` §2). A recommendation that rests
   only on `inferred` must say so in the same sentence.

3. **The method the ticket asked for is part of the question.** If the action says "run this
   query against production", reading the code and reasoning it out is **not** a cheaper route
   to the same answer. It is a different, weaker answer, and it is graded `inferred`.

4. **Never pass a test-tenant number off as production.** Every count carries its environment,
   the exact query, and the time it ran. Two environments means two rows, never one.

5. **Run the negative control before trusting any query.** A query that returns 0 rows proves
   nothing until a variant you know must return rows actually does. See `evidence-protocol.md` §3.
   Casing traps, timezone traps and a wrong `WHERE` all look like clean data.

6. **You never touch production. You write the query; the user runs it.** This is permanent
   and not a permissions problem to be solved — do not ask for access, do not treat its absence
   as a blocker. The deliverable is `{ticket_dir}/prod-queries.sql`: read-only statements, in
   run order, that a person can paste and run. Then the row waits on a **result**, not on access.

   Every such file carries: discovery queries FIRST (never guess a column or a JSON key — make
   the query ask the database), a negative control per count (`evidence-protocol.md` §3), a
   totals check, and a line telling the user to send back zeros and errors too. No `UPDATE`,
   `INSERT`, `DELETE`, `CREATE`, no temp table, no `SELECT *` on a config table (they hold
   secrets). Cap any row dump, and say what the uncapped count was.

7. **Blocked is a real answer. Guessing is not.** When a source cannot be reached, the row ships
   as `blocked` with the exact access needed and who grants it. Do not substitute a nearby source.

8. **Write for the person who must DECIDE, not for a reviewer of your method.** The answer
   doc opens on the finding, then on the decisions it asks for — never on the ticket's question
   list, which puts the weakest row in the strongest position. Keep the skill's own vocabulary
   (`grade`, negative control, ledger ids) out of the body: it proves your process to an auditor
   nobody sent. Say "read it in the code" / "needs the query run" / "only the partner can answer".
   Shape lives in `phase-contracts.yaml` → `spike-doc`.

9. **When the timebox runs out, the spike ships.** Unanswered questions ship as `blocked` or
   `open` with what would close them. A spike that runs long has already failed its main job,
   which is to give a decision a date.

10. **No product code. Ever.** A fix that looks like two lines still becomes its own ticket.
   The spike's job is to make that ticket writable, not to save it.

11. **The spike recommends. The PO raises the tickets.** Write the drafts well enough that
    someone can raise them without asking a question, then stop. Deciding what enters the
    backlog is a prioritisation call, and it is not the spike's to make. Create a ticket only
    when the user names that action for a specific draft in this session. A spike ticket whose
    own action list says *"raise a ticket per item recommended"* does not change this — that
    action is satisfied by publishing the drafts where the PO can act on them.

## Gates

| Gate | When | Asks |
|---|---|---|
| **G-SCOPE** | after `ledger` | Shows the question list + the timebox. *"This is what I will answer. Missing anything?"* |
| **G-PROD** | whenever an answer needs production data | **You never read production.** Write the statements to a `.sql` file, hand it over, and wait for the output. See hard rule 6. |
| **G-PUBLISH** | before the Jira comment | Shows the full comment text. The ticket named Jira as the destination, so posting is in scope — but the user reads it first. Never `@`-mentions anyone unless the user asks. |
| **G-TICKETS** | after the drafts are written | Lists each draft with type + one-line scope, and **hands them over**. The spike does not create tickets — see hard rule 11. |

G-PUBLISH and G-TICKETS are outward-facing and cannot be auto-approved by a `--publish` flag;
the flag only means the ledger is ready.

## Handoffs

| Need | Route to |
|---|---|
| A follow-up ticket the user explicitly asked you to raise | Your team's ticket-writing skill or standard. Never on your own initiative — hard rule 11. |
| Calling a real endpoint to prove behaviour | Your live-API test skill (needs a running service + token) |
| A question that grows into an open-ended investigation | `domain-problem-solver` — plain inline form, passing the row's question and its evidence file path. There is no `--from-spike` flag; do not invent one. |
| Building anything the spike recommends | `do-ticket` — next session, never this one |

## Output

| Artifact | Path |
|---|---|
| Question ledger (state) | `{output}/tickets/<TICKET>/question-ledger.yaml` |
| Evidence per question | `{output}/tickets/<TICKET>/evidence/<Q-n>.md` |
| The written answer | `{output}/spikes/<TICKET>.md` |
| Follow-up ticket drafts (handed over, not raised) | `{output}/tickets/<TICKET>/follow-ups.md` |
| Run telemetry (for a later retrospective) | `{output}/tickets/<TICKET>/spike-telemetry.yaml` |

The Jira comment is rendered from `{output}/spikes/<TICKET>.md`. One source, two destinations.
