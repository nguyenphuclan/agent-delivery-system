---
name: artifact-freshness-protocol
description: Shared freshness algorithm for any artifact under public-project-docs/<project>/. Consumed by scan-init, scan-update, and knowledge-audit. Single source of truth for "is this artifact stale?"
---

# Artifact freshness protocol

## Inputs (from `public-project-docs/<project>/_index.yaml`)

```yaml
artifacts:
  <name>:
    path: <relative path to artifact file>
    fingerprint: <sha256 of artifact content>
    source_globs: ["**/*.cs", ...]   # surface this artifact derives from
    source_mtime_max: <iso>           # max mtime across source_globs at last write
    source_file_count: <int>          # file count across source_globs at last write
    schema_version: <int>
```

## Algorithm

Given an artifact record + current source tree:

```
1. If artifact file missing on disk           → MISSING
2. Recompute artifact_sha = sha256(artifact)
   If artifact_sha != stored fingerprint      → MANUAL_EDIT (user touched it)
3. Walk source_globs:
     current_max_mtime = max(mtime(f) for f in glob)
     current_count     = count(f in glob)
4. If current_max_mtime ≤ source_mtime_max    → FRESH
5. delta_count = abs(current_count - source_file_count) / source_file_count
6. If delta_count < 0.20 AND no new top-level dir under tracked roots
                                              → STALE_MINOR
7. Else                                       → STALE_SIGNIFICANT
```

## Status meanings

| Status | Meaning | Recommended action |
|---|---|---|
| `FRESH` | Source unchanged since last scan | none |
| `STALE_MINOR` | Source touched but structure intact (likely bug fixes) | optional `scan-update <name>`; safe to consume |
| `STALE_SIGNIFICANT` | Structural change (file count delta ≥20% or new top-level dir) | `scan-update <name>` recommended; consumer phases warn |
| `MANUAL_EDIT` | User edited artifact directly | preserve user edits; bump fingerprint to current; no auto-rescan |
| `MISSING` | Artifact file gone | `scan-init <name>` required before consumer phases run |

## Consumer responsibilities

| Consumer | Behavior on each status |
|---|---|
| `scan-update` | FRESH → skip. STALE_MINOR/SIGNIFICANT → refresh. MANUAL_EDIT → confirm with user before overwriting. MISSING → run scan-init. |
| `knowledge-audit` | FRESH → no op. STALE_* → emit `fingerprint-refresh` op (calls `scan-update`). MANUAL_EDIT → emit `fingerprint-rebase` op (recompute stored fingerprint to match current artifact). MISSING → emit `fingerprint-refresh` (full rescan). |
| do-ticket pre-flight | FRESH/STALE_MINOR → proceed. STALE_SIGNIFICANT/MISSING → block via G10, surface to user. |

## Implementation notes

- `mtime` reads use OS metadata, not git. Git-only changes do not bump mtime — that's intentional (git operations don't invalidate scans).
- `source_globs` must be set at artifact creation. If missing → treat artifact as `STALE_SIGNIFICANT` until scan-update writes it.
- Top-level dir detection: walk source_globs, compare set of immediate-parent dirs vs the set captured at last scan (stored in `_index.yaml.artifacts.<name>.source_top_dirs`).
- Bound walk cost: cap at 5000 file stat calls per artifact. If exceeded → return `STALE_SIGNIFICANT` without precise delta (assume worst case).

## Anti-patterns

- ❌ Use git diff to determine staleness — files modified outside the working tree (build outputs, generated code) won't appear, mtime always wins.
- ❌ Re-fingerprint the artifact every read — only on write or explicit refresh.
- ❌ Promote STALE_MINOR to STALE_SIGNIFICANT based on time elapsed alone. Time is not a structural signal.
