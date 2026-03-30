# Hot Theme Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local normalization layer that converts OpenClaw semantic hot themes into normalized local board concepts before the extreme-strength screening pipeline applies its hot-theme hard gate.

**Architecture:** Introduce a staged normalization flow between OpenClaw input and hot-theme stock matching. Phase 1 ships deterministic theme splitting, alias mapping, candidate board recall, and normalized theme persistence. Phase 2 adds optional embedding-based rerank on top of the same normalization contract. Downstream screening consumes normalized board outputs instead of raw theme wording.

**Tech Stack:** Python, FastAPI service layer, SQLAlchemy/SQLite, pytest, JSON vocabulary assets, optional embeddings in later phases

---

## File Map

### Existing OpenClaw ingestion and screening flow
- Modify: `api/v1/endpoints/screening.py`
- Modify: `src/services/screening_task_service.py`
- Modify: `src/services/factor_service.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/theme_matching_service.py`

### New normalization layer
- Create: `src/services/theme_normalization_service.py`
- Create: `src/services/board_candidate_recall_service.py`
- Optional later: `src/services/theme_semantic_rerank_service.py`

### Vocabulary assets
- Create: `data/theme_aliases.json`
- Optional later: `data/theme_board_concepts.json`

### Tests
- Create: `tests/test_theme_normalization_service.py`
- Create: `tests/test_board_candidate_recall_service.py`
- Modify: `tests/test_screening_api.py`
- Modify: `tests/test_screening_task_service_hot_theme.py`
- Modify: `tests/test_theme_matching_service.py`
- Optional later: `tests/test_theme_semantic_rerank_service.py`

### Docs
- Reference: `docs/superpowers/specs/2026-03-29-hot-theme-normalization-design.md`
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

## Constraints and Guardrails

- Use TDD for every behavior change: failing test first, then minimal implementation.
- Do not force OpenClaw to emit exact local board names.
- Keep the normalization contract additive: raw theme input must remain available for display and audit.
- Keep Phase 1 deterministic and explainable.
- Do not make embeddings a hard runtime dependency in the first implementation pass.
- Preserve screening fail-open behavior when semantic rerank is unavailable.
- Do not commit unless the human explicitly asks for it.

## Task 1: Define the Normalized Theme Contract

**Outcome:** The codebase has a single, explicit normalized-theme data shape that every downstream component can rely on.

**Files:**
- Modify: `src/services/theme_context_ingest_service.py`
- Modify: `src/services/screening_task_service.py`
- Create: `tests/test_screening_task_service_hot_theme.py`

- [ ] **Step 1: Write the failing contract test**

Cover:
- raw OpenClaw theme context remains preserved
- normalized theme payload can be stored in the screening run snapshot
- normalized themes include `matched_boards`, `match_confidence`, and `match_reasons`

Suggested test shape:

```python
def test_run_config_snapshot_includes_normalized_themes():
    snapshot = service._build_run_config_snapshot(...)
    normalized = snapshot["normalized_themes"][0]
    assert normalized["raw_theme"] == "AI Agent"
    assert normalized["matched_boards"] == ["AI智能体"]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python -m pytest tests/test_screening_task_service_hot_theme.py -q
```

Expected before the fix:
- no `normalized_themes` field exists yet

- [ ] **Step 3: Add the normalized-theme structure**

Add a normalized theme shape that includes:
- `raw_theme`
- `normalized_label`
- `matched_boards`
- `match_confidence`
- `match_reasons`
- optional `status` like `high_confidence`, `weak_match`, `unresolved`

- [ ] **Step 4: Update run snapshot assembly**

In `src/services/screening_task_service.py`, reserve a place for normalized theme outputs in `config_snapshot`, while keeping raw `theme_context` unchanged.

- [ ] **Step 5: Re-run tests and confirm green**

Run:

```bash
python -m pytest tests/test_screening_task_service_hot_theme.py -q
python -m py_compile src/services/screening_task_service.py src/services/theme_context_ingest_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- the system now has an explicit normalized-theme contract
- raw and normalized theme data can coexist in one run snapshot

## Task 2: Add Deterministic Theme Splitting and Alias Resolution

**Outcome:** Semantic theme phrases can be split and normalized through a curated alias vocabulary before any board recall logic runs.

**Files:**
- Create: `src/services/theme_normalization_service.py`
- Create: `data/theme_aliases.json`
- Create: `tests/test_theme_normalization_service.py`

- [ ] **Step 1: Write the failing normalization tests**

Cover:
- split compound themes like `锂电池/锂矿`
- exact alias resolution like `AI Agent` -> `AI智能体`
- alias resolution returning multiple boards like `锂价反弹` -> `锂矿概念`, `锂电池概念`
- unresolved themes stay unresolved instead of being force-matched

Suggested test shape:

```python
def test_normalize_theme_uses_alias_map_for_ai_agent():
    result = service.normalize_theme(raw_theme="AI Agent", keywords=["Agent"])
    assert result["matched_boards"] == ["AI智能体"]
    assert "alias_hit" in result["match_reasons"]
```

- [ ] **Step 2: Run the normalization tests and verify failure**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py -q
```

- [ ] **Step 3: Add the alias vocabulary asset**

Create `data/theme_aliases.json` with a minimal curated starter set, for example:
- `AI Agent`
- `大模型`
- `创新药出海`
- `锂价反弹`
- `海南自贸港`

Keep the format simple and reviewable.

- [ ] **Step 4: Implement deterministic normalization**

In `src/services/theme_normalization_service.py`, implement:
- text cleanup
- compound-theme splitting
- alias lookup
- normalized result assembly

- [ ] **Step 5: Re-run tests and confirm green**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py -q
python -m py_compile src/services/theme_normalization_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- the service can now turn semantic themes into deterministic normalized board outputs when aliases are known

## Task 3: Add Candidate Board Recall From Local Board Vocabulary

**Outcome:** Themes not fully resolved by aliases can still recall candidate boards from local `board_master` data.

**Files:**
- Create: `src/services/board_candidate_recall_service.py`
- Create: `tests/test_board_candidate_recall_service.py`
- Reference: `src/storage.py`

- [ ] **Step 1: Write the failing recall tests**

Cover:
- exact board-name hit
- substring and token overlap
- keyword-assisted recall
- top-K candidate ordering

Suggested test shape:

```python
def test_recall_candidates_prefers_exact_board_hit(db):
    candidates = service.recall_candidates(theme_name="创新药", keywords=["医药"])
    assert candidates[0]["board_name"] == "创新药"
```

- [ ] **Step 2: Run recall tests and verify failure**

Run:

```bash
python -m pytest tests/test_board_candidate_recall_service.py -q
```

- [ ] **Step 3: Implement local board recall**

In `src/services/board_candidate_recall_service.py`, add:
- board vocabulary loading from `board_master`
- candidate generation from board names
- keyword-aware scoring
- top-K return contract

- [ ] **Step 4: Keep recall deterministic**

Do not introduce embeddings yet.
Keep this pass limited to:
- exact hits
- substring hits
- keyword overlap
- lightweight score sorting

- [ ] **Step 5: Re-run recall tests**

Run:

```bash
python -m pytest tests/test_board_candidate_recall_service.py -q
python -m py_compile src/services/board_candidate_recall_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- themes can now produce candidate boards even when no alias exists

## Task 4: Compose the Full Phase-1 Normalization Pipeline

**Outcome:** The normalization service now combines splitting, alias resolution, and candidate recall into one stable contract for downstream screening.

**Files:**
- Modify: `src/services/theme_normalization_service.py`
- Modify: `tests/test_theme_normalization_service.py`

- [ ] **Step 1: Write the failing integration-style normalization tests**

Cover:
- alias-first behavior
- recall fallback behavior
- unresolved behavior
- confidence and match reasons are filled consistently

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py -q
```

- [ ] **Step 3: Implement pipeline composition**

Pipeline order:
1. preprocess and split
2. alias match
3. candidate recall fallback
4. normalized result assembly

- [ ] **Step 4: Add status classification**

Return one of:
- `high_confidence`
- `weak_match`
- `unresolved`

- [ ] **Step 5: Re-run tests**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py -q
python -m py_compile src/services/theme_normalization_service.py src/services/board_candidate_recall_service.py
```

- [ ] **Step 6: Checkpoint**

Record:
- a complete deterministic normalization layer now exists

## Task 5: Integrate Normalization Into OpenClaw Screening

**Outcome:** OpenClaw-triggered runs store normalized themes and use normalized board outputs in the hot-theme matching path.

**Files:**
- Modify: `api/v1/endpoints/screening.py`
- Modify: `src/services/screening_task_service.py`
- Modify: `src/services/factor_service.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/theme_matching_service.py`
- Modify: `tests/test_screening_api.py`
- Modify: `tests/test_theme_matching_service.py`

- [ ] **Step 1: Write the failing API and service integration tests**

Cover:
- OpenClaw request still accepts raw semantic themes
- screening run snapshot persists normalized theme results
- hot-theme matching uses normalized boards instead of raw composite theme names

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
python -m pytest tests/test_screening_api.py tests/test_theme_matching_service.py tests/test_screening_task_service_hot_theme.py -q
```

- [ ] **Step 3: Normalize theme context before screening**

In `api/v1/endpoints/screening.py` or `src/services/screening_task_service.py`, invoke the normalization service for OpenClaw-triggered runs.

- [ ] **Step 4: Pass normalized boards into the hot-theme path**

Update the enrichment path so `ThemeMatchingService` consumes normalized board candidates rather than raw theme strings as the primary match target.

- [ ] **Step 5: Preserve backward-compatible display fields**

Keep:
- raw theme names
- catalyst summaries
- evidence

These are still needed for detail views and auditability.

- [ ] **Step 6: Re-run tests**

Run:

```bash
python -m pytest tests/test_screening_api.py tests/test_theme_matching_service.py tests/test_screening_task_service_hot_theme.py -q
python -m py_compile api/v1/endpoints/screening.py src/services/screening_task_service.py src/services/factor_service.py src/services/hot_theme_factor_enricher.py src/services/theme_matching_service.py
```

- [ ] **Step 7: Checkpoint**

Record:
- OpenClaw can keep sending semantic themes
- the screening hard gate is now backed by normalized boards

## Task 6: Add Real-Example Regression Tests

**Outcome:** Real problematic themes that previously produced zero matches are now covered by repeatable tests.

**Files:**
- Modify: `tests/test_theme_normalization_service.py`
- Modify: `tests/test_screening_api.py`
- Optional: `tests/test_factor_service.py`

- [ ] **Step 1: Add regression cases from real themes**

Cover at least:
- `锂电池/锂矿`
- `AI Agent/大模型`
- `创新药/医药生物`
- `海南自贸港/免税`

- [ ] **Step 2: Run focused regression tests**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py tests/test_screening_api.py -q
```

- [ ] **Step 3: Verify the expected outputs**

Each regression should assert:
- normalization outputs plausible local boards
- no theme silently becomes unresolved when a known alias exists

- [ ] **Step 4: Checkpoint**

Record:
- the known real-world mismatch patterns are now protected by tests

## Task 7: Prepare Phase-2 Semantic Rerank Hook

**Outcome:** The codebase is ready for embeddings later without making them mandatory now.

**Files:**
- Optional create: `src/services/theme_semantic_rerank_service.py`
- Optional create: `tests/test_theme_semantic_rerank_service.py`
- Modify: `src/services/theme_normalization_service.py`

- [ ] **Step 1: Define the rerank interface**

Add an injectable interface that accepts:
- raw theme text
- keywords
- catalyst summary
- candidate boards

and returns:
- rescored candidate boards

- [ ] **Step 2: Keep the default implementation disabled or no-op**

Do not require embeddings to ship Phase 1.

- [ ] **Step 3: Add a minimal contract test**

Run:

```bash
python -m pytest tests/test_theme_semantic_rerank_service.py -q
```

- [ ] **Step 4: Checkpoint**

Record:
- Phase 2 can be added without redesigning the Phase-1 normalization contract

## Task 8: Document and Verify

**Outcome:** The new normalization behavior is documented and verifiable.

**Files:**
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`
- Reference: `docs/superpowers/specs/2026-03-29-hot-theme-normalization-design.md`

- [ ] **Step 1: Update README**

Document:
- OpenClaw may send semantic themes
- the system normalizes them into local boards
- aliases and normalized boards drive hot-theme stock matching

- [ ] **Step 2: Update changelog**

Add an unreleased entry summarizing:
- the normalization layer
- deterministic alias mapping
- candidate board recall
- future semantic rerank hook

- [ ] **Step 3: Run the full focused verification set**

Run:

```bash
python -m pytest tests/test_theme_normalization_service.py tests/test_board_candidate_recall_service.py tests/test_screening_api.py tests/test_screening_task_service_hot_theme.py tests/test_theme_matching_service.py -q
python -m py_compile api/v1/endpoints/screening.py src/services/screening_task_service.py src/services/factor_service.py src/services/hot_theme_factor_enricher.py src/services/theme_matching_service.py src/services/theme_normalization_service.py src/services/board_candidate_recall_service.py
```

- [ ] **Step 4: Optional broader safety net**

Run if touched behavior crosses into wider screening logic:

```bash
python -m pytest tests/test_factor_service.py tests/test_strategy_screening_engine.py tests/test_screening_task_service.py -q
```

- [ ] **Step 5: Checkpoint**

Record:
- docs, tests, and screening flow are aligned

## Recommended Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 8
8. Task 7 when Phase 2 is ready

## Notes for the Implementer

- Phase 1 should already improve the current zero-match issue substantially without embeddings.
- Do not let semantic rerank block the first release.
- Prefer explicit explainability fields over opaque scoring whenever there is a trade-off.
- Keep raw OpenClaw theme inputs intact in all stored run snapshots.
