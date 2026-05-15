---
name: ticket-types
description: Ticket-type classification matrix for do-ticket. Each type produces a custom phase list — small bugs skip BA analysis, hotfixes skip qa-checklist, spikes skip implement entirely. Replaces the one-size-fits-all 15-phase pipeline.
---

# Ticket types — flow shape registry

## Why types exist

A 1-line typo fix and a cross-service migration cannot run the same pipeline. Forcing them through the same 15 phases either over-engineers small work or under-engineers risky work. Each `ticket_type` defines its own phase list, gates, and required artifacts.

## Classification protocol (phase 2 in do-ticket)

Run **after** branch is set up (phase 1) and Jira ticket fetched, **before** any analysis.

### Auto-classification heuristics

```
Inputs available:
- jira.issue_type ("Bug", "Task", "Story", "Spike", "Sub-task", "Epic")
- jira.labels (e.g., "hotfix", "doc-only", "refactor", "migration")
- jira.components
- ticket title + summary
- branch name (if user already used hotfix/ prefix)

Rules (first match wins):
1. branch starts with "${project.branch_conventions.hotfix_prefix}"  OR  jira.labels contains "hotfix"
   → ticket_type: hotfix  ⚠ redirect to hotfix-deploy skill (do not continue in do-ticket)

2. jira.issue_type == "Sub-task"
   → fetch parent ticket → inherit parent's ticket_type → confirm with user

3. jira.issue_type == "Spike"  OR  title matches /spike|investigate|research|POC/i
   → ticket_type: spike

4. jira.labels contains "doc-only"  OR  title matches /^docs?:|update readme|update changelog/i
   → ticket_type: doc-only

5. jira.labels contains "migration"  OR  title matches /db migration|schema change/i
   → ticket_type: migration-only

6. jira.labels contains "refactor"  OR  title starts with /^refactor:/i
   → ticket_type: refactor

7. jira.components limited to {"Frontend", "UI", "Web"}  AND  no api/db keywords in title
   → ticket_type: fe-only

8. jira.issue_type == "Bug"  AND  title contains "regression"
   → ticket_type: bugfix-regression

9. jira.issue_type == "Bug"
   → ticket_type: bugfix-small (default; user can override to bugfix-investigated)

10. fallback
   → ticket_type: crud-feature
```

After auto-classification, **always confirm with user**:

> "Auto-classified as `<type>` based on `<signal>`.
>  Phases will be: [list].
>  Confirm or override? (confirm / use <type>)"

Save chosen type to `ticket-context.yaml` → `ticket_type`.

### Manual override

User can pass type explicitly: `do-ticket PROJECT-1234 --type=refactor`. Skips auto-classification.

---

## Type → phase list

Phase keys reference do-ticket/SKILL.md. `*` = optional. `!` = type-specific gate.

### `crud-feature` (default — current full pipeline)

```
branch → rebase-check → requirements → analyze → invariant-scope → test-cases → plan
  → fe-impact-check → unit-tests → implement → regression → env-gate → api-test → commit
  → pre-push → ci-check → invariant-encoded → qa-checklist → pr-ready → pr-review
```

`fe-impact-check` auto-skips when plan touches no FE-consumed endpoint.

Risk profile baseline: medium. All standard gates apply.

---

### `bugfix-small`

```
branch → rebase-check → requirements (lite) → plan (lite) → unit-tests → implement
  → regression → commit → pre-push → ci-check → qa-checklist → pr-ready → pr-review
```

**Lite mode rules:**
- `requirements (lite)` — extract only the bug repro + expected behavior. No full BA analysis.
- `plan (lite)` — single-page plan: file + method + 1-line change description.
- Skip: `analyze`, `test-cases` (write-unit-tests covers it), `invariant-scope`/`invariant-encoded`, `api-test` (unless API was the bug surface), `env-gate`.

**Promotion:** if `implement` triggers FM-3X-SAME-ROOT or scope expands → upgrade to `bugfix-investigated`.

---

### `bugfix-investigated`

```
branch → rebase-check → requirements → investigate (domain-problem-solver)
  → analyze → test-cases → plan → fe-impact-check → unit-tests → implement → regression
  → env-gate → api-test → commit → pre-push → ci-check → qa-checklist → pr-ready → pr-review
```

Adds an explicit `investigate` phase before analyze. Output: `investigation-findings.md`. Used when root cause is unknown at ticket creation time. `fe-impact-check` auto-skips when plan touches no FE-consumed endpoint.

---

### `bugfix-regression`

Same phases as `bugfix-small`, but with **mandatory** new gates:
- `regression-test-first` — write a failing test that reproduces the regression BEFORE any code change.
- `git bisect hint` — if commit causing regression is unknown, suggest `git bisect` before debugging.

Risk profile: high (something that worked stopped working).

---

### `hotfix`

```
branch (${project.branch_conventions.hotfix_prefix}) → cherry-pick? → implement (surgical-patch strategy) → unit-test
  → regression → commit → pre-push → hotfix-deploy → pr-ready → pr-review
```

- `branch` MUST start with `${project.branch_conventions.hotfix_prefix}` prefix (see `_config/projects.yaml`).
- Skip: `analyze`, `test-cases`, `plan` (small enough to skip), `qa-checklist` (smoke test instead), `invariant-*`.
- `pr-ready` runs in parallel with deploy (do not block deploy on PR review).
- After hotfix lands → schedule a follow-up `crud-feature` ticket to backport fix to main + add full test coverage.

Risk profile: critical. Requires G3 confirmation before hotfix-deploy.

---

### `refactor`

```
branch → rebase-check → plan → behavior-diff-tests → implement → regression
  → commit → pre-push → ci-check → pr-ready → pr-review
```

- Skip: `requirements` (refactor goal is in ticket title), `analyze`, `qa-checklist` (no behavior change to QC).
- `behavior-diff-tests` — characterization tests that lock current behavior BEFORE refactor. Replaces `test-cases` + `unit-tests`.
- Strict invariant: no behavior change. CI must show all existing tests pass without modification.

---

### `spike` / investigation

```
branch (spike/) → requirements → investigate → spike-doc → done
```

- No `implement`, no commit of code (only docs). Output: `public-project-docs/<project>/spikes/<TICKET_ID>.md`.
- Spike ends with a recommendation that becomes a follow-up ticket of another type.
- Branch is informational; usually deleted after.

---

### `doc-only`

```
branch → doc-edit → commit → pr-ready → pr-review
```

- Skip everything in between.
- `doc-edit` — direct file edits to README/CHANGELOG/docs.
- `pre-push` still runs (secrets scan).

---

### `migration-only`

```
branch → plan → migration-script → dry-run-test → implement (apply migration)
  → regression → pre-push (with G3) → commit → pr-ready → pr-review
```

- `plan` MUST include rollback script + data risk analysis.
- `dry-run-test` — apply migration to throwaway DB clone, verify Down() works.
- G3 hard gate before `commit`: user confirms migration tested on staging.
- Skip: `qa-checklist` (DBA reviews instead), `api-test` (no API change).

Risk profile: critical. `migration-script` artifact lands in `public-project-docs/<project>/runbooks/`.

---

### `fe-only`

```
branch → rebase-check → requirements → analyze → test-cases → plan → unit-tests (Jest)
  → storybook-stories → implement → e2e-smoke → regression → commit
  → pre-push → ci-check → qa-checklist → pr-ready → pr-review
```

- `unit-tests` = Jest/Karma component specs.
- `storybook-stories` = mandatory for any visible UI change.
- `e2e-smoke` = manual or Playwright smoke test that the changed route still loads.
- Skip: `api-test`, `invariant-*` (no domain change).

---

## Promotion rules (mid-flow type changes)

A ticket may need to upgrade type mid-flow. Allowed transitions:

| From | To | Trigger |
|------|----|---------|
| `bugfix-small` | `bugfix-investigated` | FM-3X-SAME-ROOT or "I don't understand why this fails" |
| `bugfix-small` | `crud-feature` | Scope creeps: ticket grows beyond 1 file or 50 lines |
| `crud-feature` | `migration-only` | Discovered the only change needed is a schema change |
| `spike` | (any other type) | Spike concluded → user creates follow-up ticket |

When a promotion happens:
1. Update `ticket-context.yaml` → `ticket_type`.
2. Compute remaining phases per new type.
3. Skip phases already satisfied; run new ones.
4. Log to `run-telemetry.yaml`: `type_promotion: {from, to, reason}`.

## Demotion rules

Demotions are **not allowed** mid-flow (would skip already-completed gates with safety implications). If user wants to "simplify scope" mid-ticket, close ticket and create new one of correct type.

---

## Ticket type field reference

Used by Phase 2 step 5 to recompute `risk_profile` + `risk_factors` after any type change (auto-classify or user override).

| Type | Risk baseline | risk_factors | Mandatory gates | Skipped gates |
|------|---------------|--------------|-----------------|---------------|
| `crud-feature` | medium | [new-endpoint, db-change-possible, multi-layer] | all standard | none |
| `bugfix-small` | low | [targeted-fix, limited-surface] | secrets-scan, regression | analyze, qa-checklist gates |
| `bugfix-investigated` | medium | [unknown-root-cause, domain-deep-dive] | + investigate | none beyond bugfix-small |
| `bugfix-regression` | high | [working-broke, bisect-needed] | + regression-test-first | none |
| `hotfix` | critical | [prod-impact, time-pressure, minimal-test] | G3 deploy, secrets-scan | analyze, test-cases, qa-checklist |
| `refactor` | medium | [behavior-preservation, test-coverage-required] | behavior-diff-locked | qa-checklist |
| `spike` | low | [research-only, no-code-output] | none | implement, commit, pr |
| `doc-only` | low | [docs-only, no-logic-change] | secrets-scan | everything else |
| `migration-only` | critical | [schema-change, data-at-risk, rollback-required] | G3 migration, dry-run | qa-checklist, api-test |
| `fe-only` | medium | [ui-change, no-domain-change] | storybook + e2e-smoke | api-test, invariant |

---

## How do-ticket consumes this

After phase 1 (`branch`), do-ticket:
1. Reads `ticket-types.md` (this file).
2. Auto-classifies per heuristics.
3. Confirms with user.
4. Saves `ticket_type` to `ticket-context.yaml`.
5. Computes phase list from the type's section.
6. Runs phases in order, skipping any not in the list.
7. On promotion event, recomputes remaining phases.

The phase loop in SKILL.md is a generic walker — phase enumeration comes from this file.
