# Architecture

## 30-second tour

```
        ┌─────────────────┐
        │ projects.yaml   │   ← user config (gitignored)
        └────────┬────────┘
                 │
                 ▼
   ┌──────────────────────────┐
   │       scan-init          │   indexes all repos + db + domain
   │   (one-time / on drift)  │
   └────────────┬─────────────┘
                │ writes
                ▼
        ┌───────────────────┐
        │  _index.yaml      │   master registry of every artifact
        │  + per-area dirs  │   code/, db/, domain/, build/, conventions/
        └────────┬──────────┘
                 │ read by
                 ▼
   ┌────────────────────────────────────┐
   │            do-ticket               │
   │  branch → analyze → plan →         │
   │  implement → test → PR             │
   │                                    │
   │  domain-problem-solver             │
   │  (investigation, no ticket)        │
   └────────────────────────────────────┘
```

---

## Core idea: skills are pipelines, phases are contracts

Every skill is a sequence of **phases**. Each phase has:

- **Input contract** — what artifacts must exist + be fresh.
- **Output contract** — what artifact the phase produces, where it lands.
- **Readiness gate** — a flag in `_index.yaml` that flips to `ready` only when output passes validation.

A phase **refuses to run** if its input contract is unmet. The agent never improvises; it tells the user which prior phase needs to be re-run.

The contracts live in `skills/do-ticket/phase-contracts.yaml`. The format is normative — every skill compiles to this shape.

---

## Why a master index?

Without a registry, every skill rediscovers paths by string matching. That's where the agent burns context and where outputs drift apart.

`_index.yaml` answers three questions in O(1):

1. **Where does artifact X live?** — registered path, never inferred.
2. **Is it fresh?** — `produced_at` timestamp + `source_hash` from the inputs.
3. **Can phase N proceed?** — `phase_readiness.<phase>` boolean, computed from all inputs.

Skills resolve paths via `{project_docs}/...` placeholders, which the agent expands using `_index.yaml`. Hardcoded paths are a bug.

---

## Failure modes are first-class

When a phase fails (test red, lint fails, PR review rejects, JQL returns nothing), the agent doesn't improvise a fix. It matches the failure shape against `skills/do-ticket/failure-modes.yaml`, picks the registered pivot strategy, and surfaces the rationale to the user.

This is what lets `do-ticket` recover mid-pipeline without losing the original plan.

---

## Project-specific config is separated

The skill files reference logical roles (`shared_lib`, `api_task`, `frontend`). The mapping role → real repo path lives only in `_config/projects.yaml`. Two consequences:

- The skill files are portable. Same skills, different project, no edits.
- Replacing a repo (rename, split, merge) is a one-line config change.

---

## Shared protocols (the `_shared/` library)

14 small protocol files encode the parts of agent behavior that recur across skills:

- **Mapping** — `domain-mapping-protocol.md`, `mapping-integrity-protocol.md`
- **Decision-making** — `decision-confidence-protocol.md`, `risk-prioritization-protocol.md`, `hypothesis-protocol.md`
- **Clarification** — `clarification-protocol.md`, `requirements-clarification-protocol.md`
- **State / lifecycle** — `session-handoff-protocol.md`, `artifact-freshness-protocol.md`, `pre-flight-protocol.md`
- **Workflow** — `audit-apply-protocol.md`, `self-detailing-requirements-protocol.md`, `agent-docs-layout.md`, `project-config-protocol.md`

Skills cite these protocols by name rather than inlining the rules — change a rule once, every skill picks it up.

---

## See also

- [`docs/sample-outputs/_index.yaml.sample`](sample-outputs/_index.yaml.sample) — what a real master index looks like
- [`docs/sample-outputs/domain_index.yaml.sample`](sample-outputs/domain_index.yaml.sample) — what the domain index looks like
- [`skills/do-ticket/phase-contracts.yaml`](../skills/do-ticket/phase-contracts.yaml) — the actual contract definitions
- [`skills/do-ticket/failure-modes.yaml`](../skills/do-ticket/failure-modes.yaml) — registered failure pivots
