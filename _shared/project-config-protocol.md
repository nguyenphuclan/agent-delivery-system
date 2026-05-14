# Project Config Protocol

Standard for how skills load project context (paths, repos, envs, conventions) without hardcoding company-specific values.

## Single source of truth

`_config/projects.yaml` — gitignored, contains real values.
`_config/projects.example.yaml` — committed, blank template.

Skills MUST NOT hardcode:
- Company/project names (e.g. `acme`)
- Repo names (e.g. `acme-task-api`)
- URLs or hostnames
- Jira ticket prefixes
- Branch naming patterns
- DB credentials or connection strings
- Filesystem paths to repos / output / worktrees

These all come from `_config/projects.yaml`.

## How a skill reads project context

At skill startup (or on first reference), the skill:

1. Reads `_config/projects.yaml`.
2. Picks the project named in `active:`.
3. Reads only the fields that skill needs.

Throughout this doc and in skill SKILL.md files, refer to fields with dot notation:
- `${project.jira_prefix}` → e.g. `ACME`
- `${project.paths.repos_root}` → e.g. `C:/Users/.../acme-repos`
- `${project.repos.api_task}` → e.g. `acme-task-api`
- `${project.environments.dev.api_base}` → e.g. `https://api.dev.acme.com/api-portal`
- `${project.hotfix.test.repo}` → e.g. `googlecloud-acme-workflow-test`

The `${project.X}` syntax is documentation-only — skills resolve it by reading the yaml at runtime, not via a templating engine.

## Missing config — graceful degradation

If `_config/projects.yaml` does not exist, or required fields are blank:
1. Tell the user: "Project config missing. Copy `_config/projects.example.yaml` to `_config/projects.yaml` and fill in: <fields needed>."
2. Stop. Do not guess values.

If a field is OPTIONAL and missing, the skill should run in degraded mode (e.g., skip an env-specific step) and note what was skipped.

## Switching projects

User says "switch to project <name>" → assistant edits `active:` in `_config/projects.yaml` to that name.

Skills must re-read on every session start (or on switch). Do not cache across sessions.

## Per-skill discovery

Each skill's SKILL.md should list the config fields it depends on, in a section like:

```
## Project config dependencies
Reads from `_config/projects.yaml`:
- ${project.jira_prefix}    — required
- ${project.repos.api_task} — required
- ${project.paths.output_root} — required
- ${project.environments.${env}.api_base} — required when env != local
```

This makes it grep-able which skills need which fields.

## Active env

Many skills reference `${project.active_env}` — the env currently being targeted (local/dev/test/acc/prod).

User can switch by saying "switch env to dev" → assistant edits `active_env:` under the active project.

## Schema versioning

Top-level `version:` field in projects.yaml tracks schema version. If a skill needs a newer schema, it checks `version:` and prompts user to update.

Current schema version: **1**.

## Tech-stack metadata

Each skill's `SKILL.md` frontmatter MAY declare a `tech_stack:` field — a YAML list of stack assumptions baked into the skill. **Missing field = stack-agnostic.**

**Vocabulary** (lowercase-hyphenated tokens):

- Language/runtime: `dotnet`, `csharp`, `node`, `python`, `go`, `java`, `rust`
- DB: `postgres`, `mysql`, `mongodb`, `snowflake`, `mssql`
- API tooling: `postman`, `insomnia`, `swagger`
- Browser/E2E: `playwright`, `cypress`, `selenium`
- CI/CD: `github-actions`, `gitlab-ci`, `azure-devops`, `argocd`, `helm`
- Git host: `github`, `gitlab`, `bitbucket`
- CLI: `gh-cli`, `glab-cli`
- Issue tracker: `jira`, `linear`, `github-issues`
- Container/deploy: `docker`, `k8s-yaml`
- Multi-repo: `git-worktree`, `multi-repo`
- Other: `bash`, `npm`, `atlassian-mcp`, `psql`

If a skill needs a token not listed, add it (lowercase-hyphenated) here and note it.

**Use case — portability check on company switch:** when the user moves to a project with a different stack, grep skills for `tech_stack:` matching the old company's tokens. Each match is a likely break point that needs refactoring or replacement before the skill works in the new environment.

Example:
```yaml
---
name: scan-api-docs
description: ...
tech_stack: [dotnet, csharp]
---
```
