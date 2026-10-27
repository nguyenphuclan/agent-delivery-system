---
name: ticket-explain
description: Write a share-doc in PLAIN ENGLISH that explains ONE ticket to teammates who are NOT working on it — where it sits (module, service, screen, flow), what hurts today, what changes after, a short plan, and an honest list of what is still unclear. For a team session where each person walks through their own ticket. Output is English with simple everyday words (B1 level, short sentences); technical and domain terms stay in English and get a short plain gloss once. 5–10 minutes of talk. Use when the user says "explain my ticket to the team", "prepare a ticket share", "share this ticket with the team", "ticket walkthrough", or invokes /ticket-explain. Not a Jira dev note for the builder and not module docs.
---

## Pre-flight

**Tier: B** (reads Jira + repos, writes one file, no external side effect).

Follow `~/.claude/skills/_shared/pre-flight-protocol.md` — core subset.
- `requires_project_fields`: [active, output, repos, jira_prefix]
- Step 4 (two-store knowledge lookup) is where the plain names for things come from. Do not skip it.

---

# ticket-explain — tell one ticket to people who will not build it

## Who is listening

The listener **will not touch this ticket**. They sit in the same team and ship other
tickets. After the session they should be able to say: *"Oh, that's screen X. It breaks
because of Y. Sam fixes it in Z."* That is the whole target. Nothing more.

So the doc is judged by one question: **could a teammate repeat the point tomorrow?**

## What it is NOT

| Want | Use |
|---|---|
| Jira comment for the dev who WILL build it | a dev-note for the builder (not this skill) |
| Module/domain doc for a role (QC, BA, PM) | your team's role-based docs |
| Answering a SPIKE ticket's questions | `spike` |
| Writing / fixing the ticket description | your team's ticket-writing skill or standard |
| An implementation plan with file diffs | the plan phase of `do-ticket` |

The trap is drifting into a dev-note. That one tells a dev **how to build**. This one
tells a non-builder **what it is**. The plan section here is context, not instructions.

## Language — plain English

**Output is English, written for a reader whose first language is not English.** Translating
technical and domain words into the reader's own language makes them harder to follow, not
easier, because the team uses the English words every day. So:

- **Keep technical and domain terms in English, as they are.** `endpoint`, `payload`,
  `queue`, `migration`, `Order status`, `Work Order`, table and screen names.
  Never translate them and never swap them for a "nicer" synonym.
- **Everything around those terms uses simple words.** B1 level. Short common words.
  Sentences of 20 words or fewer. One idea per sentence. Active voice.
- **Gloss each project term once**, in brackets, in plain words: `outbound_order` (the record
  we send out to a contractor). After that, use the term freely.

The word list, the template and a worked example live in **`share-template.md`**. Read it
before writing — it is the authority on voice, not this file.

## Inputs — in this order

1. **The ticket** — description, comments, linked tickets, parent epic (`getJiraIssue`).
2. **Local artifacts for this ticket**, if they exist: `{output}/tickets/<TICKET>/` —
   `plan.md`, `requirements.md`, `implement-summary.md`, `api-test.md`, `repro/`.
   The user usually builds these tickets themselves, so the real story is often on disk.
   **Read these before the code.** They hold the dead ends, which is the best material.
3. **Naming** — `{output}/domain/_glossary.yaml`, `_quickref.yaml`. This is where a table name
   becomes a phrase a person says out loud.
4. **Placement** — `{output}/code/domain_index.yaml` (which repo / service),
   `{output}/topology/topology.yaml` (who talks to whom).
5. **The screen** — grep the frontend repo for the route or component, then name it the way a
   person names it: *"the Work Order detail screen, Contractor tab"*. Never a component path.
6. **The code itself**, last and only where needed to check a claim.

> `{output}/flows/` is a library of **developer procedures**, not business flows. Do not cite
> a `flow_*.md` as "the business flow" unless your project really keeps business flows there.
> Describe the flow from the ticket + code, and say it is your reading.

## Steps

1. Read inputs 1–4. Then ask: **can I say where this lives in one sentence, using something
   the listener has already seen?** If not, keep reading. That sentence is the doc's spine.
2. Name the screen (input 5). A ticket with no screen still has a surface: an import file, a
   queue, an export, a nightly job. Name *that*, and say who notices when it breaks.
3. Build the gloss list: every project term you will use → one short plain-English phrase.
   Cap it at 6 terms. More than 6 means the talk is too wide. Cut scope, not glosses.
4. Write "How it works today" as **one person doing one thing**. A named role, a real
   action, what the system does back. Not "the system processes…".
5. Write the problem, then the before/after table. The table is the thing people remember.
6. Write the plan: **at most 5 bullets, one sentence each.** No file paths, no class names,
   no code. If a bullet needs a path, it belongs in the optional deep section at the bottom.
7. Write "Still unclear" — see hard rule 6. Empty here is a red flag, not a clean bill.
8. Run the three gates below. Fix, then write the file.

## Hard rules

1. **Do not re-read the ticket aloud.** They can read Jira. The value of the session is what
   is *not* in the ticket: why the code is shaped this way, what you found when you opened
   it, the trap. A share-doc that only repeats the description has delivered nothing.

2. **Place first, content second.** The first line places the work somewhere the listener has
   already been — a screen they opened, a button they clicked, a file they imported. Never
   open on a class name, a table, or a service name alone.

3. **Gloss each project term exactly ONCE, on first use.** Glossing twice is noise. Glossing
   zero times loses the room at minute two. Common tech words every dev knows (`API`, `bug`,
   `deploy`) need no gloss.

4. **Tell it with a person, not with the system.** *"A planner opens the Work Order screen,
   clicks Assign, and picks a contractor. Now the system sends a record to PartnerPlan."* One
   person, one action, one result. This is the biggest difference between a talk people
   follow and one they nod through.

5. **Mark what is checked and what is a guess.** ✅ = read the code / ran it / queried it.
   ❓ = a guess, not checked. A guess said with confidence becomes the whole team's wrong
   belief, and it is costly to undo. Marking it costs two characters.

6. **Every unclear item has an owner.** Each one gets a row: *what is unclear · who to ask or
   where to look · does it block the work*. An unclear item with no owner dies on the page.
   An empty list on a real ticket usually means nobody looked hard enough. Say so instead
   of printing a clean list.

7. **A short plan is on purpose.** The listener will not build this. Detail past 5 bullets is
   noise to them. It also pushes you to defend a design nobody asked about. Deep material
   goes in the last section, unread unless someone asks.

8. **Say who is affected, by role.** *"If you are working on the Work Order detail screen,
   watch out: I change the Save payload."* This is the part teammates need most, and the part
   most often left out.

9. **5–10 minutes of talk. 1.5–2 pages.** Longer is not more useful. It just moves the cut
   from you to the listener.

## Gates

| Gate | Check | Fails when |
|---|---|---|
| **G-OPENING** | Read the first sentence alone. Does it place the work somewhere the listener has seen? | It opens on a class, table, service or ticket key. Rewrite. |
| **G-UNKNOWN-TERMS** | Count project terms used with no gloss. Count sentences a QC would stop and ask about. | Either count > 0. |
| **G-PLAIN-WORDS** | Count words from the "never use" list in `share-template.md` §1. Count sentences over 20 words. | Either count > 0. |

All three gates report their count, not a verdict. "Checked: 0 unglossed of 5 terms, 0
banned words, 0 long sentences" beats "looks fine" (`_shared/measurement-integrity-protocol.md`).

## Output

| Artifact | Path |
|---|---|
| Share-doc | `{output}/tickets/<TICKET>/share.md` |

One file. It is both the thing you read from while speaking and the thing you paste into
the team channel afterwards. The "Say it in 90 seconds" block at the top serves the first;
the rest serves the second.

**Not posted anywhere.** No Jira comment, no channel message, unless the user asks by name.
Never contact a stakeholder on your own.
