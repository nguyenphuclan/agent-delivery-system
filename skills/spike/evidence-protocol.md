---
name: spike-evidence-protocol
description: What counts as an answer in a spike. Five question kinds, the proof each one needs, five evidence grades, and the negative control that has to run before any query result is believed. Read by the spike skill's `answer` and `crosscheck` phases.
---

# Evidence protocol

A spike's output is prose. Prose reads the same whether it rests on a query someone ran or on a
confident paragraph. This file is the difference.

---

## 1. Question kinds

Classify each ledger row. The kind decides what proof the answer needs.

| Kind | The question sounds like | Proof required |
|---|---|---|
| **data-count** | "how many of X are Y?" | The exact statement, its environment, its run time, the raw output, and a passing negative control |
| **code-trace** | "is there any path that does X?" | `file:line` for every hop, plus the commit SHA the file was read at, plus the search that proves the absence when the answer is "no path exists" |
| **runtime-behaviour** | "does the customer actually get the mail?" | A real call or a real log line with its id and timestamp. Reading the sending code is a different, weaker answer |
| **external-contract** | "which event does their system fire?" | The other party's written answer, or a captured payload. Never our own expectation |
| **design-judgement** | "should we add ordering protection?" | The options, what each costs, what breaks without it. Marked as judgement, not fact |

A question can carry two kinds. Q-3 style questions — *"is it a failed reschedule or a late
contractor?"* — are usually **data-count plus design-judgement**: the data tells you the split
only after you have decided what in the data distinguishes the two. Write the discriminator
down first, then count with it. A count taken before the discriminator is named is a number
looking for a meaning.

### Absence is the hardest claim

"No code path sends a confirmation" is a claim about everything you did not find. It needs the
**searches you ran**, verbatim, and their scope — which repos, which branch, which terms. A
reader must be able to see what a fifth search would have had to cover. Absence proven by one
grep in one repo is graded `inferred`, not `proven`, no matter how sure it feels.

---

## 2. Evidence grades

Every answered row carries exactly one grade.

| Grade | Means | Can a recommendation rest on it alone? |
|---|---|---|
| `proven` | A second person can re-run it from the evidence file and get the same result | Yes |
| `observed` | Seen once, not reproducible — a transient log, a screenshot, a one-off run | Yes, if the recommendation is cheap to reverse. Say it was seen once |
| `inferred` | Reasoned from code or from another answer; nothing was run | Only with the word "inferred" in the same sentence |
| `blocked` | The source exists but is out of reach. Row names the access and who grants it | No — it is not an answer |
| `external` | Only another party can answer it. Row names them and what was asked | No — it is a dependency |

`blocked` and `external` are **successful spike output**. A spike that returns "three answered,
two blocked, here is exactly what would unblock them" has done its job. A spike that returns
five confident answers where two sources were unreachable has not.

### The substitution trap

The ticket's action list names a method. Answering by a cheaper method is a different answer:

> A-1 says *"run the triage query against production, read-only, and classify every case."*
> Reading the resolver code and reasoning about what it probably returns does not answer A-1.
> It is graded `inferred`, and the row stays `blocked` on production access.

This is the single most common way a spike looks finished and is not.

---

## 3. The negative control

**Run before any query result is believed.** A query that returns 0 rows is indistinguishable
from a query that is simply wrong, and the wrong one looks cleaner.

The control is a variant of the same query that **must** return rows. If it returns none, the
instrument is broken and the data has said nothing.

Standard controls, cheapest first:

1. **Drop the narrowest predicate.** Remove the one condition the question hinges on. Rows must
   appear. If not, the join or the base table is wrong, not the condition.
2. **Run it against a case you already know.** One id whose answer you can see by hand. The
   query must classify it the way you classify it.
3. **Run both spellings.** JSON keys, enum values and column names drift in casing between the
   live object and its audit copy. `partnerInfo.appointment.from` and `PartnerInfo.Appointment.From`
   are different paths, and a query against one returns nothing against the other — silently.
   Report both counts, even when one is zero. *That* zero is a finding.
4. **Check the total.** Every bucket count summed must equal the unbucketed count. A missing
   row means a `CASE` with no `ELSE`, or a `NULL` falling through every branch.

Record the control and its result in the evidence file. `crosscheck` check C5 fails without it.

### Timezone

A date comparison across a timezone boundary changes the answer near midnight. Write the zone
into the statement, and say which zone the business means. "Different day" for a Dutch planner
means different day in `Europe/Amsterdam`, not in UTC.

---

## 4. The evidence file

One per answered row: `{ticket_dir}/evidence/<Q-n>.md`.

```markdown
# Q-3 — <question verbatim>

Kind: data-count + design-judgement
Grade: proven
Environment: production (read-only), 2026-09-22 14:10 +07
Discriminator: <what in the data separates the two cases, decided BEFORE counting>

## Negative control
<the control statement>
<its output — must be non-empty>

## Statement
<the exact SQL / command / request, copy-pasteable>

## Raw output
<the real output, not a summary>

## What this shows
<two or three sentences — and what it does not show>
```

For `code-trace` rows, replace Statement/Output with the hop list — `repo — path:line — what it
does` — and the commit SHA every file was read at. A file path with no SHA ages into a wrong
citation within a sprint.

---

## 5. What is never evidence

- A number with no statement behind it, including one from earlier in the same conversation.
- A count from the dev or test tenant used to answer a question about production.
- "The code clearly does X" with no line cited.
- A screenshot of a page whose environment is not stated.
- Another agent's summary of a result. Read the result.
- A previous ticket's conclusion, unless re-checked — the code moved since.

## 6. When the timebox runs out

Ship. Fill every unanswered row with `blocked` or `open` and the one thing that would close it.
Then say, in the short answer, which decisions the ticket wanted that the spike cannot yet
support. A late spike is worth less than an honest short one, because the decision it feeds has
a date and the ticket it was raised against does not wait.
