---
name: blast-radius
description: Phase 8.7 — count the legacy surfaces a change will touch, inventory the extension points that already exist, and arm the gates. Counting only, no design.
---

# Phase 8.7 — `blast-radius`

Runs **after** `test-cases` (8) and **before** `plan` (9). It exists because the design kept running before
the code facts arrived: on PROJ-11332 four design shapes died one after another, each on a fact that a grep
would have produced in seconds.

## The one law

> **A count, never a claim.** No "several places", no "a few callers", no "most paths".
> A number you cannot produce is written `not-countable — <why>`, and that line is itself a finding.

**No design in this phase.** Do not pick a shape, do not name a solution, do not weigh options. This phase
produces facts; `plan` (9) uses them. Mixing the two is the defect this phase was created to stop.

## Output

`{ticket_dir}/blast-radius.md` — and `ticket-context.blast_radius.*` for the counts the later phases read.

## Step 0 — cheap surface probe, so a small ticket costs minutes

Ask only: **does this change touch anything shared?** Shared = a method with >1 caller · an existing save or
write path · a field with >1 reader · a public contract or export.

If **nothing** is shared — new file, new endpoint, no existing reader — write five lines and stop:

```markdown
# Blast radius — <TICKET>
surfaces_touched: none — new code only (<file list>)
armed_gates: none
counted: n/a
```

Then `plan` proceeds at normal depth with no gates armed. **This is the intended path for most tickets.**
Do not manufacture surfaces to look thorough.

## Step 1 — count the surfaces

One row per surface, each with **the exact command** that produced the number, so anyone can re-run it.

| What to count | Why it decides the design |
|---|---|
| **write sites** of every field / status / flag the change touches | anything opt-in gets missed. PROJ-11332: `Status` assigned in **183 places / 66 files** → an opt-in guard cannot work |
| **creation paths** of each entity touched, **and which are upserts** | PROJ-11332: `BundleOrderUpdater` is an upsert (`Id == 0` create / `Id != 0` update), so a stamp written there re-pins old rows — the exact thing one of the ACs forbade |
| **callers** of each method whose signature or behaviour moves | PROJ-11350: `ReasonHistoryWriter` had exactly **1** caller, which collapsed the claim that the partner plugin was out of scope |
| **readers** of each field whose meaning moves | PROJ-11350: dropping two entries from the history renderer's simple-field list changes rendering for **every** record category at once |
| **audit / tracker writers already on the touched save path** | PROJ-11350 escape E1: the existing `OrderUpdater.Update` already staged audit rows, so a second pass wrote duplicates |

Reference commands for a C# service (adapt the names, keep the shape):

```bash
# write sites of a field (mind the [^=] so == is excluded)
grep -rn "\.<Field>\s*=[^=]" --include="*.cs" src/<Service>/ | wc -l
grep -rln "\.<Field>\s*=[^=]" --include="*.cs" src/<Service>/ | wc -l   # file count

# creation paths + upsert detection
grep -rn "\.Add(<entity>\|new <Entity>\b" --include="*.cs" src/<Service>/
grep -rn "Id == 0\|Id != 0" --include="*.cs" <each creation path>        # upsert?

# callers of a service / method
grep -rln "I<Service>\|<service>\." --include="*.cs" src/<Service>/ | grep -v "/<Service>.cs"

# readers of a field, split from writers
grep -rn "\.<Field>" --include="*.cs" src/<Service>/ | grep -v "\.<Field>\s*=[^=]"
```

## Step 2 — extension-point inventory

**The question this answers:** can the change **ADD a registered participant**, instead of **EDITing a method
everyone else runs?** In legacy the binding constraint is not SOLID purity — it is **OCP at the boundary**.

> **Hard rule:** *"rather than adding infrastructure"* is **not a valid reason** until this inventory is on
> disk **and empty.** On PROJ-11332 that sentence chose the shape for the whole ticket, and it was factually
> wrong — four save-time interceptors were already registered in the project's DbContext setup.

Enumerate, for the touched service:

| Extension point | How to find it |
|---|---|
| registered **EF interceptors** | `grep -rln "SaveChangesInterceptor\|IInterceptor" --include="*.cs" src/` then the registration site: `grep -rn "AddInterceptors\|Interceptor>()" --include="*.cs" src/` |
| **keyed services** (`net8.0`+) | `grep -rn "AddKeyed\(Scoped\|Transient\|Singleton\)\|FromKeyedServices" --include="*.cs" src/` |
| **tracker / handler families** with ≥2 siblings | `ls <Service>/Features/*/` · `grep -rln "INotificationHandler\|IRequestHandler" --include="*.cs" src/` |
| **MediatR notifications** | `grep -rln "IMediator\|INotification\b" --include="*.cs" src/` |
| **existing base classes** to extend | `grep -rn "abstract class Base" --include="*.cs" src/` |

Write each as: **name · location · how it is registered · does it fit this change (yes / no + why)**.

An inventory row marked "no" must say **why** — that is what makes an `EDIT` decision defensible later.

## Step 3 — arm the gates

The surfaces decide which `legacy-contract.md` gates arm. **Never a feeling about difficulty.**

| Surface touched | Gates armed |
|---|---|
| nothing shared | **none** |
| a method with >1 caller | G1 · G3 |
| a shared save / write path | + G4 · G5 |
| a field with >1 reader, or an export / public contract | + G2 · G7 |
| behaviour must differ per customer / party | G4 becomes **mandatory** |
| >1 viable shape for the design | + `## Options considered` in `plan.md` |

Write `armed_gates:` into the artifact **and** `ticket-context.armed_gates[]`.

**This is the effort dial.** Thinking budget = the number of open armed gates; **zero open gates → stop.**
Do not keep exploring because the ticket feels big. Do not settle anything no armed gate requires — that is
drift.

## Step 4 — the marker question

> **Is there a marker — a flag, a column, a version — that lets an existing row keep its old behaviour?**

- **Yes** (PROJ-11332's `FlowVersion` pin) → **G4 arms**: prove that with the marker absent, execution takes
  the identical old branch.
- **No** (PROJ-11350 had no marker at all) → record `no_marker: true` **as a finding**. Every row changes on
  the same deploy, there is nothing to grandfather, and the whole proof burden moves onto G3 plus a
  per-category regression.

Nobody wrote this down on PROJ-11350, and it is the largest structural difference between the two tickets.

## Artifact shape

```markdown
# Blast radius — <TICKET>

surfaces_touched: <list>          armed_gates: G1 G2 G3 G5    no_marker: true|false

## Counts
| Surface | Number | Command |
|---|---|---|

## Creation paths
| Path | Upsert? | Evidence |
|---|---|---|

## Extension points available
| Point | Location | Registered how | Fits? Why |
|---|---|---|---|

## Not countable
| What | Why | What would make it countable |
|---|---|---|
```

## Skip / lite rules

| Ticket type | Behaviour |
|---|---|
| `doc-only`, `spike` | **skip** — no code changes |
| `hotfix` | **lite**: write sites + callers of the touched method only. No inventory. A hotfix that breaks legacy is the worst case, so the counts still run |
| `bugfix-small`, `refactor` | full, but Step 0 usually stops it at `armed_gates: none` |
| `fe-only` | full, with FE meanings: callers of a component, consumers of a service, readers of a store field |
| everything else | full |

## Gate

- `plan` (9) **may not be written** until `blast-radius.md` exists for this ticket.
- Any count stated in `plan.md` that is **not** in `blast-radius.md` is a **defect** — the plan is claiming a
  fact this phase did not produce.
- Any `EDIT` of a shared method in `plan.md` while the inventory has an unexplained "fits: yes" row is a
  **must-fix**.
- With `>20` write sites, `>1` write path, any upsert on a creation path, or a field whose meaning moves →
  Phase 9's confidence auto-proceed is **disabled**, and the options table is shown.
- A `bugfix-small` ticket where this phase arms **any** gate is promoted to `crud-feature`
  (`ticket-types.md` → Promotion rules).
