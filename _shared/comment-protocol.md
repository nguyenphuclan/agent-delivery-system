---
name: comment-protocol
description: When to write a code comment, what earns one, and the mechanical sweep that runs before the change ships. Split by TIMING on purpose — the reason goes in at the moment of the decision, the form is checked at the end. Referenced by do-ticket's implement phase (write-time) and by code-quality-review (check-time), so the writer and the reviewer read the same rules.
---

# comment-protocol

## Why this is a shared protocol and not a skill

A skill is something you invoke. Commenting is not a workflow — it is a rule set that two different
phases need: the one **writing** code and the one **reviewing** it. It used to live only inside
`do-ticket/code-quality-review.md`, which the writer never opens, so the implement phase carried a
one-line summary and a pointer. Two copies, and the fuller one in the wrong hands.

One invokable piece does exist: the **end-of-change sweep** (§4). That is a step in the flow, not a
separate skill.

---

## 1. Timing — the part everyone gets wrong

The usual question is "comment while coding, or after?" Both answers are wrong, because they treat a
comment as one thing. It is two, and they have opposite deadlines.

| | Deadline | Why |
|---|---|---|
| **The reason** (why this shape, what was rejected, what breaks if changed) | **At the moment of the decision. Final, not rough.** | It is the only part you cannot reconstruct later. An hour after the fact, the code is all that is left to look at — so you will write what the code *does*, which is the one comment nobody needs. |
| **The form** (wording, ids, encoding, staleness, does it restate the code) | **One sweep at the end.** | Every item is checkable by rule, cheaply, and none of it needs the decision context. Doing it inline breaks flow for no gain. |

So "write a rough comment now, tidy it later" is right about the *form* and a trap for the *reason*.
A rough reason becomes one of two things: a permanent half-truth, or a line someone deletes because it
looked like filler. Write the reason properly the first time — it is one or two sentences, and it is
the whole value.

### The third moment, which is the highest-signal one

**When anyone asks "why is it like this?", a comment is missing.** Not the answer to the question — the
comment. That question is free evidence that the code does not explain itself, and it arrives from a
reviewer, a gate, a failing test, or your own future self re-reading a diff.

Treat every one of these as a write trigger:

- a reviewer asks why
- a quality gate flags a shape you then justify (see the `constrained` disposition in
  `do-ticket/code-quality-review.md` — that one **requires** a comment by rule)
- you almost "fixed" something and found out it was load-bearing
- you had to re-derive a fact you already knew last week

### Where a comment is NOT the answer

Reach for these first; a comment is the fallback when none of them fit:

1. **A better name.** If the comment explains *what*, rename instead.
2. **A small extraction.** A named method beats a comment describing the next six lines.
3. **A named constant.** `MaxOpenOrdersPerCustomer` beats `// 3 = the cap`.
4. **A test.** "This must stay sorted" is better expressed as a test that fails when it does not.

---

## 2. What earns a comment

A comment earns its place only if it says something the code cannot.

| Rule | Do | Don't |
|---|---|---|
| **Why, not what** | The invariant held, the edge case guarded, why *not* the obvious approach, the constraint from outside | Restate the code: `// increment i`, `// constructor`, echoing the method name |
| **Name the rejected option** | "Filtered in memory because the rule is a delegate and cannot translate to SQL" | Leave the reader to wonder whether you knew about the better shape |
| **Document the non-obvious** | Units and ranges, ordering and thread-safety constraints, side effects, what makes it safe, what would make it unsafe | Comment the obvious and stay silent on the surprising |
| **Truthful and in sync** | Update or delete the comment in the *same hunk* that changes the code | Leave a stale comment describing old behaviour — worse than none |
| **Self-contained** | State the constraint directly | External identifiers: ticket keys, test-case ids, requirement ids, paths to other artifacts. They rot and they force a context switch |
| **No commented-out code** | Delete it; git remembers | `// oldFoo(...)` "just in case" |
| **TODO carries an owner** | A tracked task, or nothing | Bare `// TODO` — dead weight |
| **Match the file** | The file's existing density and style comes first | Bolt doc-comments onto one member in a file whose peers have none, or drop them where peers document |

### The amendment for agent-written code

When code is produced faster than the reasoning behind it is recorded, the share of code whose reason
nobody wrote down goes **up**. And the reader — human or agent — reconstructs intent from the code
alone, which can only show what was built. It cannot show what was considered and rejected.

So in agent-written code the highest-value comment is the one recording **the road not taken**:

```csharp
// PRE_ORDER is left refused ON PURPOSE. A pre-order already has its own family of
// preconditions asking whether the item is in stock or back-ordered. Exempting it
// here would put two mechanisms in charge of one answer. The day someone wants it,
// decide which one owns it first, then add a line.
```

Without that, the next person reads an incomplete-looking allow-list and "finishes" it. The comment is
the difference between a decision and an oversight — and from the code alone they are identical.

Three shapes worth writing every time they apply:

- **the deliberate exclusion** — what is missing on purpose, and what would unblock it
- **the load-bearing quirk** — the thing that looks removable and is not, plus what depends on it
- **the compromise** — the better shape, why it is out of reach here, what makes this safe

---

## 3. Encoding — ASCII unless the file says otherwise

Non-ASCII characters in a source file that carries **no byte-order mark** are decoded as ANSI by any
tool that guesses, and become mojibake. Em dashes, en dashes, curly quotes, ellipses and box-drawing
rules are the usual carriers, and none of them is information.

**Rule: comments are ASCII-only unless the file already has a BOM.** Use `-` for a dash, `'` and `"`
for quotes, `...` for an ellipsis. Do not draw rules or boxes — a banner made of `---` adds nothing
that the section's words do not already say.

Check it, do not eyeball it:

```bash
python -c "
import sys
p = sys.argv[1]
b = open(p,'rb').read()
print('BOM:', b[:3]==b'\xef\xbb\xbf')
n = [c for c in b.decode('utf-8') if ord(c) > 127]
print('non-ASCII:', len(n), sorted(set(n)))
" <file>
```

Observed 2026-08-14 (PROJ-11255): one new test file carried **271** non-ASCII characters, all of
them decoration, in a file with no BOM.

---

## 4. The end-of-change sweep

Runs once, on the diff, before the change ships. Mechanical — no judgement about content, only form.
Every item is a grep.

| Check | Command shape |
|---|---|
| External identifiers in comments | grep the diff's added comment lines for ticket / AC / TC / requirement id patterns and for paths to other artifacts |
| Non-ASCII in files with no BOM | the snippet in §3, per changed file |
| Commented-out code | grep added lines for a comment containing an assignment, a call with `(`, or a trailing `;` |
| Bare TODO / FIXME | grep for `TODO` and `FIXME` with no tracked owner |
| Comment and code out of sync | for each changed hunk that has a comment above it, read both — this is the one item that needs eyes |
| Restates the code | a comment whose words are the identifier names in a different order |
| Comment where a name would do | a comment explaining *what* a local or expression is |

### Language gotchas — check these at write time, they bounce a clean PR

**C# XML doc comments are XML.** A literal `<` opens a tag, and the build warns `CS1570 badly formed
XML`. Escaping it (`&lt;`) compiles but reads badly. **Reword so the angle brackets are not needed** —
"an order type followed by a customer name in brackets" beats `&lt;OrderType&gt; (&lt;customer&gt;)`.

**SonarC# S125 "sections of code should not be commented out"** false-positives on prose that *looks*
like code: a trailing `;`, an `Identifier.Method(...)` fragment, or operators (`==` `!=` `&&` `||` `?:`)
inside the comment. Write prose: no trailing semicolon, spell identifiers as words ("remaining days",
not the PascalCase symbol), describe conditions in English ("when completed or on hold", not the
boolean expression). If a comment genuinely needs to show code, that is the signal to extract a named
method instead.

**S3358 "ternary operators should not be nested"** and S125 form a trap: fixing the ternary with an
explanatory comment then trips S125. Reword the comment as prose in the same pass.

---

## 5. Who reads this

| Phase | Uses |
|---|---|
| do-ticket's implement phase (write-time) | §1 reason-at-decision-time · §2 what earns one · §3 encoding · §4 language gotchas |
| `do-ticket/code-quality-review.md` §B dimension 5 (check-time) | §2 as the standard · §4 as the sweep |
| the `constrained` disposition | §1 third moment — that disposition requires a comment by rule |

Both sides read the same file, so the reviewer cannot hold the writer to a rule the writer never saw.
