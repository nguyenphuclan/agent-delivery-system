# Setup — 4 steps

## Prerequisites

- An LLM coding agent harness that can read local skill files (Claude Code, Cursor, or similar).
- `git`, plus authenticated access to the repos you want indexed.
- (Optional, for `do-ticket`) Jira/Linear/GitHub Issues API access if you want ticket fetching.
- (Optional, for `scan-init`) read-only DB connection if you want schema indexing.

---

## Step 1 — Copy the config template

```bash
cp _config/projects.yaml.template _config/projects.yaml
```

`_config/projects.yaml` is **gitignored** — your credentials and repo paths never leave your machine.

## Step 2 — Fill in `_config/projects.yaml`

Open it and set values for the **active project**. Minimum required fields:

- `name` — short slug, e.g. `myapp`.
- `active` — boolean, set `true` on exactly one project block.
- `repos.<role>.path` — absolute paths to local clones of every repo the agent will touch.
- `output_dir` — absolute path where the agent should write all artifacts (`_index.yaml`, domain index, ticket folders, etc.). Keep it OUTSIDE the source repos.
- `ticket_system.type` and `ticket_system.prefix` — e.g. `jira` + `TICKET`.
- `db.connection_string` — optional but recommended for `scan-init`.

The template documents every field with comments. Anything not applicable to your project, delete the block entirely — the agent treats missing keys as "skip this concern".

## Step 3 — Run `scan-init`

In your agent harness, invoke:

> Run scan-init.

The agent will:

1. Read `_config/projects.yaml`.
2. Walk each repo, build per-area indexes (code, db, domain, build, conventions).
3. Write a master `{output_dir}/_index.yaml` that registers every artifact with `phase_readiness` flags.

This takes ~5–20 minutes on a medium project. The agent will stop and ask before touching anything destructive (writing to a new output directory is **not** destructive — overwriting an existing index **is**, so confirm prompts will fire there).

## Step 4 — Run `do-ticket` or `domain-problem-solver`

For a ticket:

> Run do-ticket TICKET-1234

For an investigation:

> I'm seeing X behavior on Y. Investigate.

The agent will route to `domain-problem-solver` automatically.

---

## Re-running scan-init

When the codebase shifts (new repos, large refactors, new tables), re-run `scan-init`. It detects what changed via the freshness protocol (`_shared/artifact-freshness-protocol.md`) and only re-scans the dirty shards — full re-index is rare.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Agent says "no active project in projects.yaml" | Set `active: true` on exactly one project block |
| Agent refuses to advance a phase | The previous phase's artifact is missing or stale — check `_index.yaml → phase_readiness` |
| `do-ticket` writes nothing | `output_dir` not writable, or the active project's `output_dir` points inside a source repo |
| Agent invents file paths | `_config/projects.yaml` is missing — copy template and fill in |
