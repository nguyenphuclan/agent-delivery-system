# Agent Delivery System

This repo is an agent **entry point**, not a library. Clone it, point an LLM coding agent at it, and the agent can:

1. **scan-init** — index a codebase into a structured domain index that all subsequent skills consume.
2. **do-ticket** — implement a Jira/Linear/GitHub ticket end-to-end: branch → analyze → plan → implement → test → PR.
3. **domain-problem-solver** — investigate open-ended problems (bugs, ambiguous requirements, performance, contract violations, "how does X work") without writing code.

The agent reads this file first, then routes to the correct skill based on the user's intent.

---

## Setup for a new project (one-time)

```bash
cp _config/projects.yaml.template _config/projects.yaml
# edit _config/projects.yaml — fill in: project name, repo paths, db connection, jira prefix, output path
```

Then:

1. Run **scan-init** — produces a master `_index.yaml` and per-area indexes under your configured output path.
2. Run **do-ticket TICKET-123** — the agent loads the index, picks a phase strategy by ticket type, and executes.
3. Run **domain-problem-solver** for investigation-style work that doesn't have a ticket yet.

See `SETUP.md` for the full step-by-step.

---

## Skill entry points

| Skill | Entry file | Use when |
|---|---|---|
| `scan-init`             | `skills/scan-init/SKILL.md`             | First time on a codebase, or when domain has drifted |
| `do-ticket`             | `skills/do-ticket/SKILL.md`             | A ticket is ready — implement it end-to-end |
| `domain-problem-solver` | `skills/domain-problem-solver/SKILL.md` | Open-ended question / bug / investigation, no ticket yet |

When invoked, **always read the skill's SKILL.md fully** before acting — phase contracts and gating live there.

---

## Shared protocols (`_shared/`)

All three skills compose from a small library of protocols. The agent must read these on demand:

| Protocol | When to read |
|---|---|
| `pre-flight-protocol.md`                   | Before starting ANY skill — verifies config + index freshness |
| `clarification-protocol.md`                | Ambiguous user input |
| `requirements-clarification-protocol.md`   | Ambiguous ticket requirements |
| `hypothesis-protocol.md`                   | Multiple plausible root causes |
| `domain-mapping-protocol.md`               | Mapping requirement → domain entities |
| `mapping-integrity-protocol.md`            | Validating mappings are complete + consistent |
| `decision-confidence-protocol.md`          | When to gate vs proceed |
| `session-handoff-protocol.md`              | Resuming work across sessions |
| `artifact-freshness-protocol.md`           | Is `_index.yaml` still valid? |
| `audit-apply-protocol.md`                  | Two-phase audit-then-apply changes |
| `self-detailing-requirements-protocol.md`  | Filling gaps in thin tickets |
| `risk-prioritization-protocol.md`          | Ranking observations / fixes |
| `project-config-protocol.md`               | Reading `_config/projects.yaml` correctly |
| `agent-docs-layout.md`                     | Where artifacts go in the output directory |

---

## Output structure

Every artifact the agent produces lives under the `output_dir` configured in `_config/projects.yaml`. The layout is defined in `_shared/agent-docs-layout.md`. **Do not write outputs anywhere else** — the index gates discovery, and off-tree files become invisible.

---

## Path resolution

The skill files reference `{project_docs}` as a placeholder. At runtime it resolves to `_config/projects.yaml → projects[active].output_dir`. If `projects.yaml` is missing, the agent **must stop** and prompt the user to copy the template — never invent a path.

---

## What this repo intentionally does NOT include

- Project-specific data (repo names, DB credentials, Jira prefixes) — those live in your local `_config/projects.yaml`, which is gitignored.
- A runtime / harness — bring your own (Claude Code, Cursor, etc).
- Auto-execution — every skill gates on user confirmation at phase boundaries.
