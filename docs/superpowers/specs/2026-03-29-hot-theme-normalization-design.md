# Hot Theme Normalization Design

**Date:** 2026-03-29

**Goal:** Add a dedicated normalization layer between OpenClaw hot-theme input and the existing stock screening pipeline, so the system can map free-form theme semantics like `AI Agent`, `创新药出海`, or `锂价反弹` into stable local board concepts before screening.

## Context

The current OpenClaw-triggered extreme-strength screening flow already accepts external themes and persists stock-to-board memberships locally:

- [api/v1/endpoints/screening.py](E:/daily_stock_analysis/api/v1/endpoints/screening.py) accepts `POST /api/v1/screening/openclaw-theme-run`
- [src/services/theme_context_ingest_service.py](E:/daily_stock_analysis/src/services/theme_context_ingest_service.py) stores external hot-theme context
- [src/services/factor_service.py](E:/daily_stock_analysis/src/services/factor_service.py) enriches factor snapshots with board memberships and hot-theme metadata
- [src/services/hot_theme_factor_enricher.py](E:/daily_stock_analysis/src/services/hot_theme_factor_enricher.py) currently determines `is_hot_theme_stock`
- [src/services/theme_matching_service.py](E:/daily_stock_analysis/src/services/theme_matching_service.py) currently uses string similarity and keyword overlap against local board names
- [src/storage.py](E:/daily_stock_analysis/src/storage.py) now persists `board_master` and `instrument_board_membership`

We also confirmed from real runs that the current hard gate:

- `is_hot_theme_stock == true`

can reject all candidates even when the theme is directionally correct, because OpenClaw emits semantic topics while the local database stores normalized board labels.

Example mismatch:

- OpenClaw theme: `锂电池/锂矿`
- Local board names: `锂电池`, `锂电池概念`, `锂矿概念`

This is not a board-cache problem. It is a semantic normalization problem.

## Problem Statement

OpenClaw is good at discovering narrative themes from news and event catalysts, but it should not be forced to emit exact local board labels.

The current matching approach is too shallow for this job:

1. It assumes the incoming `theme.name` is already close to a local board name.
2. It uses only fuzzy string match and keyword overlap.
3. It treats board matching as a hard gate for candidate eligibility.
4. It has no explicit alias system, no semantic expansion, and no embedding-based recall.

As a result, semantically correct themes can fail to map to any board strongly enough, causing zero hot-theme matches even when relevant stocks clearly exist in the universe.

## Requirements

1. Keep OpenClaw free to send semantic themes, not only exact board names.
2. Normalize each external theme into one or more local standard boards before stock matching.
3. Prefer deterministic matches when possible, but support semantic similarity when wording differs.
4. Preserve explainability: every normalized board should record how it was matched.
5. Fit into the existing screening pipeline with minimal behavioral drift outside the hot-theme path.
6. Support future iterative improvement without requiring strategy changes for every new theme wording.

## Non-Goals

1. Do not replace OpenClaw as the theme discovery source.
2. Do not redesign the stock-to-board persistence model.
3. Do not require vector search on day one if a lower-cost staged rollout is chosen.
4. Do not change the downstream extreme-strength scoring model in this phase.

## Options Considered

### Option A: Force OpenClaw to emit exact board names

OpenClaw would be constrained to send only values from a local board whitelist.

Pros:

- Simplest runtime logic
- Easy to validate mechanically

Cons:

- Pushes local ontology burden into the external system
- Brittle against wording drift
- Loses semantic richness from news narratives
- Still difficult for compound themes and new narratives

### Option B: Add a local rule-based normalization layer

Use aliases, controlled keyword expansion, theme splitting, and board whitelists to normalize semantic themes into local boards.

Pros:

- Deterministic and explainable
- Low operational complexity
- Fast to implement and test

Cons:

- Requires ongoing alias maintenance
- Recall quality degrades for novel theme phrasings

### Option C: Add a staged semantic normalization layer

Use a layered approach:

1. deterministic alias/rule matching
2. keyword and board candidate recall
3. optional embedding-based rerank

Pros:

- Best balance of precision, recall, and explainability
- Supports semantic topics without requiring exact board names
- Lets us roll out incrementally

Cons:

- More moving parts than a pure rules engine
- Requires a lightweight embedding/index strategy if semantic rerank is enabled

## Recommendation

Use **Option C**.

The system should own the transformation from:

- external semantic theme

to:

- local normalized board set

This keeps OpenClaw focused on theme discovery while preserving control, explainability, and iteration speed inside our own codebase.

## Proposed Architecture

### 1. Raw Theme Layer

This remains the existing OpenClaw input contract.

Input fields continue to look like:

- `theme.name`
- `theme.keywords`
- `theme.catalyst_summary`
- `theme.evidence`

No hard requirement that `theme.name` exactly equals a local board name.

### 2. Theme Normalization Layer

Add a dedicated service that converts a raw semantic theme into normalized local boards.

Suggested new service:

- `src/services/theme_normalization_service.py`

Responsibilities:

- split compound theme labels when needed
- apply alias and synonym rules
- recall candidate boards from local board vocabulary
- optionally rerank recalled boards semantically
- output final normalized board matches with confidence and evidence

### 3. Normalized Theme Context Layer

Instead of passing only raw external themes downstream, produce an enriched theme structure that carries both raw and normalized data.

Suggested normalized output shape:

```json
{
  "raw_theme": "锂价反弹",
  "normalized_label": "锂电产业链",
  "matched_boards": [
    "锂电池概念",
    "锂矿概念"
  ],
  "match_confidence": 0.91,
  "match_reasons": [
    "alias_hit",
    "keyword_overlap",
    "embedding_top1"
  ]
}
```

This structure should become part of the screening run context so results remain auditable.

### 4. Screening Consumption Layer

The hot-theme screening path should stop treating raw external theme names as the direct board-matching key.

Instead:

- stock boards are matched against `matched_boards`
- raw theme text remains for display, explanation, and traceability

This means the current `ThemeMatchingService` would evolve from:

- `raw theme text` -> `stock boards`

to:

- `normalized board set` -> `stock boards`

with raw theme semantics used only during normalization.

## Matching Pipeline

### Step 1: Theme Preprocessing

Normalize the incoming theme text before any matching:

- trim whitespace
- normalize punctuation
- split obvious compound labels like `半导体/芯片`
- deduplicate repeated concepts

Examples:

- `锂电池/锂矿` -> `锂电池`, `锂矿`
- `AI Agent/大模型` -> `AI Agent`, `大模型`
- `海南自贸港/免税` -> `海南自贸港`, `免税`

### Step 2: Alias and Synonym Resolution

Use a local alias dictionary to map common semantic themes to standard local boards or board families.

Suggested asset:

- `data/theme_aliases.json` or a dedicated repository/service table

Examples:

- `AI Agent` -> `AI智能体`
- `大模型` -> `AIGC概念`, `多模态AI`
- `创新药出海` -> `创新药`
- `算力芯片` -> `AI芯片`
- `锂价反弹` -> `锂矿概念`, `锂电池概念`

This should be the first and highest-confidence matching layer.

### Step 3: Candidate Board Recall

For themes not fully resolved by alias rules, recall candidate boards from the local vocabulary:

- `board_master.board_name`

Candidate recall signals:

- exact board-name hit
- substring / token overlap
- keyword overlap against board names and alias descriptions
- optional historical co-occurrence metadata later

Output:

- Top K candidate boards, for example `K = 10`

### Step 4: Semantic Rerank

Rerank candidate boards using richer semantic context:

- `theme.name`
- `theme.keywords`
- `theme.catalyst_summary`
- optional evidence titles

Preferred long-term method:

- embeddings on both theme text and board concept representations

Candidate board representations can be built from:

- board name
- alias list
- optional board description

Output:

- scored candidate boards
- final accepted normalized boards above confidence threshold

### Step 5: Final Normalization Decision

The service should output one of three outcomes:

1. `exact_or_high_confidence_match`
2. `weak_match`
3. `unresolved`

Only high-confidence matches should feed the hot-theme hard gate by default.

Weak matches can still be retained in the run context for analyst review.

## Data Model Additions

### Normalized Theme Result

Add normalized data alongside the existing external theme context.

Suggested fields inside screening run config snapshot:

- `normalized_themes`
- `normalized_boards`
- `normalization_version`

### Alias Vocabulary

Store a curated alias layer separate from board persistence.

Two acceptable starting approaches:

1. file-based JSON asset
2. database table if frequent updates are expected

Initial recommendation:

- file-based JSON for fast iteration and reviewability

Suggested fields per alias entry:

- `raw_alias`
- `normalized_label`
- `matched_boards`
- `priority`
- `notes`

### Board Concept Index

If semantic rerank is enabled, maintain a derived concept corpus from local boards:

- board name
- aliases
- optional category text

This does not need to mutate `board_master`; it can be built as a derived index.

## Integration Points

### OpenClaw Endpoint

[api/v1/endpoints/screening.py](E:/daily_stock_analysis/api/v1/endpoints/screening.py)

Current responsibility:

- accept raw themes
- build `OpenClawThemeContext`

New responsibility:

- keep accepting raw themes unchanged
- invoke normalization before screening begins, or defer to the task service

### Screening Task Service

[src/services/screening_task_service.py](E:/daily_stock_analysis/src/services/screening_task_service.py)

Recommended role:

- own the lifecycle of normalization for OpenClaw-triggered runs
- persist raw and normalized theme context together

### Factor Service

[src/services/factor_service.py](E:/daily_stock_analysis/src/services/factor_service.py)

Current role:

- enrich factor snapshots using stock boards plus raw theme context

Future role:

- enrich factor snapshots using stock boards plus normalized theme boards

### Theme Matching Service

[src/services/theme_matching_service.py](E:/daily_stock_analysis/src/services/theme_matching_service.py)

Current role:

- calculate direct match score from stock name and board names against raw theme wording

Future role:

- compare stock board memberships against normalized board candidates
- optionally remain as a secondary scoring helper instead of the first-line gate

## Explainability Requirements

Every normalized theme should be explainable in the final result payload.

Minimum explanation fields:

- raw theme input
- normalized board outputs
- confidence score
- match reasons
- whether the match came from alias, keyword, exact board hit, or semantic rerank

This is important for both debugging and user trust.

## Error Handling

1. If normalization fails completely:
   - preserve raw theme context
   - mark the theme as unresolved
   - do not silently fabricate a board match

2. If only weak matches are available:
   - store them separately
   - do not automatically treat them as hard-gate matches unless policy allows

3. If the semantic layer is unavailable:
   - fall back to deterministic alias and keyword matching
   - never block the entire run solely because semantic rerank is unavailable

## Rollout Strategy

### Phase A: Deterministic Normalization

Ship:

- theme splitting
- alias dictionary
- candidate board recall
- normalization result persistence

No vector search yet.

### Phase B: Semantic Rerank

Add:

- board concept representations
- embedding generation
- candidate rerank
- confidence threshold tuning

### Phase C: Policy Tuning

Tune:

- what qualifies as `is_hot_theme_stock`
- whether weak matches can be admitted to watchlists
- how normalized themes appear in result explanations

## Testing Strategy

1. Unit tests for normalization
   - compound theme splitting
   - alias resolution
   - unresolved theme behavior

2. Integration tests for screening
   - raw semantic theme produces normalized boards
   - normalized boards produce hot-theme matches where direct string match would have failed

3. Regression tests from real examples
   - `锂电池/锂矿`
   - `AI Agent/大模型`
   - `创新药出海`
   - `海南自贸港/免税`

4. Explainability tests
   - run snapshots contain raw and normalized theme data
   - detail views can show why a board was matched

## Open Questions

1. Should alias vocabulary live in a JSON asset first, or go straight into a managed table?
2. Which embedding provider should be used if Phase B starts?
3. Should one theme be allowed to normalize into multiple board families by default, or should we cap at Top 3?
4. Should unresolved themes be dropped entirely, or preserved for analyst review and telemetry?

## Recommendation Summary

OpenClaw should continue to send semantic themes.

The repository should add a local normalization layer that maps those themes into standard boards through:

1. deterministic alias and rule matching
2. candidate board recall
3. optional embedding-based semantic rerank

That is the cleanest boundary between external theme discovery and internal board-based stock screening.
