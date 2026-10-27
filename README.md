# Agent Delivery System

A drop-in agent entry point for delivering software tickets end-to-end with an LLM coding agent (Claude Code, Cursor, or any IDE harness that supports custom skills).

Clone this repo, configure one YAML file, and an agent can:

- Index a multi-repo codebase into a structured domain map.
- Take a ticket from "Jira → branch → analyze → plan → code → test → PR" without losing context across phases.
- Investigate open-ended bugs and ambiguous requirements with explicit hypotheses, not vibes.

---

## The problem this solves

LLM coding agents are good at single-turn coding. They are bad at **multi-step delivery** because:

1. Each turn forgets what the previous turn decided.
2. Without an index, exploration burns context budget on the same files repeatedly.
3. Ad-hoc prompting produces inconsistent quality across tickets.
4. No clear handoff means tests, PR description, and implementation drift apart.

This repo encodes the parts that don't change across projects — phase contracts, artifact layout, mapping protocols, failure modes — as **skills** the agent reads, plus a thin **config file** for the parts that do change (repo names, DB connection, ticket prefix).

---

## Architecture (one paragraph)

Three top-level skills (`scan-init`, `do-ticket`, `domain-problem-solver`) compose from 14 shared protocols. Each skill is a phase pipeline; each phase produces a named artifact that the next phase reads. A master `_index.yaml` registers every artifact with explicit `phase_readiness` gates, so the agent can resume mid-pipeline, detect stale outputs, and refuse to advance when prerequisites are missing. Project-specific config (repo paths, JQL, DB) is isolated in `_config/projects.yaml`. Skills themselves are portable across projects.

See [`docs/architecture.md`](docs/architecture.md) for the full diagram.

---

## Quick start

```bash
git clone https://github.com/nguyenphuclan/agent-delivery-system
cd agent-delivery-system

cp _config/projects.yaml.template _config/projects.yaml
$EDITOR _config/projects.yaml
```

Then in your agent harness, point it at this repo and say:

> Run `scan-init` for my project.

Once the index lands:

> Run `do-ticket TICKET-1234`.

Full setup in [`SETUP.md`](SETUP.md). Agent entry rules in [`CLAUDE.md`](CLAUDE.md).

---

## What's in the box

| Path | What it is |
|---|---|
| `CLAUDE.md`                       | Agent entry point — read first |
| `SETUP.md`                        | Human setup guide |
| `skills/scan-init/`               | Phase 1 — codebase indexing |
| `skills/do-ticket/`               | Phase 2 — end-to-end ticket delivery |
| `skills/domain-problem-solver/`   | Investigation without a ticket |
| `skills/push-code/`               | Pre-push quality gate — the only sanctioned push path (do-ticket phase 17) |
| `skills/worktree-setup/`          | Parallel git worktrees for a multi-repo service stack, port-offset per worktree |
| `skills/spike/`                   | Timeboxed spike ticket — answer its own questions with re-runnable evidence, draft follow-ups, write no code |
| `skills/ticket-explain/`          | Plain-English share-doc that explains one ticket to teammates who will not build it |
| `_shared/`                        | Reusable protocol files (clarification, hypothesis, mapping, etc.) + `check-scope.py` |
| `_shared/tools/`                  | Small Python gate tools the skills call (below) |
| `_config/projects.yaml.template`  | Project config schema |
| `docs/`                           | Architecture + sample outputs |

### `_shared/tools/`

Python 3, stdlib only (PyYAML used when present). Each one turns a prose rule that kept being skipped into
a command with an exit code. Each SKILL.md keeps a manual check as the fallback when a tool cannot run.

| Tool | Purpose |
|---|---|
| `check_artifacts.py`        | Blocks a do-ticket gate (`pre-commit` / `pre-push` / `pr` / `done`) when a declared artifact is missing, hollow, or unparseable. PASS = "the record exists", not "the work is right" |
| `ticket_fingerprints.py`    | `check` finds artifacts that drifted since their phase ended; `refresh` re-fingerprints a deliberate edit, with a reason |
| `ticket_cost.py`            | $ cost of a ticket run (per part, main vs sub-agent), read from Claude Code transcripts on disk; no model call |
| `check_worktree.py`         | Is a worktree safe to build in: every repo fresh against the base branch, and which of its services are running |
| `check_flow_registries.py`  | Flow files, `flows/flow_index.yaml` and the `knowledge.md` FLOWS table agree |
| `check_skill_frontmatter.py`| Every `SKILL.md` has YAML frontmatter that parses (no BOM, has `name` + `description`) |
| `shared_store.py`           | Library: locked, atomic `append_lines` / `rewrite` for files several sessions write (e.g. `observations.md`) |

Repo check before a commit to this repo:

```bash
python _shared/tools/check_skill_frontmatter.py skills     # exit 0 = every skill loads
python -m unittest discover -s _shared/tools -p "test_*.py" # tools' own tests (unittest ones)
python _shared/tools/test_shared_store.py                   # these two run as plain scripts
python _shared/tools/test_ticket_cost.py
```

---

## Design principles

1. **One source of truth per artifact.** Skills resolve paths via `_index.yaml`, never hardcode.
2. **Phase contracts > implicit chains.** Each phase has a named input/output contract enforced by `phase-contracts.yaml`.
3. **Failure modes are explicit, not improvised.** `failure-modes.yaml` lists known pivots; the agent matches and acts.
4. **Generic algorithm, environment-separated.** Skill logic = portable; project data = `_config/projects.yaml`.
5. **Confirm before destructive shared-state actions.** PRs, force-pushes, prod data — never auto.

---

## Status

Built and used in production on a real multi-repo .NET + TypeScript microservice stack. The redactions you see in examples (`myapp-api-task`, `TICKET-XXXX`) are because the original deployment is private; the design itself is general-purpose.

---

## License

MIT — see `LICENSE`.
