---
name: code-quality-review
description: Code-quality discipline for do-ticket. Two checkpoints — a thin structural-quality gate injected into Phase 9 (plan), and a full diff-scoped review at Phase 13.5 (post-implement, pre-commit). Modeled on a strict-reviewer QUALITY mandate, adapted for brownfield .NET. Catches what completeness-audit (Phase 13) and invariant-check (Phase 7/19) cannot: is the produced code well-structured, thin, non-duplicative, and clean?
---

# do-ticket — Code-Quality Review

**Created:** 2026-06-01

## Why this exists

do-ticket already proves a change is **domain-correct** (Phase 6/7/19 + flow-gate) and **complete** (Phase 13 completeness-audit). Nothing proved it was **well-built**. That gap is why tickets ship domain-correct code with fat handlers, duplicated logic, leaked layers, and rubber-stamp tests.

This file adds the missing layer — a QUALITY pass with a strict reviewer mandate: **push back with actionable bullets; rubber-stamping is forbidden.** It is the brownfield-appropriate analogue of fail-red architecture tests + a reviewer (a brownfield codebase cannot retrofit fail-red arch tests cheaply, so the lever is a judgment pass, not a mechanical gate).

## Two checkpoints, different scope

The dividing principle: **push a check to plan-time iff it is knowable from the plan; everything that lives at the line-of-code level must wait until the code exists.**

| Checkpoint | When | Catches | Cost to fix |
|---|---|---|---|
| **Structural gate** (this file §A) | Phase 9 `plan`, folded into the existing confidence-gated review | Wrong layer · new-handler-vs-extend-fat-one · improve-vs-mirror decision · duplication of *existing* logic | Cheap — edit words |
| **Full review** (this file §B) | **Phase 13.5 `code-quality-review`**, after implement+regression+completeness-audit, before env-gate | Handler thinness · naming vs glossary · introduced duplication · dead weight · data-access waste · error handling · test meaningfulness · conventions conformance · base-value supersession | Expensive — rewrite + re-test |

The post-code review is the **primary** one — the user's complaint ("domain correct, code structure weak") is about properties of written code, invisible in a plan.

---

## §A — Structural gate (Phase 9, plan-time)

do-ticket injects a `structural_quality` decision group into the Phase 9 confidence-gated review (alongside the existing decision cards). It is **not** a separate user prompt unless something fails — it rides the existing plan review gate.

For the proposed change in `plan.md`, the planner answers five questions and records each as a decision card with confidence:

1. **Layer placement** — does each proposed edit sit in the right layer? (business logic → domain/application, not controller; no infra type referenced from domain.) Flag any misplacement as a `low`-confidence card → forces it into the plan review surface.
2. **New vs extend** — for each method/class being grown: is it already carrying ≥3 responsibilities? If extending it adds a 4th, propose a new handler/service instead and note why.
3. **Improve-vs-mirror** (prefer improving over mirroring a weak pattern) — for every "follow existing pattern X" decision: state explicitly *"pattern X does A; new code uses B for the same behavior because B is cleaner"* OR *"mirroring X verbatim — its quirk is load-bearing because <reason>"*. A silent "copy pattern X" with no improve/mirror verdict is itself a finding.
4. **Duplication of existing logic** — does the proposed logic re-implement something that already exists and should be called instead? (One targeted grep of the touched area is enough — this is a plan-time smell check, not an exhaustive search.)
5. **Base-value impact** (proactive half of §B dimension 11) — does any field this plan touches appear in `{project_docs}/domain/_field_impact.yaml`? If yes, surface its `consumers` + `supersede_note` as a decision card, marked `low`-confidence when the plan would overwrite the base or add a superseding field (so it enters the review surface). Registry absent or no touched field matches → clean, no card. Read-only lookup — the *warn-before-coding* half; the *reactive catch* runs post-code in §B.

**Gate behavior:** these five feed the existing Phase 9 decision tree. If any is `low`-confidence or flags a problem → it appears in the ≤5 CRITICAL items the user reviews. If all clean → auto-proceed (no extra interruption). Record the five verdicts in `plan.md` under a `## Structural quality` heading and in `ticket-context.structural_quality_decisions[]`.

**Skip when:** `ticket_type ∈ {doc-only, spike, hotfix}` (hotfix = surgical-patch, no drive-by improvement by rule). `migration-only` runs questions 1 and 5 — layer placement + base-value impact, because a migration that renames or supersedes a column is prime supersession territory.

---

## §B — Full review (Phase 13.5, post-code)

### Scope discipline (read first — non-negotiable)

**Review the DIFF, not the repo.** The unit of review is `git diff <base>...HEAD` — new and changed lines plus their immediate enclosing method/class. Pre-existing debt in untouched code is **out-of-scope by default**: a brownfield codebase has unbounded debt and reviewing it all is scope creep. When pre-existing debt is *adjacent and relevant*, record it as an `out-of-scope` finding (→ optionally a `spawn_task` follow-up) but **do not fix it in this ticket.** This is the discipline that lets the gate have teeth without exploding scope.

### Who reviews — independence is the whole mechanism

**Run §B in a COLD SUBAGENT, not in the implementer's own context.**

Spawn it with the `Agent` tool and hand it exactly three things: the rubric below, the
absolute paths to the artifacts under review, and the required output shape. Tell it nothing
about the implementer's reasoning, the strategies that were tried and dropped, the open user
decisions, or the conversation. Only what is on disk.

Why this is not ceremony: a reviewer that has read the implementer's own account of the change
is no longer checking the change — it is checking a summary of the change, written by the party
with the strongest reason for it to look finished. The authority of this gate comes from
independence, and reading implementer-side notes spends that authority for nothing.

Hard rules for the reviewer subagent:

- Read ONLY the named artifacts plus the diff. Do not go looking for the implementer's notes.
- Every `must-fix` MUST cite `file:line`. A finding with no citation is downgraded to
  `question` before the report is written — no exceptions, including when it feels obvious.
- Do NOT propose new scope. If the requirements do not ask for something, its absence is at
  most a `question`, never a `must-fix`.
- Do NOT speculate about what code "probably" does. Unverifiable against the artifacts shown →
  downgrade to `question`.
- Max 2 review iterations per checkpoint. A third is a contract violation, not a longer
  conversation — see FM-REVIEW-LOOP-EXHAUSTED.

*Provenance: an earlier review-gate design (2026-05-14) had this isolation rule. When this file
replaced it on 2026-06-01, the review CONTENT was kept and the isolation rule was dropped; this
section puts it back.*

**Open question, deliberately not answered here:** that earlier design also declared a `post-analyze`
checkpoint — reviewing `requirements-analysis.md` before any plan exists. It was never built, so
there is nothing to port, only the idea. Worth deciding on merit: is a cold read of the analysis
worth a third gate, or does Phase 7 invariant-check already cover it?

### Methodology

1. Get the diff: `git diff` of staged+unstaged changes for this ticket (or `git diff <base_branch>...HEAD` if already committed in an update cycle).
2. **Compute the activation set** (next section) from what the diff *contains*, not from what the ticket is about.
3. For each changed hunk, walk every dimension in the activated groups. Cite `file:line`.
4. Assign every finding a **severity** and **disposition** (table after the dimensions).
5. Write `code-quality-review.md` to the ticket folder. **Name the groups you ran and the groups you skipped, with the reason** — a review that does not say what it did not look at reads as complete when it was partial.
6. Apply the gate: any `must-fix` open → block, loop to implement. Otherwise surface `nice-to-have` for a fix-now/defer decision and proceed.

---

### Groups, and which ones fire

This review judges **codebase health**, never business correctness — whether the code does what the
ticket asked is `completeness-audit`'s job, and whether it is domain-correct is `invariant-check`'s.
Everything here would still be a finding if the feature were something else entirely.

The dimension list is long on purpose: "good code" is not one axis. Running all of it on every diff
would be unaffordable and would train you to skim, so groups **activate off the diff's own content**.
Dimension IDs are stable — the groups are a view over them, not a renumbering.

| Group | Fires when the diff… | Dimensions |
|---|---|---|
| **G1 — Shape & placement** | always | D1, D2, **D14** |
| **G2 — Reuse & waste** | always | D4, D5 |
| **G3 — Language-level hazards** | always | D7, **D15**, **D16**, **D17** |
| **G4 — .NET runtime** | contains `async`/`Task`, a `using`/`IDisposable`, `HttpClient`, or a loop over a collection | **D18**, **D19**, **D20**, **D21** |
| **G5 — Data & persistence** | touches a `DbContext`, repository, raw SQL, or a migration | D6, **D22**, **D23** |
| **G6 — Concurrency & shared state** | adds/changes a `static`, a singleton, a cache, or a queue consumer | **D24**, **D25** |
| **G7 — Operability** | adds a log line, a config value, a literal constant, or an error message | **D26**, **D27** |
| **G8 — Security surface** | touches a controller, an endpoint, auth, or handles caller-supplied input | **D28** |
| **G9 — Tests** | adds or changes any test | D8, **D29** |
| **G10 — Convention & language** | always | D3, D9, D5 (comments) |
| **G11 — Design judgement** | always | D10, D11, D12, D13 |

**Five groups are always on** (G1, G2, G3, G10, G11) — they need no trigger because every diff has
shape, waste, hazards, naming and a design choice. The other six are content-gated.

**Gating is on content, not intent.** "This ticket is not about performance" is not a reason to skip
G4; the trigger is whether the diff contains `async`, not whether the ticket mentions speed. A rule
you can talk your way out of is not a rule.

**When a group is skipped, say so in the output** with its trigger: *"G5 not run — the diff touches
no DbContext, repository, raw SQL or migration."* A skipped group is a fact about the diff. A group
silently absent is indistinguishable from a group that found nothing.

### Two passes, because the dimensions need different zoom

Reviewing every dimension line by line drowns you in noise and still misses design. Reviewing
everything block by block catches design and walks straight past a single-line hazard. So the diff is
walked **twice**, and each dimension is tagged with the zoom it actually needs.

| Pass | Unit | What it can see | Dimensions |
|---|---|---|---|
| **1 — line** | each changed line, plus a line either side | hazards that live in one expression: a blocking call, a wrong clock, a culture-sensitive compare, a leftover, a bad name, a missing token in a signature | D3, D5, D15, D16, D17, D18, D19, D20, D26, D27 |
| **2 — block** | each changed method/class as a whole | anything you can only see with the surrounding code: responsibility, duplication, query shape, ownership, the design question | D1, D2, D4, D6, D7, D8, D9, D10, D11, D12, D13, D14, D21, D22, D23, D24, D25, D28, D29 |

Pass 1 is fast and mechanical — most of it is a scan. Pass 2 is where the thinking goes. Doing pass 2
first is the common failure: you form a view of the design and stop seeing the `.Result` on line 4.

**Every finding must state the failure it prevents, not the rule it breaks.** *"D18: no `.Result`"* is
a rule and it invites arguing. *"this blocks a request thread; under load the pool starves and
unrelated endpoints time out"* is a failure, and it settles the argument by itself. A finding you
cannot phrase as a failure is a preference — drop it.

### Can the standard actually be reached here? — the `constrained` disposition

A brownfield codebase will sometimes make the right shape unreachable: an interface you do not own, a
base class every sibling uses, a framework limit, an upstream contract, a performance trade that goes
the other way. Silently lowering the bar is the wrong answer, and so is raising a `must-fix` that
cannot be fixed.

So every finding runs this chain, in order:

1. **Does the standard apply here at all?** If the dimension does not fit this code, say so and stop —
   an N/A with a reason is a real answer.
2. **Can it be reached in this ticket?** Yes → `must-fix` or `nice-to-have` as usual.
3. **If not, why not?** Name the blocker concretely. *"It would be nicer"* is not a blocker; *"the
   base class is the one every sibling uses and changing it is a repo-wide migration"* is.
4. **Is that reason sound?** If it is only "we are in a hurry", it is not — that is `nice-to-have
   deferred`, and it goes in the follow-up list, not in the code.
5. **If the reason is sound → `constrained`, and leave a comment at the spot.**

**`constrained` is the only disposition that REQUIRES a code comment.** Without it, a deliberate
compromise and an accident look identical six months later, and the next person either "fixes" the
compromise and breaks something, or copies it thinking it is the house style. The comment is the
whole point of the disposition; a `constrained` finding with no comment is not resolved.

The comment says three things and stays short — two lines, prose, no ticket ids (they rot), and no
code-shaped fragments (S125 fires on those):

```csharp
// Filtered in memory rather than in the query: the rule is a delegate, so it cannot
// translate to SQL. Safe here because the query is already narrowed to one customer.
```

Shape: **what was done instead · why the better shape was not reachable · what makes it safe, or what
would have to change to reach it.** Anyone reading it later can either relax or knows where to start.

Log every `constrained` finding in the report with its comment location, so the set is countable. A
codebase whose `constrained` count keeps climbing in one area is telling you where the next refactor
is — that signal only exists if the compromises are written down.

### The dimensions

| # | Dimension | What a finding looks like |
|---|---|---|
| 1 | **Layering & placement** | Business logic in a controller; domain type importing `Infrastructure.*`; query logic inside a command handler |
| 2 | **Handler/service thinness** | A handler that loads + branches + maps + calls 3 services inline; a method doing >1 job; orchestration tangled with rules |
| 3 | **Naming vs ubiquitous language** | A variable/method/class whose name doesn't match `{project_docs}/domain/_glossary.yaml`; misleading name (`GetX` that mutates) |
| 4 | **Duplication (introduced)** | The same block copy-pasted across the diff; logic the diff re-implements that already exists elsewhere and should be reused |
| 5 | **Dead weight & comments** | Unused param/using/local; commented-out code; a redundant/stale comment or one that restates the code *(see **Comment quality** below)*; an interface added with exactly one implementation and no test seam needing it |
| 6 | **Data access & control flow** | `ToListAsync` then `foreach`+filter instead of `AnyAsync(predicate)`; N+1; two round-trips where one query suffices; deep nesting that a guard clause flattens *(the canonical mirror-instead-of-improve smell)* |
| 7 | **Error handling** | Swallowed exception (`catch {}`); catch-all that hides real failures; a null/edge path no test covers |
| 8 | **Test meaningfulness** | A test that asserts on the mock, not the SUT; `Assert.NotNull` as the only assertion; a negative case that doesn't actually trigger the guard; false-green (passes even if the code is reverted) |
| 9 | **Conventions conformance** | Diff violates a rule in `{project_docs}/conventions.md` / `conventions/*.yaml`. **New recurring pattern with no convention →** propose adding one (note it; do not silently invent) |
| 10 | **Mirror-vs-improve audit** | A "followed pattern X" decision from the plan that propagated debt instead of improving it, with no load-bearing justification (closes the loop on §A question 3) |
| 11 | **Base-value supersession hygiene** | The diff folds a modifier straight into a base value (`deadline = deadline + extension`); or adds a superseding field (`effectiveDeadline`, `netAmount`) while the base stays unqualified and its consumers aren't repointed; or newly points a sort/filter/derivation at a base value without marking it load-bearing *(see **Base-value supersession hygiene** below)* |
| 12 | **Smells this change introduced on purpose** | A deliberate trade with no trade recorded: state widened to `public` for one caller; mutable flag on a shared object; a static doing I/O; a string contract duplicated across BE and FE. Distinct from dimension 4, which only catches *duplication* — this catches the intentional ones. Each finding must carry **the trade** and **the cheapest fix if the trade is rejected**; a smell with a stated trade is a decision, one without is an accident |
| 13 | **Does the fix repeat the class of bug it fixes?** | Ask it as one sentence: *if the bug was "one place carrying several meanings", does the fix create a new place carrying several meanings?* Same for "state that can drift", "a rule every caller must remember", "an event inferred instead of stored". The other 12 dimensions all look at code shape; this one looks at whether the **design** re-commits the original sin at a smaller scale. Observed on PROJ-11350: the bug was one status-reason column standing for five kinds of reason, and the fix made a new `UpdatedAt` timestamp stand for both "when it changed" and "whether the user meant it" |

**Added 2026-08-14** — the list above judged *structure* well and *runtime* barely at all. These close
that gap. They are as non-business as D1–D13: every one of them would be a finding whatever the
feature does.

| # | Group | Dimension | What a finding looks like |
|---|---|---|---|
| 14 | G1 | **Coupling & construction** | A new dependency taken as a concrete type instead of the abstraction its siblings use; a class `new`-ing its own collaborator instead of receiving it; a service registered with the wrong lifetime (a scoped `DbContext` captured by a singleton — the classic silent one); a static call used where a seam is needed for testing |
| 15 | G3 | **Null & absence** | A reference dereferenced on a path where the diff itself can produce null; `!` / `.Value` used to silence the compiler rather than to state a proven fact; "not found" modelled as `null` where the caller cannot tell it from "found, empty"; a nullable annotation that contradicts what the code does |
| 16 | G3 | **Time, timezone & culture** | `DateTime.Now` where the value is stored, compared or sent across a boundary (`UtcNow` or an explicit zone); a date formatted or parsed without an explicit culture; a "today" computed in server-local time for a user in another zone; a duration built by adding days to a local time across a DST boundary |
| 17 | G3 | **Comparison & equality** | `==` on strings where the domain wants case- or culture-insensitive matching, or `ToLower()` used instead of `StringComparison`; a type used as a dictionary key or in a `Distinct`/`Contains` without value equality; `Equals` overridden without `GetHashCode`; a sort whose comparer is not a total order, so the result is not reproducible |
| 18 | G4 | **Async discipline** | `async void` outside an event handler; `.Result` / `.Wait()` / `GetAwaiter().GetResult()` on a path that could have awaited (sync-over-async, the deadlock and thread-starvation source); a `Task` created and never awaited so its exception is lost; `async` on a method that only wraps a return value |
| 19 | G4 | **Cancellation** | A long-running or I/O method with no `CancellationToken` parameter while its callers have one; a token accepted and then not passed to the call that actually blocks; `CancellationToken.None` hard-coded mid-chain, quietly breaking cancellation for everything below |
| 20 | G4 | **Lifetime & disposal** | An `IDisposable` created and not disposed; a `using` whose scope ends before the resource is finished with; `HttpClient` constructed per call instead of taken from the factory; a stream or connection handed to a caller with no stated ownership |
| 21 | G4 | **Enumeration & allocation** | An `IEnumerable` enumerated more than once (each pass re-runs the source — with a query, re-runs the query); a `ToList()` added only to enumerate once; work done inside a loop that is invariant to the loop; a string built by `+=` in a loop. **Judge against the real size of the collection** — on ten rows this is noise, and calling it a finding trains the reader to ignore the dimension |
| 22 | G5 | **Transaction & write scope** | Two writes that must both land, with no single transaction around them; `SaveChanges` inside a loop; a write and the event announcing it committed separately, so a crash between them leaves a lie; an isolation level assumed rather than stated |
| 23 | G5 | **Unbounded results & migration safety** | A query with no upper bound on rows returned, on a table that grows; paging accepted from the caller with no cap; a migration adding a non-nullable column with no default to a populated table, dropping a column still read by running code, or creating an index on a large table without stating the lock cost; a `down` script that does not undo the `up` |
| 24 | G6 | **Shared mutable state** | A `static` field that is written after startup; a cache with no eviction or no thread-safe access; state hung on a singleton that assumed one request at a time. *(Read-only `static readonly` data is fine and is the intended shape — the finding is mutation.)* |
| 25 | G6 | **Idempotency & redelivery** | A queue consumer or retried handler that would double-apply its effect if delivered twice; an operation keyed only by "now" so a retry writes a second row; a compensating path that assumes the first attempt got no further than it did |
| 26 | G7 | **Logging & diagnosability** | A failure path that returns an error with nothing logged, so production has no trace; a secret, token, password or personal detail in a log line; logging inside a hot loop; a log written at the wrong level (an expected validation refusal as `Error`); a message that states what happened but not enough to act — no id, no correlation. **And the one that hides longest: two different code paths that return the SAME message or error code, so a log line cannot say which one fired** *(see below)* |
| 27 | G7 | **Configuration & magic values** | A number, timeout, limit, URL or feature switch hard-coded where its siblings are configured; a value duplicated in two places that must agree; a default that differs between environments with nothing saying which is authoritative |
| 28 | G8 | **Input & authorization at the boundary** | Caller-supplied input reaching a query, a file path or a command without validation; an endpoint added with no authorization attribute while its siblings have one; an id taken from the request and used to read data without checking the caller may see it; an error response that leaks internal detail. *(Secrets-in-diff and unprotected-endpoint remain hard stops in `push-code` — this dimension is the softer surface around them.)* |
| 29 | G9 | **Test isolation & repeatability** | A test that shares mutable state with another (the banned-base-class trap — take the base from the recorded rule, never from the neighbouring file); a test that depends on run order, wall-clock time, or a machine-specific path; a test that leaves data behind for the next one; a test whose fixture writes outside the repo |

### Comment quality

**The standard, the timing model and the end-of-change sweep live in
`_shared/comment-protocol.md`.** Read it there; it is not duplicated here, because the phase that
*writes* comments needs the same file and used to get a one-line summary instead.

What this review adds on top of that protocol:

- §B **dimension 5** gates the protocol's §2 standard on the diff's added comment lines.
- The protocol's **§4 sweep** is the mechanical half of dimension 5 — run it before judging content.
- The **`constrained` disposition** is where the protocol's "third moment" becomes a rule: a compromise
  the gate accepts is only resolved once the comment exists.

### Base-value supersession hygiene — the deadline trap (dimension 11)

**The failure it prevents:** a feature reads a *base value* X (deadline, price, quantity). Later the business layers an adjustment on top (extension, discount, reservation). Whoever adds the adjustment either (a) **overwrites X** (`deadline += extension`) — destroying the original and silently changing meaning for *every other* reader of X — or (b) **adds `effectiveX` beside X but leaves X untouched** — so any consumer still reading X (a sort, a filter, a daily job) silently keeps using the un-adjusted value. Both fail *silently*: no crash, just wrong order / wrong number. The team forgets the consumer exists, so it never gets repointed. This is the single defect class this dimension exists to kill.

**Diff-scoped, NOT a field audit.** Dimension 11 fires ONLY on a base value the *current diff* touches — a field the diff overwrites, a modifier field the diff introduces, or a base value the diff newly wires into a sort/filter/derivation. It does **not** scan the repo's other fields: that eager 100s-of-fields scan was deliberately rejected (do-ticket Phase 6c, "why flow-gate, not field-gate"). The lever is to catch the supersession *at the moment it is authored*, when the cost is one rename — not to predict every risky field up front.

**Reactive lint (the trigger that needs no foresight):**

- Diff adds a field/column matching `effective_ | net_ | adjusted_ | final_ | actual_ | real_ <X>` (or a local-language equivalent) AND the base `<X>` still exists unqualified → **must-fix**. Resolve in this order of preference:
  1. Keep `<X>` as the base and make the new value **derived** so it cannot drift — computed column / `GENERATED ALWAYS AS (...) STORED` / view; OR
  2. **Rename** the base `<X>` → `original_<X>` / `committed_<X>` / `base_<X>` so *every* consumer breaks compile and is repointed with intent (the break is the discovery mechanism); OR
  3. If neither fits this ticket, **enumerate** the base's consumers (find-refs + grep the column name; note dynamic / raw-SQL-string / cross-service readers the compiler can't see) and repoint each, recording any you can't reach as an explicit `out-of-scope` follow-up.
  A silent "added `effectiveX`, left `X` alone" with none of the above **is** the defect.
- Diff **overwrites** a base value in place (`x = x + modifier`, accumulating) → **must-fix**: destroys the original and is an idempotency hazard (job re-runs → double-adds). Introduce the adjusted value as a separate *derived* field; keep the base immutable.
- **Mirror exclusion:** dimension 11 fires on the diff that *creates* the split. A diff that merely mirrors an already-split-and-handled base (reads `original_deadline` like its siblings do) is fine — do not re-litigate a supersession the codebase already resolved.

**Load-bearing marking (cheap; applied once the above is resolved, or when a base value newly becomes a sort/filter/derivation input):**
Leave two durable markers so the next agent OR human is warned *even with no pipeline running* — this is the "survives without an agent" half:

1. **Code annotation on the field** — a human editing in the IDE can't miss it:
   ```
   // [load-bearing] feeds: <e.g. remaining_days (stored, sorted)> | consumers: <list>
   // Extend via effective_X (derived), do NOT overwrite. See domain/_field_impact.yaml (<TICKET_ID>).
   ```
   Match the file's existing comment density/style; write it as prose — no trailing `;`, spell identifiers as words — so it doesn't trip a "commented-out code" linter (e.g. SonarC# S125).

2. **Registry entry** in `{project_docs}/domain/_field_impact.yaml` (a domain *registry* — underscore-prefixed like `_relationships.yaml`/`_concerns.yaml`, NOT an entity shard; agent-read; written lazily and grown ticket-by-ticket like `patterns/_index.yaml`):
   ```yaml
   fields:
     <entity>.<field>:
       role: sort-key | filter | derivation-input
       consumers: [<list>]
       supersede_note: "base value — extend via effective_X (derived), don't overwrite"
       discovered_in: <TICKET_ID>
   ```
   *(End-to-end wiring: 13.5 writes this entry lazily AND surfaces it in the review output (not silent) — then the **Phase 9 §A structural gate reads it** to warn before you touch the field, and **Phase 22.5 promote-knowledge** dedups it + refreshes `INDEX.md`/`_index.yaml`, the same treatment every other store gets. Until those run, the always-present marker is the code annotation, which needs no registry.)*

### Two paths, one message — the guard that stayed invisible (dimension 26)

**The failure it prevents:** the same rule is implemented in two places and both report it with the
*same* error code and the *same* text. Everything looks fine. Then a bug report arrives with that code
in the log, and nothing in the system can say which of the two refused. So you fix one, ship it,
and the other keeps refusing — because the evidence you had could not tell them apart.

**Observed 2026-08-14 (PROJ-11255).** An open-record rule lived in two classes, both emitting the same
numeric error code with the identical text. One was updated and the other was not, and the second
guard sat undetected across **two replans**. It was found by reading the code, not by any log, test,
or measurement — and the only reason it was found at all is that someone went looking a third time.

**What to look for on the diff:**

- the diff adds or changes an error code / message that already exists elsewhere in the codebase —
  grep the literal, and if there is a second site, that is the finding
- two branches inside the changed method return the same code for different reasons
- a shared helper returns a decision and each caller supplies its own message, but the messages are
  copies of each other

**The fix is not always "change the message."** Error codes and texts are often a customer contract, so
the cheapest correct fix is usually a **log line that names the site** while the customer-facing text
stays byte-identical. State which you chose.

**Why this belongs in the operability group and not in duplication (D4).** D4 asks whether the *logic*
is duplicated. This asks whether the *evidence* is ambiguous. A codebase can have one clean rule and
still be undebuggable, and it can have duplicated logic that is perfectly diagnosable. The two
findings are independent, and this one costs more, because it is the one that makes the other one
invisible.

### Severity & disposition

| Severity | Definition | Default disposition |
|---|---|---|
| **must-fix** | Introduced (not pre-existing) defect in correctness-adjacent quality: leaked layer, swallowed error, false-green test, duplicated logic that will drift, fat handler that buries a rule | **Blocks commit.** Loop to Phase 11 implement → re-run 12/13/13.5 |
| **nice-to-have** | Real improvement, not blocking: a cleaner data-access call, a better name, a guard clause, a small extraction | User picks `fix-now` / `defer` (→ `ticket-context.deferred_quality_items[]`) |
| **constrained** | The standard applies and is understood, but cannot be reached here for a sound, named reason (an interface not owned, a base class every sibling uses, a framework limit, a trade that goes the other way) | **Requires a comment at the spot** — what was done instead, why the better shape was unreachable, what makes it safe. No comment → not resolved. Counted in the report. |
| **out-of-scope** | Pre-existing debt in code this ticket merely touched | Log only; optionally `spawn_task` a cleanup. **Never fix here.** |

**`constrained` vs `nice-to-have deferred` — the line is the reason, not the effort.** "We are in a
hurry" defers; "the shape is unreachable from here" constrains. Deferring puts it in a follow-up list
that someone reads once; constraining puts it in the code, where the next person to touch that line
cannot miss it. Mislabelling a rushed decision as `constrained` is how a comment becomes a lie.

**must-fix ALSO includes** — a **behavior change with no requirements trace AND no test locking it**, regardless of how small or mechanical the diff looks. The highest-signal defect on real brownfield diffs is a silent behavior change camouflaged by an unrelated rename/refactor (e.g. a compaction loop quietly deleted). Catch these even when the surrounding hunk looks trivial. Resolution: confirm it's intended (trace to requirements) + add a test that locks the new behavior — then it downgrades to resolved.

**must-fix EXCLUDES (→ out-of-scope, never a block)** — anything whose only fault is **mirroring a pattern already pervasive in untouched code** (e.g. a new endpoint that sources `clusterId` from query exactly like its 6 siblings). The fix spans code this ticket didn't introduce, so it belongs in a spawned follow-up, not bolted onto this ticket. Marking it must-fix is the canonical scope-creep failure — blocking a small feature on a repo-wide redesign.

### Output: `code-quality-review.md`

```markdown
# Code-Quality Review — <TICKET_ID>

Diff reviewed: <N files, +X/-Y lines>  ·  Base: <base_branch @ sha>  ·  Generated Phase 13.5 at <ISO>

Groups run:     <e.g. G1 G2 G3 G5 G9 G10 G11>
Groups skipped: <e.g. G4 — the diff contains no async, using, HttpClient or loop
                      G6 — no static, singleton, cache or consumer touched
                      G7 — no log line, config value or literal added
                      G8 — no controller, endpoint, auth or caller-supplied input>
Not examined:   <dimensions dropped by lite-mode / ticket_type + why · files excluded (generated, migrations) · "pre-existing debt in touched files — logged out-of-scope, not audited">

## Verdict: <CLEAN | BLOCKED | MUST-FIX (n) | NICE-TO-HAVE (n)>

## must-fix
- [ ] <dim #> `file:line` — <one-line problem> → <one-line fix>

## nice-to-have
- [ ] <dim #> `file:line` — <problem> → <suggested improvement>   (decision: fix-now/defer)

## constrained (standard understood, unreachable here — comment left in code)
- <dim #> `file:line` — <what the standard wanted> · blocked by: <the concrete reason>
  · comment left at `file:line` · unblocks when: <what would have to change>

## out-of-scope (pre-existing, not fixed)
- <dim #> `file:line` — <debt noted> (follow-up: <spawned task / none>)

## Supersession / field-impact (dim 11 — omit section if nothing touched)
- must-fix: <entity.field> — <overwrite-in-place | superseding field added, base unhandled> → <derived / rename base / enumerate+repoint consumers>
- marked load-bearing: <entity.field> → code annotation + `_field_impact.yaml` entry (consumers: <list>)

## Conventions
- New pattern observed with no convention: <describe> → propose adding to conventions.<file>?  (y/n)
```

### Gate (the teeth)

- **Preflight, before reading any hunk** — one command, and paste its `SCOPE` line into the report header:
  ```
  python _shared/check-scope.py diff <repo> <base_branch>
  ```
  Exit 2 → stop, fix the diff resolution, do not review. Exit 0 → its `SCOPE` line **is** the
  `Diff reviewed:` header. Run it per repo on a multi-repo ticket.
- **`BLOCKED` — the diff resolved to nothing.** Per `_shared/measurement-integrity-protocol.md`: if
  `git diff <base>...HEAD` yields 0 files (stale/wrong `base_branch`, wrong repo dir, changes still
  unstaged in another worktree), the review found no problems *quite honestly* — and `CLEAN` here is the
  single cheapest way to ship an unreviewed diff, because Phase 13.5 is the last human-shaped gate before
  env-gate. Report `BLOCKED`, fix the diff resolution, re-run. **Never CLEAN on a zero-file scope**, and
  never emit a verdict without the `N files, +X/−Y` header — a `CLEAN` with no counts is unauditable.
- `must-fix` list non-empty → **do not proceed to env-gate.** Set `phase: code-quality-review` with the open list in `ticket-context.quality_findings[status=open]`. Loop: implement → regression → completeness-audit → code-quality-review. (FM-QUALITY-MUST-FIX.)
- `must-fix` empty, `nice-to-have` present → surface the list once; user chooses per item `fix-now` / `defer`. Defer logs to `ticket-context.deferred_quality_items[]` and surfaces in the Phase 23 done summary + PR description.
- All clean → 1-line summary (`Code-quality: clean (N hunks, 0 must-fix). Proceeding.`) and proceed. Mirror the Phase 9 auto-proceed ethos: don't interrupt when there's nothing worth interrupting for.

### Lite mode

For `bugfix-small` and `refactor`: run **G1, G2, G9, G11** plus any **content-gated group the diff
actually triggers** (G4–G8). Skip G3's culture/equality checks and G10's glossary/conventions
deep-checks. ≤1-screen output. (G11 carries dimension 11, which stays on because refactors
rename/repoint fields — the exact place supersession bites.)

The content-gated groups stay on even in lite mode, and that is the point: a one-line bugfix that
adds a `.Result` or drops a `CancellationToken` is exactly the diff nobody reviews carefully. Lite
mode shortens the *always-on* work; it never turns off a group the diff itself asked for.

---

## What this is NOT

- **Not a bug hunter** — correctness bugs are caught by tests + api-test (Phase 15) + invariant-check. This is quality only. (Mirrors the `/code-review` vs `/simplify` split.)
- **Not a repo-wide audit** — diff-scoped, always. Pre-existing debt → out-of-scope.
- **Not a parallel meaning model** — this touches only the code-quality layer; it does not introduce one (the meaning layer is the scan-init artifact suite, not a separate model doc).
