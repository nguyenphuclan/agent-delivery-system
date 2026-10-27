# `legacy-contract.md` — the one file a legacy change is approved on

**Reader:** a user who does not read source code. **Purpose:** they approve once, and a machine re-checks
the promise after implement. Written before code, not after.

**Core rule:** this file earns approval by being **falsifiable**, never by being well written. Every
claim carries a check that fails loudly if the claim is wrong.

---

## Where it runs in do-ticket

| Phase | Moment | What happens |
|---|---|---|
| **8.7** `blast-radius` | — | counts the surfaces, inventories extension points, **arms the gates** (`blast-radius.md`) |
| **9** `plan` | — | shape + `## Options considered` |
| **9.8** `legacy-contract` | **T0** | assemble this file · **run the frozen tests before any code change** · gate `G-T0` |
| **11** `implement` | entry gate | **blocked** while `armed_gates` non-empty and `contract_approved_at` unset |
| **12.7** `contract-recheck` | **T1** | re-run the same command against the same baseline · all green → **no second review** |

**Both 9.8 and 12.7 skip entirely when `armed_gates` is empty.** Most tickets skip.

## When it is required

Not every ticket. Gates arm from **surfaces the change touches**, counted in `blast-radius.md` before
the plan — never from a feeling about difficulty.

| Surface touched | Gates armed |
|---|---|
| nothing shared — new file, new endpoint, no existing reader | **none.** Skip this file entirely |
| a method with >1 caller | G1 · G3 |
| a shared save / write path | + G4 · G5 |
| a field with >1 reader, or an export / public contract | + G2 · G7 |
| behaviour must differ per customer / party | G4 mandatory |
| >1 viable shape for the design | + `## Options considered` in `plan.md` |

**Stop rule:** thinking budget = the number of open armed gates. **Zero open gates → stop.** Do not
keep exploring because the ticket "feels" big.

---

## The gates

| Gate | Demands | Fails when |
|---|---|---|
| **G1 Counted, not described** | every legacy surface has a number **and the exact grep that produced it** | any "several places", "a few callers", "most paths" |
| **G2 No-touch list, with a reason each** | what is deliberately NOT touched, and why that is safe. Should be **longer** than the touch list | the list is missing, or a reason is "should be fine" |
| **G3 Frozen-behaviour proof** | a named test class pinning today's behaviour, **run before the change**, with the count printed | no baseline number, or the test was written after |
| **G4 Reach-old-path test** | with the new marker / flag / column absent, execution provably takes the identical old branch | the claim exists only as prose |
| **G5 Extension point named** | the change **ADDs** a registered participant. If it **EDITs** a shared method, show the extension-point inventory and why nothing fits | "rather than adding infrastructure", with no inventory on disk |
| **G6 Agent-owned open items = 0** | anything a grep or a test can settle is unfinished work, never an open question. Only human-authority questions may stay open | any open item whose settle-method is "grep" or "run the test" |
| **G7 How I would know I broke it** | per change, the observable symptom | the word "risk" with no symptom |

`G8 (every file:line resolves)` is **parked** — it catches nothing in the escape ledger yet. Do not add
it back until an escape needs it.

**Extension-point inventory** (G5 input) — list, for the touched service: registered interceptors ·
keyed-service registrations · tracker/handler families with ≥2 siblings · MediatR notifications ·
existing base classes. `"rather than adding infrastructure"` is not a valid reason until this inventory
is on disk **and empty**. How to build it: `blast-radius.md` Step 2.

---

## Skeleton

```markdown
# Legacy contract — <TICKET>

## Self-check   (the user reads only this to decide)
armed_gates: G1 G2 G3 G4 G5 G6 G7      open_gates: 0
frozen_tests: <TestClass>   baseline: <N> passed   cmd: <one command>
reach_old_path_test: <TestName>        (or: n/a — no marker in this change)
write_sites: N (grep: <exact>)   callers: N   readers: N
extension_point: <name> — ADD
   (or: EDIT <method> because the inventory has no fit: <inventory summary>)
agent_owned_open: 0    user_owned_open: N    po_owned_open: N

## A. The picture — what exists today
One row per legacy surface. file:line · count · the grep that produced the count.

## B. Not touched, and why safe
Longer than C. One reason per row, each traceable to a code fact.

## C. Touched — one row per change
file · what changes · shape · extension point · ADD or EDIT.

## D. Proof of no regression
G3 and G4 tests by name, with the command and the printed baseline.

## E. How I would know I broke it
One observable symptom per change in C. No "risk".

## F. Decisions still open
owner (agent / user / PO) + cheapest way to settle. THE AGENT COLUMN MUST BE EMPTY.
```

---

## The two moments

- **T0 (Phase 9.8) — the user approves a predicate, not a plan.** They read the self-check block; the agent
  has already run the frozen tests. `agent_owned_open != 0` or `extension_point: EDIT` means stop and read
  properly.
- **T1 (Phase 12.7) — the same command re-runs, against the same baseline, verbatim.** Frozen pass count ≥
  baseline **and the failure set unchanged** · preconditions identical · reach-old-path green (or
  `no_marker: true` said out loud) · `blast-radius` counts re-run to the same values. Green → **no second
  review.**

**Three ways T1 lies, and the guard for each:**

| Lie | Guard |
|---|---|
| baseline re-derived after seeing the result | **verbatim only.** A threshold adjusted after the fact is not a threshold |
| a precondition changed (Docker came up, a filter changed) | a changed precondition **invalidates the comparison** — it is not a pass |
| same pass count, different failures | compare the **failure set by name**, never just the count |

A **moved count** is not a small thing: the blast radius grew after the user approved it, so the approval no
longer covers the change. Re-approve at T0.

**Honest limit:** this removes the fear of breaking legacy. It does **not** remove the design choice —
picking the shape stays the user's call, once, at T0.

---

## How this file's own gates are judged

Keep an **escape ledger**: every defect that actually got through a real ticket becomes a permanent test
case for this gate set.

- **Enough = every recorded escape is caught by some gate.** Report recall over `n`, never "complete".
- **A gate that catches nothing in the ledger is ceremony.** Park it.
- The set becomes known-incomplete the moment a new escape is not caught. That is the intended state, not
  a failure.
