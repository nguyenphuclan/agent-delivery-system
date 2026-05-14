---
name: requirements-clarification-protocol
description: Proactively generates 80-90% of the questions a senior dev would ask PO before committing to a ticket. Two-tier reminder system — Tier 1 gentle after analyze, Tier 2 sharp with rework-cost framing before commit if user dismissed without follow-up. Targets the root cause of "AI làm đúng nhưng thiếu" — unclear requirements that cause 5-10x rework.
---

# Requirements Clarification Protocol

## Purpose

The single most expensive bug class is **vague requirements**. Tickets that look clear at start become 5-10 rework cycles because nobody asked the right question to PO upfront.

This protocol forces AI to act like a senior dev reading the ticket: **predict 80-90% of the questions that, if not confirmed with PO, will cause rework**. Then surface them with rework-cost framing so user can make informed choice — not lazy choice.

Two-tier delivery:
- **Tier 1 (gentle, post-analyze):** surface questions, allow defer/dismiss without blocking
- **Tier 2 (sharp, pre-commit):** if questions still unaddressed, surface again with cost predictions, similar past incidents, explicit "I accept rework risk" ack required

## When to run

| Phase | Tier | Behavior |
|-------|------|----------|
| `analyze` (after requirements-analysis.md drafted) | Tier 1 | Generate questions; surface to user; non-blocking — user can defer |
| Pre-commit (Step 7c, after completeness-audit) | Tier 2 | Re-surface deferred/dismissed-without-followup questions; require explicit ack |

## When PO is unavailable / vague — see Self-Detailing Protocol

Standard Tier 1/Tier 2 below assume "ask PO". When PO writes vague requirements ("just make it work, don't care") + deadline is hard, that assumption breaks.

For those cases, **also load `~/.claude/skills/_shared/self-detailing-requirements-protocol.md`**. It classifies questions into 3 buckets:
- `needs_po` (1-3 items) — actually escalate
- `ai_default` (most items) — AI proposes default with source citation, user bulk-accepts
- `gray_zone` (1-2 items) — quick decisions

Self-detailing auto-triggers when clarity score < 60, OR when user passes `--speed-mode`. Tier 2 reminder shrinks accordingly — only blocks on `needs_po` deferred items.

## Tier 1 — Question Generation

### Sources (run all in parallel)

#### Source A — Generic pitfalls (always)

Triggered by these patterns in requirements text:

| Pitfall | Trigger | Question to ask |
|---------|---------|-----------------|
| **Vague verb** | "support", "handle", "manage", "improve", "enhance" | "What does '<verb>' specifically mean? Define observable behavior." |
| **Missing acceptance criteria** | No bulleted "Given/When/Then" or no measurable output | "How do we verify this works? What's the smallest test case PO would accept?" |
| **Ambiguous pronoun** | "it", "they", "this", "the user" without prior antecedent | "When you say '<pronoun>' — which entity exactly?" |
| **Implicit role** | Action mentioned without explicit actor | "Who can perform <action>? Which roles? What about other roles — error or hidden?" |
| **Undefined edge case** | Happy path only, no error/empty/concurrent mention | "What happens if <input> is empty / null / concurrent / oversized / repeated?" |
| **Out-of-scope ambiguity** | Adjacent feature mentioned but not scoped | "Is <adjacent feature> in scope, or separate ticket?" |
| **Unspecified persistence** | Action implies state change but no audit/history mention | "Should this action be auditable? Logged? Reversible?" |
| **Time/date ambiguity** | "yesterday", "recent", "old" without definition | "Define '<time term>' — by what cutoff exactly?" |
| **Cross-tenant / cross-org** | Multi-tenant context implied | "Does this affect only the calling user's org, or cross-org?" |
| **Concurrency unspecified** | Mutating operation on shared resource | "Two users do this at the same time — first wins, both proceed, or error?" |

#### Source B — Project-specific pitfalls

Read `public-project-docs/<project>/requirements-pitfalls/_index.yaml` if exists. Format:

```yaml
- id: PIT-AUTH-1
  pattern_match: "ticket touches Controller endpoint"
  question: "Which roles can call this? What's the policy attribute? What error code for non-allowed roles?"
  rework_probability: 0.85
  similar_past_incidents:
    - ticket: PROJECT-9821
      cost_hours: 4
      reason: "Forgot to set [Authorize(Roles=...)], anonymous users could hit endpoint"

- id: PIT-MIGRATION-1
  pattern_match: "ticket adds DB column"
  question: "Backfill strategy for existing rows? Default value? Index needed?"
  rework_probability: 0.7
  similar_past_incidents:
    - ticket: PROJECT-7733
      cost_hours: 2
      reason: "Added NOT NULL column without default, migration failed on prod with existing rows"

- id: PIT-STATE-1
  pattern_match: "ticket modifies state machine for entity X"
  question: "What about active records currently in old states when this deploys? Backfill, force-transition, or leave alone?"
  rework_probability: 0.8

- id: PIT-CROSS-SVC-1
  pattern_match: "ticket changes API/event consumed by other service"
  question: "Deploy ordering — producer first or consumer first? Backwards-compat strategy?"
  rework_probability: 0.9
```

User maintains this file over time. `/learn` proposes new entries from telemetry (recurring rework patterns become new pitfalls).

#### Source C — Domain invariants

Use `_shared/domain-mapping-protocol.md` to identify entities touched. For each:
- Read entity shard in `public-project-docs/<project>/domain/<entity>.yaml`
- For each invariant (uniqueness, lifecycle, ownership) — check if requirement explicitly addresses it
- If not → generate question

Example: requirement says "create new Network". Domain has `NET-OWNER-1: every Network has exactly one owner Org`. Requirement doesn't say which org. Question: "Which Org owns the new Network — caller's org by default? Specified in request? Inherited from parent?"

#### Source D — Cross-entity relationships

From `public-project-docs/<project>/domain/_relationships.yaml`. If requirement touches entity A, check:
- A's parent — does requirement consider parent's state?
- A's children — what happens to children when A changes?
- Sibling entities — any side effects?

#### Source E — Historical rework

Read telemetry across all prior tickets:
```
{output}/tickets/*/run-telemetry.yaml
```

Look for:
- Tickets in same area (`ticket_context.domain_entities_in_scope` overlap)
- That had `update_cycles.count >= 1` (got reworked)
- What caused the rework (`update_cycles.triggers`)

If same root cause appeared 2+ times → high signal: "Last time touching <entity>, ticket was reworked because <X>. Confirm <X> is handled this time?"

### Question card format

```yaml
- id: Q-1
  question: "Which roles can transfer ownership of a Network?"
  source: PIT-AUTH-1 (project-specific) + Source A (implicit role pattern)
  rework_probability: 0.85
  rework_cost_estimate: 3-5 hours
  similar_past_incident:
    - ticket: PROJECT-9821
      what_happened: "Built endpoint without [Authorize], rolled back after security review"
      cost: 4 hours
  requirement_quote: "User can transfer Network to another org"
  user_action_options:
    - has_answer: write answer here, will save to requirements-clarified.md
    - defer_to_po: mark for PO confirmation, AI will remind before commit
    - dismiss: AI continues but logs for retrospective
```

### Tier 1 surface (after analyze-requirements writes requirements-analysis.md)

Output to user (not full plan, not all questions):

```
## Requirements Clarification — 7 questions identified

Based on this ticket touching Network entity + Controller endpoints, here are the questions that — if not confirmed with PO — have HIGH probability of causing rework:

### CRITICAL (rework probability > 70%)
1. **Roles allowed to transfer Network?** [PIT-AUTH-1]
   Rework risk: 85% / ~4h
   Past: PROJECT-9821 reworked because [Authorize] missing
   Action: [answer] / [defer to PO] / [dismiss]

2. **Active Networks in old state when this deploys — what happens?** [PIT-STATE-1]
   Rework risk: 80% / ~3h
   Action: [answer] / [defer to PO] / [dismiss]

3. **Producer vs consumer deploy order for the new event?** [PIT-CROSS-SVC-1]
   Rework risk: 90% / ~6h
   Past: PROJECT-7110 had 2 days of consumer crash because deployed wrong order
   Action: [answer] / [defer to PO] / [dismiss]

### IMPORTANT (rework probability 40-70%)
4. **Empty source-org case — error or no-op?** (Source A: undefined edge case)
   Action: [answer] / [defer to PO] / [dismiss]

[... 3 more ...]

User: choose action for each. Defer = AI will remind you before commit.
```

User responds. AI saves to `requirements-clarifications.yaml`:

```yaml
clarifications:
  - q_id: Q-1
    status: deferred       # answered | deferred | dismissed
    user_note: "Will check with Khoa tomorrow — assuming admin-only for now"
    addressed_at_phase: null
  - q_id: Q-2
    status: answered
    user_note: "Force-transition to NEW state on deploy. Will write migration."
    addressed_at_phase: analyze
  - q_id: Q-3
    status: dismissed
    user_note: "Same service deploys both, ordering doesn't matter"
    addressed_at_phase: analyze
```

User can defer / dismiss freely. **Tier 1 is non-blocking.**

## Tier 2 — Pre-commit Reminder (the "sharp" reminder)

Triggered after `completeness-audit` (Step 7b.5), BEFORE commit (Step 7c).

### Algorithm

1. Read `requirements-clarifications.yaml`.
2. Filter: items with status=`deferred` AND no `addressed_at_phase` set, OR status=`dismissed` for items with rework_probability > 70%.
3. If filtered list is empty → silent, proceed to commit.
4. If non-empty → **block, surface Tier 2**.

### Tier 2 surface

Designed to be unmissable. Not "are you sure?" — but "here's exactly what you'll regret":

```
══════════════════════════════════════════════════════════════════════
  ⚠ STOP — REWORK RISK before commit
══════════════════════════════════════════════════════════════════════

You deferred or dismissed 3 questions in analyze phase.
Based on this project's rework history, this commit has:

  ESTIMATED REWORK PROBABILITY: 78%
  ESTIMATED REWORK COST: 7-12 hours over 2-3 PR cycles
  EXPECTED COMPLETION DELAY: 1-2 working days

Specifically:

┌──────────────────────────────────────────────────────────────────┐
│ Q-1: "Roles allowed to transfer Network?"                        │
│   Status: DEFERRED — never followed up with PO                   │
│   Rework risk: 85% / ~4h                                         │
│   Past: PROJECT-9821 reworked because [Authorize] missing.        │
│         reviewer caught it in PR review, you spent 4h re-doing.      │
│                                                                  │
│   Quick mitigation:                                              │
│     - Pause now, message PO, wait for answer (15-30 min)         │
│     - OR commit with anonymous policy as default + flag in PR    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ Q-3: "Producer vs consumer deploy order?"                        │
│   Status: DISMISSED — you said "same service, ordering doesn't   │
│           matter"                                                │
│   AI second opinion: Network event is consumed by Notification   │
│   service (different deployment). Past: PROJECT-7110 caused 2-day │
│   consumer crash from wrong order.                               │
│                                                                  │
│   Quick mitigation: confirm with team lead or check deploy pipeline.  │
└──────────────────────────────────────────────────────────────────┘

[... 1 more ...]

══════════════════════════════════════════════════════════════════════
TO PROCEED WITH COMMIT, choose ONE:
══════════════════════════════════════════════════════════════════════

  [pause]   I'll stop, message PO, address these first  ← RECOMMENDED
  [commit-with-flags]  Commit but list these as TODO in PR description
  [accept-rework]  I accept rework risk, explain in 1 sentence: ___

  Type your choice. Empty input = pause.
══════════════════════════════════════════════════════════════════════
```

Note the framing:
- **Cost is concrete** ("7-12 hours") not abstract ("might be slow")
- **Past incident is specific** (ticket ID + person + outcome)
- **Recommended option is highlighted** — gentle nudge toward right choice
- **Default on empty input is `pause`** — laziness leads to safety, not danger
- **`accept-rework` requires 1-sentence explanation** — friction proportional to risk

### Tier 2 outcomes

| User choice | Effect |
|-------------|--------|
| `pause` | State `phase: blocked`, `blocked_reason: "PO clarification pending: Q-1, Q-3"`. Resume re-runs Tier 2 check. |
| `commit-with-flags` | Proceed to commit. PR description auto-includes "Open questions" section listing deferred items. Telemetry: `tier2_used: commit-with-flags`. |
| `accept-rework <reason>` | Proceed. Reason saved. Telemetry: `tier2_used: accept-rework`. /learn flags repeated `accept-rework` for review. |

### Anti-laziness reinforcement

- Tier 2 surface is the **last gate** before commit. There's no Tier 3.
- Reminder text is intentionally formatted to be visually striking (box borders, caps, color cue if terminal supports).
- `pause` is default — even if user just hits Enter, they pause (which is the safe outcome).
- `accept-rework` requires typing reason — friction discourages laziness without preventing it.

## How `analyze-requirements` consumes this protocol

Replace existing "open questions" gate with this protocol's Tier 1:

```markdown
## Step: Generate clarification questions

Follow `~/.claude/skills/_shared/requirements-clarification-protocol.md` Tier 1.

Skill-specific overrides:
- `min_questions`: 3 (always generate at least 3, even for trivial tickets)
- `max_questions`: 15 (cap to avoid overload)
- `surface_critical_threshold`: 0.7 (rework_probability cutoff for CRITICAL section)
```

Output: `requirements-clarifications.yaml` (new sibling of requirements-analysis.md).

## How `do-ticket` consumes this protocol

Add new sub-step in Step 7c (commit):

```
Step 7c.0 — Pre-commit clarification recheck (NEW)

Read requirements-clarifications.yaml.
If any item has status=deferred without addressed_at_phase set,
   OR status=dismissed AND rework_probability > 0.7:
  → Run Tier 2 surface per requirements-clarification-protocol.md
  → Block until user chooses pause / commit-with-flags / accept-rework
Else:
  → Silent, proceed to commit.
```

## Project pitfall registry — `public-project-docs/<project>/requirements-pitfalls/_index.yaml`

User builds this over time. Initial seed:

```yaml
# Auth & permission
- id: PIT-AUTH-1
  pattern_match: "ticket touches Controller endpoint"
  question: "Roles allowed? Policy attribute name? Error response for denied roles?"
  rework_probability: 0.8

# Migration & schema
- id: PIT-MIGRATION-1
  pattern_match: "ticket adds DB column"
  question: "Backfill strategy? Default value? Index? Lock duration on prod?"
  rework_probability: 0.7

- id: PIT-MIGRATION-2
  pattern_match: "ticket modifies existing column"
  question: "Backwards compat for running services during deploy? Backfill needed?"
  rework_probability: 0.85

# State machine
- id: PIT-STATE-1
  pattern_match: "ticket changes entity state machine"
  question: "What about records in old states at deploy time? Force-transition / leave / migrate?"
  rework_probability: 0.8

# Cross-service
- id: PIT-CROSS-SVC-1
  pattern_match: "ticket changes API/event consumed by another service"
  question: "Deploy ordering? Backwards-compat? Version bump or additive change?"
  rework_probability: 0.9

# Audit
- id: PIT-AUDIT-1
  pattern_match: "ticket adds mutating endpoint"
  question: "Should this be audited? Where (audit_log table, event)? What's logged?"
  rework_probability: 0.6

# Multi-tenancy
- id: PIT-TENANT-1
  pattern_match: "ticket queries shared table without org filter"
  question: "Should this filter by caller's org? Cross-org accidental data leak risk?"
  rework_probability: 0.85
```

`/learn` skill auto-proposes new entries from telemetry. User confirms before adding.

## Telemetry

```yaml
clarification:
  questions_generated: 7
  by_source:
    generic: 3
    project_pitfalls: 2
    domain_invariants: 1
    historical_rework: 1
  user_actions:
    answered: 4
    deferred: 2
    dismissed: 1
  tier2_triggered: true
  tier2_outcome: pause   # pause | commit-with-flags | accept-rework
  tier2_unaddressed_count: 2
  estimated_rework_probability: 0.78
  estimated_rework_cost_hours: 7
```

`/learn` insights:
- Repeated `accept-rework` choices → user is too lazy or AI over-flags. Investigate per-ticket.
- Tier 2 triggered + actual rework happened → calibration good (predicted X, X happened).
- Tier 2 NOT triggered + rework happened → AI missed a question type. Propose new pitfall.
- Pitfall ID hit ≥3 times → propose promoting to higher rework_probability or making it a hard-block.

## Anti-patterns (do NOT do)

- ❌ Surface 30 questions — overload kills attention. Cap 15, top 5-10 in CRITICAL section.
- ❌ Skip Tier 2 because user already saw Tier 1. The whole point is anti-laziness.
- ❌ Block at Tier 1. Tier 1 must be non-blocking — block at Tier 2 only.
- ❌ Use abstract framing in Tier 2 ("rework might happen"). Use concrete framing ("4 hours, like PROJECT-9821").
- ❌ Auto-add to pitfall registry without user confirmation.
- ❌ Make `accept-rework` a 1-key choice. Friction proportional to risk.

## Vietnamese summary

Mỗi ticket, AI sẽ:
1. **Sau analyze:** đưa 5-10 câu hỏi quan trọng (CRITICAL = rework probability > 70%) cần confirm với PO. User chọn answer / defer / dismiss. **Không block flow.**
2. **Trước commit:** nếu vẫn có deferred/dismissed mà chưa follow-up → reminder lần 2 với:
   - Cost cụ thể: "78% rework probability, ~7-12 giờ qua 2-3 PR cycles"
   - Past incident cụ thể: "PROJECT-9821 đã rework 4h vì lý do này"
   - Buộc user chọn 1 trong 3: `pause` (default), `commit-with-flags`, `accept-rework <reason>`

Lười không sao — Tier 2 sẽ đập vào mặt, default = pause, không thoát được.
