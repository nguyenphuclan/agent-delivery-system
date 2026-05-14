---
name: mapping-integrity-protocol
description: Auto-flag every cross-schema mapping where source and target field names diverge. Catches the "network_owner → org_id" class of bugs that hide in 40-file diffs. Used by implement (during code generation) and pr-description (review surface).
---

# Mapping Integrity Protocol

## Purpose

The most expensive bugs in AI-assisted code are wrong mappings. Names diverge between schemas (`network_owner_id` ↔ `organizationId`), AI infers semantic equivalence, gets it wrong, ships it. User reviews 40 files at a glance, doesn't notice the 1 line.

This protocol forces every mapping to be classified, scored, and surfaced according to risk. Divergent-name mappings can never hide.

## When to apply

Trigger this protocol whenever AI writes code that:
- Maps DTO ↔ Entity (`Map(source.X, target.Y)`)
- Maps Request ↔ Command (`new SomeCommand { Field = req.OtherField }`)
- Maps DB column ↔ property (EF Core `HasColumnName`, Dapper column attributes)
- Maps event payload ↔ handler input
- Maps API response ↔ FE model
- Reads from one schema and writes to another
- Migrates data across schemas

Don't trigger for:
- Same-name passthrough (`target.foo = source.foo`)
- Newly created field with no source (default values, computed)

## Mapping classification

Every mapping AI writes is classified into one of 5 tiers:

### Tier 0 — IDENTICAL (silent)
```
source.userId → target.userId
source.created_at → target.created_at
```
Names identical (or differ only in convention: snake_case vs camelCase). No flag. Confidence high.

### Tier 1 — CONVENTION DIFFERENCE (silent or low flag)
```
source.user_id → target.userId          (snake → camel)
source.UserID → target.userId           (Pascal → camel)
source.user-id → target.userId          (kebab → camel)
```
Pure naming convention differences. Detected via case-conversion. No flag unless the project has a known anti-pattern.

### Tier 2 — SYNONYM (low flag)
```
source.id → target.userId               (singular → typed)
source.timestamp → target.createdAt
source.amount → target.totalAmount
source.role → target.userRole
```
Same concept, slightly different naming. Often safe but worth noting. Add as a note in `mapping-integrity.yaml`, not surfaced in CRITICAL section.

### Tier 3 — SEMANTIC SIMILAR (MEDIUM flag — review-priorities IMPORTANT)
```
source.userId → target.ownerId          (user vs owner — usually equivalent but not always)
source.email → target.contactEmail      (could be different fields)
source.startDate → target.effectiveFrom (similar concept, different domain term)
```
Concepts are related but not identical. Flag in `review-priorities.md` IMPORTANT. AI must justify with evidence.

### Tier 4 — DIVERGENT (HIGH flag — review-priorities CRITICAL)
```
source.networkOwnerId → target.organizationId   ⚠️
source.legacyOwnerId → target.userId            ⚠️
source.parentId → target.tenantId               ⚠️
source.code → target.identifier                 ⚠️
```
Names suggest different domain concepts. **Always surface in CRITICAL.** AI must produce decision card with:
- evidence_for (why these are equivalent)
- evidence_against (why they might NOT be)
- alternative interpretation
- explicit "user_action_needed: confirm semantic equivalence"

### Tier 5 — TYPE COERCION (BLOCKER — G1 always)
```
source.userId (Guid) → target.userIdString (string)    ⚠️ always G1
source.amount (decimal) → target.amount (int)          ⚠️ always G1
source.optional? → target.required (nullable lost)     ⚠️ always G1
source.bigint → target.int                             ⚠️ always G1
```
Type changes that can lose data or change semantics. **Always block with G1 — user must explicitly approve.**

## Detection algorithm

When implementing a mapping, AI runs:

```
function classifyMapping(source_field_name, target_field_name, source_type, target_type):
    # Type coercion check
    if types_lossy(source_type, target_type):
        return TIER_5_TYPE_COERCION  # BLOCKER

    # Name similarity check
    src_normalized = normalize_case(source_field_name)
    tgt_normalized = normalize_case(target_field_name)

    if src_normalized == tgt_normalized:
        return TIER_0_IDENTICAL

    if pure_case_difference(source_field_name, target_field_name):
        return TIER_1_CONVENTION

    # Synonym check (fuzzy match — Levenshtein, common synonyms)
    if name_synonym(src_normalized, tgt_normalized):
        return TIER_2_SYNONYM

    # Semantic-similar check (shared root word, common pattern)
    if shared_root_word(src_normalized, tgt_normalized) or
       semantic_pattern_match(src_normalized, tgt_normalized):
        return TIER_3_SEMANTIC_SIMILAR

    # Otherwise — divergent
    return TIER_4_DIVERGENT  # always CRITICAL
```

### Synonym pairs (built-in, project-extendable)
```yaml
synonyms:
  - [id, identifier, key, code]            # Tier 2
  - [name, title, label]                   # Tier 2
  - [createdAt, created, timestamp, date]  # Tier 2
  - [updatedAt, modified, lastChanged]     # Tier 2
  - [userId, accountId, memberId]          # Tier 3 (semantic-similar — surface!)
  - [organization, company, tenant, org]   # Tier 3 (semantic-similar — surface!)
```

User can extend per project at `public-project-docs/<project>/mapping-synonyms.yaml`. AI reads this before classification.

## Output: `mapping-integrity.yaml`

Generated by `implement` after main run. Sibling of `implement-summary.md`.

```
{output}/tickets/<TICKET_ID>/mapping-integrity.yaml
```

```yaml
total_mappings: 47
tier_0_identical: 32
tier_1_convention: 9
tier_2_synonym: 4
tier_3_semantic: 1
tier_4_divergent: 1
tier_5_coercion: 0

critical_mappings:                       # tier 4 + 5 — go to review-priorities CRITICAL
  - id: M-1
    source: ContractorDto.networkOwnerId
    target: User.organizationId
    file: src/Application/Mappers/ContractorMapper.cs
    line: 42
    tier: 4 (divergent)
    confidence: low
    evidence_for:
      - "Both fields are Guid type"
      - "Comments in 1 sample file say 'org link via network owner'"
    evidence_against:
      - "User schema also has separate networkOwnerId field that's NULL here"
      - "Org service sets organizationId based on auth context, not domain logic"
    alternative: "Check if User.networkOwnerId should be the target instead"
    user_action_needed: "Confirm semantic equivalence — risk of data integrity bug"

important_mappings:                      # tier 3 — go to review-priorities IMPORTANT
  - id: M-2
    source: ContractorDto.contactEmail
    target: User.email
    tier: 3 (semantic_similar)
    confidence: medium
    note: "Likely same concept; sample files use them interchangeably"
```

## How `implement` consumes this protocol

During code generation:
1. For every mapping written, classify per tiers above.
2. If Tier 5 (type coercion) → STOP, raise G1 immediately.
3. If Tier 4 (divergent) → mark for CRITICAL surfacing; produce decision card.
4. If Tier 3 (semantic similar) → mark for IMPORTANT surfacing.
5. Tier 0-2 → log silently to mapping-integrity.yaml.

After implement run:
- Write mapping-integrity.yaml.
- Feed `critical_mappings` and `important_mappings` into review-priorities.md generation.

## How `pr-description` consumes this protocol

In PR description, include a section:

```markdown
## Mapping Review (auto-generated)

**Critical mappings — verify before merge:** 1
- ⚠️ ContractorDto.networkOwnerId → User.organizationId at ContractorMapper.cs:42
  Decision: AI inferred semantic equivalence (LOW confidence). Reviewer: please verify against User schema.

**Important mappings — review if time:** 1
- ContractorDto.contactEmail → User.email (semantic-similar names)

Total mappings: 47 (32 identical, 9 case-convention, 4 synonyms, ...)
Full report: mapping-integrity.yaml
```

## Override hooks

| Hook | Default | Purpose |
|------|---------|---------|
| `synonym_pairs_file` | built-in + `public-project-docs/<project>/mapping-synonyms.yaml` if exists | Project-specific synonyms reduce false-CRITICAL |
| `tier_4_always_block` | true | Make tier 4 G1 (not just CRITICAL) — for high-risk projects |
| `tier_3_to_critical` | false | Promote tier 3 to CRITICAL — paranoid mode |
| `levenshtein_threshold` | 3 | For synonym fuzzy match |

## Anti-patterns (do NOT do)

- ❌ Skip the protocol because "mapping is obvious". Run it always — that's the point.
- ❌ Tier 4 with confidence `high`. If you're tier 4, you can't be high — names diverge, that's evidence against.
- ❌ Burying CRITICAL mappings in a long list. Cap at 5 per implement run; if more, ticket scope is wrong.
- ❌ Auto-resolve Tier 5 by adding a cast. Always G1 to user.
- ❌ Manual mapping registry instead of synonym file. Synonyms must live in `mapping-synonyms.yaml` for transparency + extension.

## Telemetry

```yaml
mapping_integrity:
  total: 47
  by_tier: {0: 32, 1: 9, 2: 4, 3: 1, 4: 1, 5: 0}
  user_caught_bugs:
    - mapping_id: M-1
      was_correct: false      # user verified, found bug
      saved: "data integrity in production"
  user_acked_correct: 4
```

`/learn` insights:
- If user caught bug in CRITICAL → calibration good
- If user found bug in tier 0/1/2 → classifier missed → propose adding synonym
- If user always acks tier 4 as correct → maybe synonyms should be added so they become tier 2
