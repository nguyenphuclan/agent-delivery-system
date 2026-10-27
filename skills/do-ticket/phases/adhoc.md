# do-ticket — ad-hoc phase escape hatch

Phase procedure for the ad-hoc phases any regular phase may insert. The router is `../SKILL.md`: trigger, state files, the phase list, the
generic phase loop, gates and rules. Inputs and outputs of each phase are in `../phase-contracts.yaml`.
A bare file name here is a do-ticket companion file in `~/.claude/skills/do-ticket/`.

The fixed phase list per `ticket_type` is the default path — **not a cage**. When the AI judges that the standard sequence is not the most effective path *for this specific situation*, it may insert an **ad-hoc phase** between two regular phases.

Ad-hoc phases are bounded — they preserve the spine while allowing exploration:

- **Allowed contexts:** mid-flow discovery suggests a quick check would change the plan; a domain question must be resolved before continuing; a similar feature should be read as reference.
- **Forbidden contexts:** skipping a regular phase (use type promotion instead); writing production code (must happen in `implement` phase only); modifying state of other tickets.

## Whitelisted ad-hoc phases

| Ad-hoc phase | Purpose | Output |
|--------------|---------|--------|
| `quick-api-poke` | Make 1 API call to validate an assumption before plan/implement | finding noted in `ticket-context.adhoc_findings[]` |
| `consult-dps` | Invoke domain-problem-solver mini-session for a specific question | `investigation-findings.md` (mini), reference in context |
| `read-reference-feature` | Read a similar feature already in codebase as a reference for plan/implement | reference paths added to `ticket-context.reference_files[]` |
| `verify-domain-rule` | Quick Track B lookup for one specific invariant | rule_id cited in `ticket-context.invariants_in_scope` |
| `quick-db-query` | One read-only DB query to confirm data shape (psql, LIMIT 10, no writes) | finding noted in `ticket-context.adhoc_findings[]` |
| `consult-runbook` | Look up a saved runbook for a recurring problem | runbook path noted, applied if relevant |

## Protocol (mandatory transparency)

When the AI decides to insert an ad-hoc phase, it MUST declare in chat:

```
[ad-hoc] Pausing <current-phase> at step <N>.
Inserting <ad-hoc-phase> because <one-line reason>.
Will resume <current-phase> with new context.
Estimated time: <e.g., 2 min>.
```

Then run the ad-hoc phase. When done:

```
[ad-hoc complete] <ad-hoc-phase> finished.
Findings: <one-line>.
Resuming <current-phase>.
```

Append to `ticket-state.yaml.adhoc_phases[]` and `run-telemetry.yaml.adhoc_phases[]`:

```yaml
adhoc_phases:
  - id: quick-api-poke
    inserted_during: plan
    inserted_at_step: "validating field name on GET /tasks/<id>"
    reason: "Plan assumed field 'completionDate' but API may use 'finishedAt'"
    started: 2026-05-02T11:00:00
    duration_seconds: 90
    outcome: "Field is 'finishedAt'. Plan corrected before write."
    affected_phase_outputs: [plan.md]
```

## Hard rules

- Ad-hoc phase MUST NOT bypass `secrets-scan`, `pre-push`, `commit` user gate, or any G3/G7 gate.
- Ad-hoc phase MUST NOT write code (no edits to source). For code-writing exploration, escalate to a `quick-db-query` or `read-reference-feature` instead, then return to the proper phase.
- Maximum 3 ad-hoc phases per regular phase. After that → likely the type/strategy is wrong; switch instead.
- Each ad-hoc phase logged to telemetry. /learn detects patterns: if same ad-hoc fires often during the same regular phase → propose making it part of the regular phase.

## Why this exists

Without an escape hatch, the AI either rigidly follows the wrong path (waste) or hacks around the structure invisibly (untrustworthy). The escape hatch is bounded freedom: the AI can deviate, but must declare why and log the deviation for review.
