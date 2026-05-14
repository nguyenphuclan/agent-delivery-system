---
name: audit-apply-protocol
description: Contract for the `audit-apply` interface that knowledge-audit dispatches to per-store managers (doc-manager, vault, repo-steward, update-config, scan-update). Defines op shape, response shape, and idempotency rules.
---

# Audit-apply protocol

`knowledge-audit` is a planner + dispatcher. It detects drift across stores but does not edit files. Each per-store manager exposes an `audit-apply` interface that accepts a list of ops and applies them automatically.

## Invocation

```
<manager> audit-apply <ops.yaml>
```

`ops.yaml` is passed as a path (temp file under `<output>/_audits/_dispatch/<run-id>-<store>.yaml`).

## Op schema

```yaml
run_id: <iso-with-ms>
store: <public-project-docs|vault|skills-repo|settings|memory>
ops:
  - id: <run_id>-<n>
    op: <op-type>
    target: <relative path or registry key>
    payload: { ... }            # op-specific
    revert_cache_key: <sha>     # set if op is destructive — manager preserves prior state under this key
```

## Op types

Every manager must handle these where they apply to its store. Ops not relevant to the store are returned with `result: skipped, reason: not_applicable`.

| Op | Payload | What manager does |
|---|---|---|
| `index-add` | `{entry_path, summary}` | Add the leaf to the store's index file |
| `index-prune` | `{entry_key}` | Remove the entry from index (file already gone) |
| `fingerprint-refresh` | `{artifact_name}` | Trigger `scan-update <artifact>` (only `scan-update` itself implements this; other managers skip) |
| `fingerprint-rebase` | `{artifact_name, new_sha}` | Update fingerprint in `_index.yaml` to match current artifact (no rescan; user edited artifact directly) |
| `duplicate-canonicalize` | `{topic, canonical: {store, path}, others: [{store, path}]}` | If `store == this`: replace this store's copy with one-line pointer to canonical |
| `mis-located-move` | `{from: {store, path}, to: {store, path}}` | If `store == from.store`: write content to `to`, delete from `from`, leave forwarding pointer |
| `conflict-resolve` | `{topic, winner: {store, path}, losers: [{store, path}]}` | If `store` matches a loser: replace loser content with one-line pointer to winner |

## Response schema

Manager writes `<output>/_audits/_dispatch/<run-id>-<store>.result.yaml`:

```yaml
run_id: <same as input>
store: <same as input>
results:
  - id: <op id>
    result: ok | skipped | failed
    reason: <required when not ok>
    revert_cache_key: <sha if destructive op succeeded>
```

`knowledge-audit` reads the result file, aggregates into the audit log, deletes the dispatch + result temp files.

## Idempotency

Every op must be idempotent — re-applying the same op produces the same outcome:
- `index-add` on already-indexed entry → `result: skipped, reason: already_present`
- `index-prune` on missing entry → `result: skipped, reason: already_absent`
- `duplicate-canonicalize` where this store is already a pointer → `result: skipped, reason: already_pointer`

Reason: if a manager crashes mid-batch, audit retries the whole batch safely.

## Revert cache

For any destructive op (`duplicate-canonicalize`, `mis-located-move`, `conflict-resolve`):

1. Manager computes `sha = sha256(prior_content)`.
2. Manager writes prior content to `<output>/_audits/_revert-cache/<sha>.md`.
3. Manager returns `revert_cache_key: <sha>` in result.
4. Audit log captures the key alongside the op record.

`/knowledge-audit --revert <audit-id>` reads the log + revert cache to restore prior state. Cache TTL: 90 days.

## Cross-store ops

`duplicate-canonicalize`, `mis-located-move`, `conflict-resolve` involve two stores. Audit dispatches the **same op record to both** managers; each manager checks if it owns the canonical/winner side or a loser/source side, acts accordingly, returns its half. Audit verifies both halves succeeded before marking the op complete.

## Anti-patterns

- ❌ Manager performs edits beyond what the op record specifies. The protocol is closed — no opportunistic cleanups during audit-apply.
- ❌ Manager skips revert-cache write to "save time". Revertability is mandatory for destructive ops.
- ❌ Manager interprets payload fields it doesn't understand. Unknown fields → fail with `reason: unknown_payload_field`.
- ❌ Manager batches ops out of order. Apply in `ops[]` order — audit may have computed dependencies.

## Manager checklist (when adding audit-apply to a manager)

1. Add `audit-apply <path>` command to manager's SKILL.md command table.
2. Implement op handlers for op types relevant to the store (others → `skipped, not_applicable`).
3. Wire revert cache for destructive ops.
4. Ensure idempotency (re-runnable safely).
5. Write result file at the path audit expects.

---

## Sibling interface — `live-sync`

Managers of **private stores** also expose a per-write sync handler. See `_shared/live-sync-protocol.md` for the full protocol; the interface contract is:

```
<manager> live-sync <path> <op>
```

Where `op ∈ {create, edit, delete}`. Single path, single op — invoked synchronously after every agent Edit/Write/NotebookEdit on a path the manager owns.

| Op | Manager action |
|---|---|
| `create` | Add index entry. Compute fingerprint. Set `last_updated`. Recompute `phase_readiness` if applicable. |
| `edit` | Recompute fingerprint. Bump `last_updated`. If artifact has `source_globs`, recompute `source_mtime_max` + `source_file_count`. |
| `delete` | Remove index entry. Recompute `phase_readiness`. |

`live-sync` is a one-call interface — no temp files, no result yaml. Idempotent: re-applying same op = same outcome. Errors raise inline.

**audit-apply vs live-sync — when to use which:**

| Scenario | Interface |
|---|---|
| Single agent write just happened, must update one entry | `live-sync` (fast path) |
| Periodic batch from knowledge-audit, multiple ops, may include destructive cross-store ops | `audit-apply` (batch path with revert cache) |

A manager owning a private store implements **both**. Public-store managers (managing stores the agent doesn't write to directly, e.g. `repo-steward` against the GitHub origin) implement only `audit-apply`.
