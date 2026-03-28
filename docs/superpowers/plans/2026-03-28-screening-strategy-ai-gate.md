# Screening Strategy AI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the screening page's current generic AI second-pass with a page-scoped strategy AI gate that evaluates one active strategy per candidate, returns structured `buy/watch/reject` decisions, and surfaces them in the existing screening UI.

**Architecture:** Keep the existing screening run pipeline, but split the AI second-pass away from the legacy single-stock analyzer. `ScreeningTaskService` should resolve one `active_strategy`, build a strategy-specific evidence package and news digest, call a dedicated AI gate service, normalize the result into a stable contract, persist it with the candidate, and expose a compact display model to the screening page. The first implementation slice should fully support `bottom_divergence_double_breakout`, while other strategies degrade safely to `skipped` until their `ai_gate` assets are added.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy, YAML strategy assets, React, TypeScript, Vitest, pytest

---

## File Map

### Strategy assets and domain models
- Modify: `strategies/bottom_divergence_double_breakout.yaml`
- Modify: `strategies/ma100_low123_combined.yaml`
- Modify: `strategies/ma100_60min_combined.yaml`
- Modify: `strategies/extreme_strength_combo.yaml` or the actual active extreme-strength strategy file used by the screening page
- Create: `src/schemas/screening_ai_gate.py`
- Create: `src/services/screening_ai_gate_registry.py`

### Factor snapshot and evidence builders
- Modify: `src/services/factor_service.py`
- Create: `src/services/screening_ai_gate_resolver.py`
- Create: `src/services/screening_ai_gate_evidence_builder.py`
- Create: `src/services/screening_ai_gate_news_builder.py`
- Reference: `src/indicators/bottom_divergence_breakout_detector.py`
- Reference: `src/search_service.py`

### AI gate orchestration
- Create: `src/services/screening_ai_gate_prompt_builder.py`
- Create: `src/services/screening_ai_gate_service.py`
- Modify: `src/services/screening_task_service.py`
- Optional modify: `src/services/candidate_analysis_service.py` only if the old page-facing AI hook must be bypassed explicitly

### Persistence and API
- Modify: `src/storage.py`
- Modify: `api/v1/schemas/screening.py`
- Optional modify: `api/v1/endpoints/screening.py` if response shaping or detail endpoints need explicit mapping

### Web page integration
- Modify: `apps/dsa-web/src/types/screening.ts`
- Modify: `apps/dsa-web/src/stores/screeningStore.ts`
- Modify: `apps/dsa-web/src/components/screening/ScreeningCandidateTable.tsx`
- Modify: `apps/dsa-web/src/components/screening/CandidateDetailDrawer.tsx`
- Optional create: `apps/dsa-web/src/components/screening/aiGateFormatters.ts`

### Tests
- Create: `tests/test_screening_ai_gate_registry.py`
- Create: `tests/test_screening_ai_gate_resolver.py`
- Create: `tests/test_screening_ai_gate_evidence_builder.py`
- Create: `tests/test_screening_ai_gate_prompt_builder.py`
- Create: `tests/test_screening_ai_gate_service.py`
- Modify: `tests/test_factor_service_bottom_divergence.py`
- Modify: `tests/test_screening_task_service.py`
- Modify: `tests/test_screening_api.py`
- Modify: `apps/dsa-web/src/components/screening/__tests__/ScreeningCandidateTable.test.tsx`
- Modify: `apps/dsa-web/src/components/screening/__tests__/CandidateDetailDrawer.test.tsx`
- Optional modify: `apps/dsa-web/src/stores/__tests__/screeningStore.test.ts`

### Docs
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`

## Constraints and Guardrails

- Do not reuse `src/analyzer.py` or the generic single-stock dashboard prompt for the screening page AI gate.
- Keep the implementation page-scoped: the new AI gate should only affect the screening page path that flows through `ScreeningTaskService`.
- Preserve backward compatibility where practical by appending new candidate fields instead of renaming or removing existing `ai_summary`/`ai_operation_advice` immediately.
- Follow TDD for each behavior change: add or extend a failing test first, then implement the minimal code to pass it.
- Prefer deterministic backend decisions for strategy selection, stage mapping, and hard vetoes; the model should explain and refine, not invent structure.
- Unsupported strategies in phase 1 must degrade to `ai_status="skipped"` with a clear reason rather than falling back to the old generic analyzer.
- Do not commit unless the human explicitly asks for it. Replace commit steps with checkpoint steps.
- Because this changes user-visible screening output, update `README.md` and `docs/CHANGELOG.md` before closing the work.

## Task 1: Define Strategy AI Gate Assets and Registry

**Outcome:** Strategy YAML files can declare `ai_gate` metadata, and backend code can load and validate a single page-scoped AI gate config per strategy.

**Files:**
- Modify: `strategies/bottom_divergence_double_breakout.yaml`
- Modify: `strategies/ma100_low123_combined.yaml`
- Modify: `strategies/ma100_60min_combined.yaml`
- Modify: `strategies/extreme_strength_combo.yaml` or the actual active extreme-strength strategy file
- Create: `src/schemas/screening_ai_gate.py`
- Create: `src/services/screening_ai_gate_registry.py`
- Create: `tests/test_screening_ai_gate_registry.py`

- [ ] **Step 1: Write failing tests for YAML loading and fallback behavior**

Add coverage for:
- `bottom_divergence_double_breakout` loads a complete `ai_gate` block
- strategies without a complete page-scoped AI definition return `None` or an explicit unsupported marker
- registry exposes `ai_priority`, `version`, `stage_definitions`, and `payload_fields`

Suggested test shape:

```python
def test_registry_loads_bottom_divergence_ai_gate():
    registry = ScreeningAiGateRegistry.from_builtin_strategies()
    config = registry.get("bottom_divergence_double_breakout")
    assert config is not None
    assert config.version == "v1"
    assert config.ai_priority >= 1
    assert "confirm_entry_window" in config.stage_definitions
```

- [ ] **Step 2: Run the focused registry test and confirm it fails**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_registry.py -q
```

Expected before the fix:
- no `screening_ai_gate` schema or registry exists
- strategy YAML files do not expose page-scoped AI gate metadata yet

- [ ] **Step 3: Implement the registry and add phase-1 strategy assets**

Implementation requirements:
- add a dedicated `ai_gate` block under strategy assets rather than overloading existing `instructions`
- fully define `bottom_divergence_double_breakout`
- add minimal phase-1 metadata for the other screening-page strategies so the resolver can identify whether each strategy is supported or currently skipped

Suggested schema outline:

```python
class ScreeningAiGateConfig(BaseModel):
    strategy_name: str
    version: str
    ai_priority: int
    supported: bool = True
    playbook: dict
    stage_definitions: dict
    hard_veto_rules: list[str]
    news_focus: list[str]
    payload_fields: list[str]
```

- [ ] **Step 4: Verify registry behavior**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_registry.py -q
python -m py_compile src/schemas/screening_ai_gate.py src/services/screening_ai_gate_registry.py
```

Expected:
- bottom divergence AI gate config loads correctly
- unsupported or incomplete strategies are handled explicitly
- no syntax errors

- [ ] **Step 5: Checkpoint**

Record:
- which strategies are phase-1 ready
- which strategies intentionally degrade to `skipped`
- where `ai_gate` config now lives in YAML

## Task 2: Enrich Bottom-Divergence Factor Snapshot for AI Evidence

**Outcome:** The screening factor snapshot contains the raw bottom-divergence evidence needed by the page-scoped AI gate, without forcing the model to re-derive chart structure from prose.

**Files:**
- Modify: `src/services/factor_service.py`
- Modify: `tests/test_factor_service_bottom_divergence.py`
- Create or modify: `tests/test_screening_ai_gate_evidence_builder.py`
- Reference: `src/indicators/bottom_divergence_breakout_detector.py`

- [ ] **Step 1: Write failing tests for raw evidence persistence**

Cover these cases:
- factor snapshot includes A/B lows, MACD lows, rebound high, horizontal resistance, and downtrend-line data
- factor snapshot preserves breakout booleans and signal strength
- phase-1 unsupported strategies still keep their current factor behavior unchanged

Suggested test shape:

```python
def test_bottom_divergence_snapshot_exposes_raw_ai_gate_evidence():
    snapshot = service.build_factor_snapshot(universe_df=df, trade_date=trade_date)
    row = snapshot.iloc[0].to_dict()
    assert row["bottom_divergence_state"] in {"structure_ready", "confirmed", "late_or_weak"}
    assert row["bottom_divergence_price_low_a"]["price"] is not None
    assert row["bottom_divergence_horizontal_resistance"] is not None
```

- [ ] **Step 2: Run focused factor tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_factor_service_bottom_divergence.py tests/test_screening_ai_gate_evidence_builder.py -q
```

Expected before the fix:
- factor snapshots only contain the summarized fields
- raw detector evidence is missing from the row

- [ ] **Step 3: Extend factor snapshot output minimally**

Implementation requirements:
- keep the current summary fields
- append raw evidence fields needed by the AI gate
- avoid copying every detector field blindly; only persist the fields that support `strategy_payload`, stage mapping, or deterministic hard vetoes

Suggested output fields:

```python
{
    "bottom_divergence_price_low_a": result.get("price_low_a"),
    "bottom_divergence_price_low_b": result.get("price_low_b"),
    "bottom_divergence_macd_low_a": result.get("macd_low_a"),
    "bottom_divergence_macd_low_b": result.get("macd_low_b"),
    "bottom_divergence_rebound_high": result.get("rebound_high"),
    "bottom_divergence_horizontal_resistance": result.get("horizontal_resistance"),
    "bottom_divergence_downtrend_line": result.get("downtrend_line"),
    "bottom_divergence_rejection_reason": result.get("rejection_reason"),
}
```

- [ ] **Step 4: Verify factor snapshot compatibility**

Run:

```bash
python -m pytest tests/test_factor_service_bottom_divergence.py tests/test_factor_service.py tests/test_screening_ai_gate_evidence_builder.py -q
python -m py_compile src/services/factor_service.py
```

Expected:
- bottom-divergence rows now carry raw evidence
- existing screening factor tests still pass

- [ ] **Step 5: Checkpoint**

Record:
- exact raw fields added to `factor_snapshot`
- any fields intentionally left out until later strategies need them

## Task 3: Build Active Strategy Resolution and Evidence/News Builders

**Outcome:** The screening page can deterministically choose one `active_strategy` per candidate and build a compact evidence package and news digest tailored to that strategy.

**Files:**
- Create: `src/services/screening_ai_gate_resolver.py`
- Create: `src/services/screening_ai_gate_evidence_builder.py`
- Create: `src/services/screening_ai_gate_news_builder.py`
- Create: `tests/test_screening_ai_gate_resolver.py`
- Create: `tests/test_screening_ai_gate_evidence_builder.py`
- Optional modify: `tests/test_screening_task_service.py`
- Reference: `src/search_service.py`

- [ ] **Step 1: Write failing tests for active-strategy resolution**

Cover:
- one selected strategy and one hit -> that strategy wins
- multiple hits -> resolver picks by `ai_priority`, then stronger deterministic signal
- unsupported strategy configs -> `skipped` decision path

Suggested test shape:

```python
def test_resolver_prefers_highest_priority_supported_strategy():
    active, alternatives = resolver.resolve(
        matched_strategies=["ma100_low123_combined", "bottom_divergence_double_breakout"],
        factor_snapshot={"bottom_divergence_signal_strength": 0.92},
    )
    assert active.strategy_name == "bottom_divergence_double_breakout"
    assert "ma100_low123_combined" in alternatives
```

- [ ] **Step 2: Write failing tests for evidence and news digest shape**

Cover:
- bottom-divergence evidence package only includes relevant fields
- missing key evidence marks the package insufficient
- news digest separates structural positives, structural negatives, and ignored noise

Suggested test shape:

```python
def test_bottom_divergence_evidence_builder_marks_missing_anchor_points():
    evidence = builder.build(candidate, strategy_config)
    assert evidence.data_quality == "insufficient"
    assert "bottom_divergence_rebound_high" in evidence.missing_fields
```

- [ ] **Step 3: Run the focused builder tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_resolver.py tests/test_screening_ai_gate_evidence_builder.py -q
```

Expected before the fix:
- no resolver exists
- no strategy-specific evidence package or digest builder exists

- [ ] **Step 4: Implement deterministic resolution and compact evidence/news builders**

Implementation requirements:
- resolve `active_strategy` before any LLM call
- construct a strategy-specific package instead of passing through the whole `factor_snapshot`
- keep news digest short and typed; avoid feeding raw long-form news blocks

Suggested builder output:

```python
{
    "candidate_meta": {...},
    "strategy_snapshot": {...},
    "strategy_raw_evidence": {...},
    "market_filter_snapshot": {...},
    "news_digest": {
        "structural_positive": [...],
        "structural_negative": [...],
        "ignored_noise": [...],
    },
}
```

- [ ] **Step 5: Verify builder behavior**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_resolver.py tests/test_screening_ai_gate_evidence_builder.py tests/test_screening_task_service.py -q
python -m py_compile src/services/screening_ai_gate_resolver.py src/services/screening_ai_gate_evidence_builder.py src/services/screening_ai_gate_news_builder.py
```

Expected:
- exactly one `active_strategy` is chosen
- evidence packages are strategy-specific and small
- missing evidence is explicit instead of silently ignored

- [ ] **Step 6: Checkpoint**

Record:
- resolution precedence
- evidence fields for bottom divergence
- skip behavior for unsupported strategies

## Task 4: Implement the Page-Scoped AI Gate Prompt Builder and Service

**Outcome:** The screening page uses a dedicated AI gate service that produces normalized `AiGateDecision` results without calling the legacy single-stock analyzer prompt.

**Files:**
- Create: `src/services/screening_ai_gate_prompt_builder.py`
- Create: `src/services/screening_ai_gate_service.py`
- Modify: `src/services/screening_task_service.py`
- Create: `tests/test_screening_ai_gate_prompt_builder.py`
- Create: `tests/test_screening_ai_gate_service.py`
- Modify: `tests/test_screening_task_service.py`

- [ ] **Step 1: Write failing tests for prompt shape and normalized output**

Cover:
- prompt includes only system rules, strategy playbook, candidate evidence, and output contract
- prompt omits old dashboard instructions and generic analyzer sections
- service normalizes invalid or partial model output into `ai_status=failed` or `insufficient_data`
- `buy` is blocked if required evidence is missing

Suggested test shape:

```python
def test_prompt_builder_uses_strategy_gate_sections_only():
    prompt = builder.build(config, evidence)
    assert "dashboard" not in prompt.user_content
    assert "trend_prediction" not in prompt.user_content
    assert "stage_definitions" in prompt.user_content
```

- [ ] **Step 2: Run focused AI gate tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_prompt_builder.py tests/test_screening_ai_gate_service.py tests/test_screening_task_service.py -q
```

Expected before the fix:
- no page-scoped prompt builder exists
- screening task service still routes into the old AI enrichment flow

- [ ] **Step 3: Implement the AI gate prompt builder and service**

Implementation requirements:
- use a small system prompt with hard rules only
- inject one strategy playbook only
- require a stable JSON contract
- normalize model output before persistence
- degrade gracefully instead of falling back to the old analyzer

Suggested normalization rule:

```python
if evidence.data_quality != "sufficient":
    decision.verdict = "watch"
    decision.ai_status = "insufficient_data"

if decision.risk_gate.hard_vetoes:
    decision.verdict = "reject"
```

- [ ] **Step 4: Replace screening-page AI enrichment in `ScreeningTaskService`**

Wire the `ai_enriching` stage so that it:
- resolves `active_strategy`
- builds evidence and news digest
- calls `ScreeningAiGateService`
- stores normalized gate results on each candidate payload
- does not invoke the old generic single-stock analysis path for the screening page

- [ ] **Step 5: Verify the new AI path**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_prompt_builder.py tests/test_screening_ai_gate_service.py tests/test_screening_task_service.py tests/test_screening_api.py -q
python -m py_compile src/services/screening_ai_gate_prompt_builder.py src/services/screening_ai_gate_service.py src/services/screening_task_service.py
```

Expected:
- screening runs produce normalized gate results
- no legacy analyzer prompt is used for page-scoped second-pass evaluation
- unsupported strategies are marked `skipped`

- [ ] **Step 6: Checkpoint**

Record:
- exact fallback and veto semantics
- whether any old AI code path remains reachable from the screening page

## Task 5: Persist and Expose the AI Gate Result Through Storage and API

**Outcome:** Screening candidates persist the full AI gate decision for audit/refresh and expose a stable API contract plus a compact backward-compatible summary.

**Files:**
- Modify: `src/storage.py`
- Modify: `api/v1/schemas/screening.py`
- Optional modify: `api/v1/endpoints/screening.py`
- Modify: `tests/test_screening_api.py`
- Modify: `tests/test_screening_storage.py`

- [ ] **Step 1: Write failing tests for storage and schema expansion**

Cover:
- screening candidates persist `active_strategy`, `ai_status`, `verdict`, `stage_assessment`, `risk_gate`, and `strategy_payload`
- list and detail endpoints expose the new fields
- old `ai_summary` remains available as a compact compatibility field derived from `decision_summary`

Suggested test shape:

```python
def test_screening_candidate_detail_exposes_ai_gate_decision(client):
    response = client.get(f"/api/v1/screening/runs/{run_id}/candidates/{code}")
    payload = response.json()
    assert payload["verdict"] in {"buy", "watch", "reject"}
    assert payload["active_strategy"]["key"] == "bottom_divergence_double_breakout"
```

- [ ] **Step 2: Run focused storage and API tests**

Run:

```bash
python -m pytest tests/test_screening_storage.py tests/test_screening_api.py -q
```

Expected before the fix:
- storage has nowhere to persist the full AI gate contract
- API schema only exposes `ai_summary` and `ai_operation_advice`

- [ ] **Step 3: Add storage columns and response fields**

Implementation requirements:
- prefer JSON text columns for the structured gate result if that matches the existing storage pattern
- append new fields rather than remove old ones
- expose a compact list view and a fuller detail view

Suggested storage additions:

```python
ai_status = Column(String(32))
ai_gate_result_json = Column(Text)
active_strategy_key = Column(String(80))
ai_verdict = Column(String(16))
```

- [ ] **Step 4: Verify persistence and API compatibility**

Run:

```bash
python -m pytest tests/test_screening_storage.py tests/test_screening_api.py tests/test_screening_task_service.py -q
python -m py_compile src/storage.py api/v1/schemas/screening.py
```

Expected:
- new AI gate fields are persisted
- existing clients still receive `ai_summary`
- detail responses expose the structured contract

- [ ] **Step 5: Checkpoint**

Record:
- exact columns and JSON fields added
- compatibility story for old consumers of `ai_summary`

## Task 6: Update the Screening Page to Display the AI Gate Result

**Outcome:** The screening page shows the new strategy verdict, stage, and next action without exposing raw internal JSON, while detail drawers expose the richer gate decision.

**Files:**
- Modify: `apps/dsa-web/src/types/screening.ts`
- Modify: `apps/dsa-web/src/stores/screeningStore.ts`
- Modify: `apps/dsa-web/src/components/screening/ScreeningCandidateTable.tsx`
- Modify: `apps/dsa-web/src/components/screening/CandidateDetailDrawer.tsx`
- Optional create: `apps/dsa-web/src/components/screening/aiGateFormatters.ts`
- Modify: `apps/dsa-web/src/components/screening/__tests__/ScreeningCandidateTable.test.tsx`
- Modify: `apps/dsa-web/src/components/screening/__tests__/CandidateDetailDrawer.test.tsx`
- Optional modify: `apps/dsa-web/src/stores/__tests__/screeningStore.test.ts`

- [ ] **Step 1: Write failing UI tests for verdict and stage rendering**

Cover:
- candidate table shows verdict tag and active strategy
- detail drawer shows current stage, primary action, key hard risks, and watch levels
- unsupported or skipped AI gate results render a neutral fallback instead of broken UI

Suggested test shape:

```tsx
it('renders AI gate verdict and stage for a candidate', () => {
  render(<ScreeningCandidateTable candidates={[candidate]} ... />);
  expect(screen.getByText('观察')).toBeInTheDocument();
  expect(screen.getByText('结构待确认')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused web tests and confirm they fail**

Run:

```bash
cd apps/dsa-web
npm run test -- ScreeningCandidateTable CandidateDetailDrawer
```

Expected before the fix:
- current types do not expose `verdict`, `activeStrategy`, or `stageAssessment`
- UI still expects the old generic AI summary only

- [ ] **Step 3: Add the new types and minimal UI mapping**

Implementation requirements:
- add typed interfaces for the new AI gate result
- keep table display concise
- put richer evidence, stage, and risk data in the detail drawer
- do not dump raw JSON directly into the page

Suggested display mapping:

```ts
const verdictTag = candidate.aiGate?.verdict ?? 'skipped';
const stageLabel = candidate.aiGate?.stageAssessment?.stageLabel ?? '未评估';
const summary = candidate.aiGate?.decisionSummary ?? candidate.aiSummary ?? '暂无 AI 判关结果';
```

- [ ] **Step 4: Verify web behavior**

Run:

```bash
cd apps/dsa-web
npm run lint
npm run test -- ScreeningCandidateTable CandidateDetailDrawer
npm run build
```

Expected:
- list and detail screens render new AI gate results
- skipped/failed states degrade cleanly
- build succeeds

- [ ] **Step 5: Checkpoint**

Record:
- what appears in the table
- what appears only in the drawer
- how skipped/failed AI states are explained to the user

## Task 7: Update User-Facing Docs and Verification Notes

**Outcome:** Repo docs match the new screening page behavior and explain the phase-1 scope of the strategy AI gate.

**Files:**
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`
- Optional modify: `docs/superpowers/specs/2026-03-25-bottom-divergence-double-breakout-design.md` only if the implemented behavior diverges from the design assumptions

- [ ] **Step 1: Write the docs diff after behavior is stable**

Document:
- screening page now uses a page-scoped strategy AI gate
- phase-1 supported strategy or strategies
- `buy/watch/reject` and skipped/failure semantics
- any API response additions that are user-visible

- [ ] **Step 2: Verify docs accuracy against the implementation**

Check:
- file names
- endpoint names
- visible field names
- strategy names shown in the UI

- [ ] **Step 3: Run the final validation set**

Run:

```bash
python -m pytest tests/test_screening_ai_gate_registry.py tests/test_screening_ai_gate_resolver.py tests/test_screening_ai_gate_evidence_builder.py tests/test_screening_ai_gate_prompt_builder.py tests/test_screening_ai_gate_service.py tests/test_screening_task_service.py tests/test_screening_api.py tests/test_screening_storage.py -q
python -m py_compile src/services/factor_service.py src/services/screening_ai_gate_registry.py src/services/screening_ai_gate_resolver.py src/services/screening_ai_gate_evidence_builder.py src/services/screening_ai_gate_news_builder.py src/services/screening_ai_gate_prompt_builder.py src/services/screening_ai_gate_service.py src/services/screening_task_service.py src/storage.py api/v1/schemas/screening.py
cd apps/dsa-web
npm run lint
npm run build
```

Expected:
- backend tests pass
- no syntax errors
- web lint and build pass

- [ ] **Step 4: Checkpoint**

Record:
- final supported strategy list
- known gaps for non-phase-1 strategies
- rollback path: restore `ScreeningTaskService` AI stage to pre-gate behavior and remove new candidate fields if a release must be reverted

## Recommended Execution Order

1. Task 1: strategy assets and registry
2. Task 2: factor snapshot enrichment
3. Task 3: resolver plus evidence/news builders
4. Task 4: prompt builder plus AI gate service
5. Task 5: storage and API
6. Task 6: web integration
7. Task 7: docs and full verification

## Notes for the Implementer

- Treat `bottom_divergence_double_breakout` as the only fully supported strategy in the first working slice.
- Do not block the whole run when AI gate evaluation fails for one candidate; degrade that candidate to `failed` or `skipped` and continue.
- Keep deterministic logic on the backend whenever possible:
  - active strategy selection
  - missing evidence detection
  - hard veto application
  - stage mapping where the strategy defines clear rules
- Keep the model focused on:
  - strategy confirmation
  - structured explanation
  - news-based veto or downgrade
  - concise execution guidance
