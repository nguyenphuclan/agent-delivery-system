---
name: pre-flight-protocol
description: Mandatory checklist that runs BEFORE any heavy/side-effecting skill, regardless of how the skill is invoked (direct command, orchestrator routing, mid-conversation). Replaces the implicit "assistant always-on" assumption with an explicit per-skill contract. After adopting this, users no longer need to prefix `/assistant` before skills.
---

# Pre-flight Protocol

## Why this exists

Until now, the system relied on an **implicit assumption** — that the assistant orchestrator was always loaded into context (per `CLAUDE.md` global instructions), so any skill could trust that:
- `MEMORY.md` was read
- `projects.md` was loaded
- `observations.md` rules with count ≥ 2 were applied
- Routing rules were considered

This assumption breaks when:
- Conversation context gets compacted and CLAUDE.md preamble is dropped
- A new conversation starts and the user invokes a skill directly before any prior turn establishes orchestrator state
- The user calls a skill via slash command without any prior natural-language interaction
- A skill is invoked from another skill (mid-flow handoff) without re-loading user-level state

The workaround was: user manually prefixed `/assistant` before every skill call. That's coupling user discipline to a system invariant — fragile.

**This protocol fixes it:** every heavy skill explicitly declares its pre-flight requirements. The skill itself ensures the checks run, regardless of how it was invoked. User no longer needs `/assistant` prefix.

## Tier system

Skills are classified by side-effect surface:

| Tier | Description | Pre-flight |
|------|-------------|------------|
| **A — Heavy ops** | Multi-step, persistent state, mutating side effects, code changes, deploys | Full pre-flight (mandatory) |
| **B — Side effects** | Single-step but writes files / external systems | Core pre-flight (mandatory subset) |
| **C — Read-only / utility** | Lookups, listings, displays | Skip pre-flight (no overhead) |
| **D — Already-in-flow** | Resume / continue commands of an active session | Skip pre-flight (state already hydrated) |

### Tier classification

| Tier | Skills |
|------|--------|
| A | `do-ticket`, `domain-problem-solver`, `hotfix-deploy`, `implement`, `learn-crud`, `verify-env`, `handle-pr-review` |
| B | `jira-to-requirements`, `analyze-requirements`, `write-test-cases`, `implement-plan`, `write-unit-tests`, `qa-checklist`, `pr-description`, `scan-init`, `scan-update`, `scan-api-docs`, `invariant-check`, `worktree-setup`, `runbook` (write ops), `specimen-sandbox` (`/specimen-add`) |
| C | `doc-manager` (LIST/OPEN), `runbook` (recall ops), `specimen-sandbox` (`/specimen-find`), `learn` (read-only sweep), `promote-observations`, `my-brain` (read), `doc-for-role` |
| D | Any skill invoked with `resume`, `continue`, `pr-review`, `update` flags where state already exists |

When in doubt, default to Tier B.

## The pre-flight checklist

### Full pre-flight (Tier A — mandatory)

Run these in order. Skip any check that's already satisfied in the current session (memoization).

1. **Memory load** — read `~/.claude/skills/assistant/projects/<global>/memory/MEMORY.md` if not already in context. Apply any feedback rules referenced.

2. **Observations apply** — read `~/.claude/skills/assistant/observations.md`. For every entry with `count ≥ 2`, apply as mandatory behavior for this skill's run.

3. **Project context resolution** — read `~/.claude/skills/assistant/projects.md`. Confirm:
   - `active` project is set
   - All fields the skill requires (`output`, `repos`, `db`, `jira_prefix` per skill's needs) are populated
   - If any required field missing → G10: ask once, save to projects.md, continue

4. **Two-store knowledge lookup** — read keyword indexes from BOTH knowledge stores:
   - **Personal store** (vault, portable, GitHub repo): `$VAULT_PATH/_meta/INDEX.md` — engineering brain, learning, reference, life-ops, notes
   - **Project store** (public-project-docs, local-only): `public-project-docs/<active-project>/INDEX.md` — project-specific working memory, tickets, runbooks, domain index

   Process:
   1. Extract 3–6 keywords from task description (domain entities, operations, repo names)
   2. Grep BOTH index files for matches → collect (filepath, match_count) tuples per store
   3. Read up to **3 top-matched files per store** (max 6 reads total)
   4. Inject relevant excerpts into task context, tagged with store origin

   Skip if: task is purely mechanical (git ops, file rename, format-only).
   Apply if: implement, diagnose, design, review, explain, plan.

   Token budget: 2 index reads + ≤ 6 content reads. Bounded — does not scale with store size.

5. **Session memoization replay** — if any prior skill in this session populated state files (ticket-state.yaml, ticket-context.yaml, investigation.md, etc.), load them into context BEFORE running. Skip any check whose result is already present.

6. **Risk gate pre-check** — scan the skill's stated impact. If any G3/G7 condition is implied by the invocation, surface to user before starting:
   - G3: irreversible action mentioned (deploy, force push, drop, migration)
   - G7: security-sensitive surface (auth, secrets, prod data, public endpoint)

7. **Telemetry log** — append entry-point record to the skill's telemetry file:
   ```yaml
   pre_flight:
     entry_point: direct      # direct | orchestrated | mid-flow-handoff | resume
     invoked_at: <iso>
     checks_skipped:           # for transparency — what was already cached
       - memory: cached_in_session
       - projects: cached_in_session
     checks_run:
       - observations: 3 rules applied
       - project_context: confirmed (active=<project>)
       - knowledge_lookup:
           vault_hits: [_brain/judgments/no-db-mock-in-integration.md, Techlead/Aggregate boundary.md]
           project_hits: [knowledge_task.md, runbooks/temporal-namespace-init-wsl.md]
       - risk_gate: G3 implied (db migration possible) — flagged
   ```

### Core pre-flight (Tier B — mandatory subset)

Cheaper. Steps 1, 3, 4, and 7 above. Skip observations replay and risk gate (lighter ops, less likely to break user trust). Knowledge lookup still runs because Tier B skills (analysis, planning, requirements) benefit most from cross-store context.

### Phase-readiness check (skill opt-in via `requires_phase_readiness`)

For phased skills (do-ticket and similar pipelines that consume public-project-docs artifacts per phase), add this between steps 5 and 6:

1. Read `<output>/<project>/_index.yaml.phase_readiness[<current_phase>]`.
2. If absent (no readiness map yet) → warn once: "phase_readiness not populated; consumer artifact freshness unverified". Continue.
3. If `ready: true` → continue silently.
4. If `ready: false` → **G10 block**. Surface `missing[]` to user with three options:
   - `rescan` → invoke `scan-update <artifact>` for each missing artifact, recompute readiness, retry pre-flight.
   - `skip` → mark phase as running degraded (logged in telemetry: `phase_readiness_skipped: true`), continue.
   - `abort` → halt pre-flight, return to caller.

Skill declares the check via SKILL.md frontmatter override:

```markdown
## Pre-flight
Tier: A
requires_phase_readiness: true
```

Without that override, the check is skipped (preserves Tier-A skills that don't consume public-project-docs artifacts).

### No pre-flight (Tier C / D)

Skip entirely. The savings matter for fast recall ops.

## Memoization rules

A pre-flight check is **skippable** when:
- Same check ran successfully in this session (track via session-level memo)
- < 30 minutes since last check
- No mutating action between then and now
- Underlying source file (MEMORY.md, projects.md, observations.md) hasn't changed (mtime check)

Re-run is forced when:
- Source file modified mtime is newer than last memoization
- > 30 minutes idle
- User explicitly says "re-verify" or "reload"
- A 4xx/5xx error occurred (state may have shifted)

## How a skill consumes this protocol

In SKILL.md, near the top (right after frontmatter), add:

```markdown
## Pre-flight

Tier: A (or B / C / D)

Follow `~/.claude/skills/_shared/pre-flight-protocol.md`.

Skill-specific overrides:
- `requires_project_fields`: [active, output, repos, jira_prefix]
- `risk_signals`: [g3-deploy, g7-prod-data]    # for risk gate pre-check
- `skip_when`: state file <foo>.yaml exists with phase != initial   # auto-Tier-D
```

Claude reads SKILL.md, sees the Pre-flight section, runs the appropriate checklist, then proceeds with skill-specific logic.

## Anti-patterns (do NOT do)

- ❌ Skip pre-flight on Tier A skill because "user seems to know what they're doing"
- ❌ Run full pre-flight on Tier C skills (wastes tokens, irritates user with repeated context)
- ❌ Auto-fill missing project fields by guessing from OS env or path heuristics — always G10 ask
- ❌ Run pre-flight silently — always note "X skipped — verified Nm ago" or "Pre-flight: 3 checks run, 2 cached" so user sees what's happening
- ❌ Re-prompt user for `/assistant` prefix — this protocol replaces that workaround

## Relationship to assistant orchestrator

The assistant orchestrator (`~/.claude/skills/assistant/SKILL.md`) is still the **routing brain**. It decides which skill to invoke when user input is ambiguous, manages cross-skill state, and handles open-ended conversation.

What changes with this protocol:
- **Before:** Assistant brain was the *only* layer guaranteeing pre-flight. Skill called directly = no guarantee.
- **After:** Each Tier A/B skill self-ensures pre-flight via this protocol. Assistant brain is now optional for direct skill calls.

User can:
- Type `/do-ticket PROJECT-1234` directly — pre-flight runs inside do-ticket
- Type natural language — assistant orchestrator routes to do-ticket — same pre-flight runs (memoized if assistant already did it)
- Resume a session — Tier D skip — fast resume

Both paths are equally safe. User no longer has to type `/assistant` prefix to ensure context loading.

## Migration note

After this protocol is adopted by all Tier A skills, `CLAUDE.md` global instructions can be simplified — the "always operating as assistant orchestrator" rule becomes a soft default rather than a hard requirement. Recommend updating CLAUDE.md to:

> "Default to assistant orchestration mode, but heavy skills run their own pre-flight per `_shared/pre-flight-protocol.md` regardless of orchestration."

(User decides when to make this CLAUDE.md edit — not auto-applied.)
