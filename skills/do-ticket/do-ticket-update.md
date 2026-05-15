---
name: do-ticket-update
description: Update cycle handler for do-ticket. Invoked when requirements change mid-ticket or QC finds missing cases after initial PR. Child skill — not user-facing.
---

# Update Cycle

Triggered by: `do-ticket <TICKET_ID> update`

Phase numbers below match the canonical enumeration in `do-ticket/SKILL.md` (§ "Canonical phase enumeration").

1. Ask: *(a) requirements changed in Jira, (b) QC found missing cases*
2. **Increment `update_count` first** (before writing any files).
3. Write delta to `update-implement-v<update_count>.md` — never overwrite a previous version. Preserves full history of what changed each round.
4. If (a): re-run phase 5 (`requirements`) → phase 6 (`analyze`) → show requirements diff → write `update-implement-v<N>.md` → re-run the implementation chain in update mode: phases 9 (`plan`) → 10 (`unit-tests`) → 11 (`implement`) → 12 (`regression`) → 13 (`completeness-audit`) → 14 (`env-gate`) → 15 (`api-test`) → 16 (`commit`) → 17 (`pre-push`) → 18 (`ci-check`) → 19 (`invariant-encoded`) → 21 (`pr-ready`, regenerate description).
5. If (b): ask user for missing cases → update `test-cases.md` (phase 8) → write `update-implement-v<N>.md` → re-run the implementation chain (same phase list as step 4).
6. Child skills (`implement-plan`, `implement`) receive the path `update-implement-v<N>.md` explicitly — they do not assume the filename.
7. Increment `pr_count` when user confirms PR raised.
