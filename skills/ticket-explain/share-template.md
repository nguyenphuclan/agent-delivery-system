# share-template.md — voice, template, and a worked example

This file decides **how to write**. `SKILL.md` decides how to work. Read this before you
start writing.

---

## 1. Voice

Write as if you stand at a screen and talk to the teammate next to you. Not document style.
The reader knows the tech, but English is their second language. Hard words cost them time.

| Write this | Not this |
|---|---|
| "The planner clicks Assign and picks a contractor." | "The user performs the contractor assignment operation." |
| "The last write wins here." | "The current mechanism employs last-write-wins semantics." |
| "Open Task detail and the field is empty." | "The interface renders a null value." |
| "I have not checked this." | (silence, then carry on as if it was checked) |

Short sentences. One idea per sentence. Max 20 words. Read it out loud — if it sounds stiff,
rewrite it.

### Simple words — always pick the short one

| Use | Not |
|---|---|
| use | leverage, utilize |
| help | facilitate |
| full, complete | comprehensive |
| solid | robust |
| reduce | mitigate |
| make sure | ensure |
| show | demonstrate, surface (verb) |
| then | subsequently |
| before | prior to |
| to | in order to |
| more | additional |
| enough | sufficient |
| try | attempt |
| many | numerous |
| start / stop | initiate, commence / terminate |
| about | approximately, regarding |
| fit | accommodate |
| merge | consolidate |
| spread | propagate |

**Never use:** nuanced, granular, delineate, holistic, paradigm, myriad, salient, ostensibly,
albeit, whilst, hence, thereby, notwithstanding, aforementioned, requisite.

Test: if a sentence needs a dictionary, rewrite it.

### Keep in English, as is

`endpoint` · `payload` · `queue` · `job` · `migration` · `index` · `deadlock` · `nullable` ·
`webhook` · `timeout` · table names · class names · field and screen names exactly as the UI
shows them.

These are the words the team already uses every day. Replacing them with a "simpler" synonym
makes the talk harder to follow, not easier.

### Gloss once, on first use

Each term **that belongs to this project** gets one short plain gloss, in brackets, the first
time it shows up:

| Term | Gloss once |
|---|---|
| `outbound_order` | (the record we send out to a contractor) |
| `inbound_order` | (a job an outside system sends in to us) |
| `plan window` | (the time slot the field crew is booked for) |
| `appointment` | (the time agreed with the customer — the customer sees this) |
| `stamp guard` | (a check on the timestamp: an older update that arrives late is dropped) |
| `partner adapter` | (the part that connects our system to a contractor's system) |

Max 6 terms per session. More than 6 means the talk covers too much. Cut scope, not glosses.

---

## 2. Template

Write every section below, in this order. If a section has nothing to say, write one line
saying why. Do not delete the heading — the reader needs to know it was considered.

```markdown
# <TICKET> — <the work in plain words, not the Jira title>

## Say it in 90 seconds
<3–4 sentences. Can be read out word for word. Someone who comes in late reads only this
block and can follow.>

## Where it lives
- **Screen:** <name as shown in the UI, plus the path: which menu → which tab>
- **Who uses it:** <a specific role>
- **Place in the system:** <service / repo, one line>
- **Talks to:** <outside systems, if any>

## How it works today
<One person, one action, what the system does back. 4–6 sentences. Mark ✅ / ❓.>

## The problem
<What is wrong or missing. Who feels it. When.>

## What changes

| | Before | After |
|---|---|---|
| <case 1> | | |
| <case 2> | | |

## The plan
<At most 5 bullets, one sentence each. No file paths, no code.>

## Still unclear

| What is unclear | Who to ask / where to look | Blocks the work? |
|---|---|---|
| | | |

## Who is affected
<Who works near this area and what they need to know. Name the role.>

## For deeper questions
<Not read out in the session. Files, endpoints, related tickets. Can be empty.>
```

### Marks

- ✅ read the code / ran it / queried it — you can say it with confidence
- ❓ a guess, not checked — **say out loud that it is a guess**

A guess said with confidence becomes the whole room's wrong belief. It is hard to undo.
Two characters are much cheaper.

---

## 3. Worked example

> An example for the voice only. The ticket, the systems and the class names are made up
> for illustration — **do not quote them as facts.**

```markdown
# PROJ-1234 — Bring the PartnerPlan appointment time back to our work order

## Say it in 90 seconds

When we hand a job to a contractor, they plan it in their own system, PartnerPlan. Their
planner agrees a time with the customer. Until now that time never came back to us. So our
work order shows no appointment. This ticket brings it back, and clears it when they cancel.

## Where it lives

- **Screen:** Work Order detail — the date and time part of the order. ✅
- **Who uses it:** planners looking at the order, and customers on the Customer Portal.
- **Place in the system:** `acme-api`, in the partner adapter (the part that connects our
  system to a contractor's system).
- **Talks to:** PartnerPlan, through `acme-connector`.

## How it works today

A planner sends an install job to the contractor. In PartnerPlan, their planner books the
crew into a `plan window` (the time slot the field crew is booked for). ✅ Then they agree an
`appointment` with the customer (the time the customer sees). These are two different things.

The two values come back to us by two different roads. The `plan window` comes back. The
`appointment` did not, before this ticket. ✅ So our work order shows the crew's slot, but
not the time the customer was promised.

There is one more gap. `plan window` uses "last write wins". `appointment` has a
`stamp guard` (an older update that arrives late is dropped). ❓ I have not checked what
trouble this difference causes.

## The problem

A customer opens the Customer Portal and sees no appointment time. But there is a real
appointment, and the crew is booked. And when PartnerPlan cancels the appointment, we never
hear about it. So the screen can keep showing a time that is no longer true.

## What changes

| | Before | After |
|---|---|---|
| PartnerPlan sets an appointment | our order is empty | our order shows the right time |
| PartnerPlan removes the appointment | we keep the old time | we clear it too |
| Two updates arrive out of order | the late one overwrites the newer one | the `stamp guard` keeps the newer one |

## The plan

- Catch one more event type from PartnerPlan in the connector.
- Read the two appointment fields, pick one, and log why.
- Write it to the order, with a `stamp guard` so a late old event cannot overwrite it.
- When the event says "removed", clear the value instead of keeping it.

## Still unclear

| What is unclear | Who to ask / where to look | Blocks the work? |
|---|---|---|
| Is the customer told when the time changes? | Out of scope here; split into its own spike | no |
| Which PartnerPlan event really means "appointment changed"? | the PartnerPlan team needs to confirm | no, but it changes how we test |
| Does `plan window` need the same order check? | look into it, or let the spike answer | no |

## Who is affected

- Customer Portal devs: the appointment field will now have data. Before, it was often empty.
- Anyone in the PartnerPlan adapter: there is one more event branch. Read it before adding another.
- QC: when testing, keep `plan window` and `appointment` apart. They are different things.

## For deeper questions

- `AppointmentPicker` — where we choose between the two appointment fields.
- `PlanWindowWriter` — where `plan window` is written.
- Spike PROJ-1240 covers what the customer sees.
```

---

## 4. Check before you hand it over

Three gates. All of them are **counts**. Do not eyeball.

**G-OPENING** — cover the whole doc and read only the first sentence. Does it put the
listener somewhere they have been? Opens on a class, table, service or ticket key → rewrite.

**G-UNKNOWN-TERMS** — count two numbers:
1. project terms used with no gloss
2. sentences a QC would stop and ask about

Both must be 0.

**G-PLAIN-WORDS** — count two numbers:
1. words from the "never use" list or the left side of "Not" in §1
2. sentences over 20 words

Both must be 0. Report the numbers, not "looks fine".

**Read it out loud.** If you run out of breath in a sentence, it is too long. Cut it.

---

## 5. Common failures

| Failure | Fix |
|---|---|
| Repeats the ticket description in other words | Drop it. Tell what the ticket does **not** say: what you saw in the code, why it is shaped this way |
| A 12-bullet plan | Cut to 5. The rest goes to "For deeper questions" |
| "Still unclear" left empty to look clean | Real tickets always have unclear parts. Empty = not looked at hard enough. Say so |
| "The system will handle it" | Who clicks? Where? What do they see after? |
| A guess said as fact | Add ❓, and say out loud it is a guess |
| No "who is affected" | This is what teammates need most. Do not skip it |
| Fancy English words | Use the short word from §1. The reader's English is a second language |
| Translating tech terms into plain words | Keep `endpoint`, `payload`, field names in English. Gloss once instead |
