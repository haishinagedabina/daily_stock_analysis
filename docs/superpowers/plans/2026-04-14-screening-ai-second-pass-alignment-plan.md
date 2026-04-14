# Screening AI Second-Pass Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the screening AI second-pass with the Notion "AI二筛设计规范" so the module becomes a structured rule-following review layer instead of a general single-stock analyzer.

**Architecture:** Keep the existing five-layer screening pipeline as the source of truth, but replace the current `AnalysisService/analyzer` reuse path with a dedicated screening AI review path. The new path must consume structured `candidate_decision` data, request a fixed JSON schema, enforce hard rule constraints, and fail closed back to rules when the model output is invalid or insufficient.

**Tech Stack:** Python, pytest, existing screening pipeline services, current storage layer, LLM integration already used by the project

---

## Spec Anchor

Primary spec source:
- Notion page: `AI二筛设计规范`
- Page URL: `https://app.notion.com/p/333304835347812aba1cf8d5f852cf09`
- Snapshot reviewed in this planning session: `2026-03-30`

Minimum contract that must be matched during implementation:
- `environment_ok`
- `trade_stage`
- `entry_maturity`
- `setup_type`
- `risk_level`
- `initial_position`
- `stop_loss_rule`
- `take_profit_plan`
- `invalidation_rule`
- `reasoning_summary`
- `confidence`

Hard rules from the spec that must be explicitly tested:
- if `environment_ok = false`, `trade_stage` must not be higher than `watch`
- if `setup_type = none`, `entry_maturity` must not be high
- if `trade_stage` is execution-level, `stop_loss_rule`, `take_profit_plan`, and `invalidation_rule` must not be empty
- invalid JSON or timeout must fail closed to rule results

## Result Source Rules

There are only three allowed final source states:

- `rules_only`
  Meaning: no AI review was attempted or AI review was skipped
- `rules_fallback`
  Meaning: AI was attempted but the final adopted result is fully from the rule path due to invalid JSON, timeout, exception, or retry exhaustion
- `rules_plus_ai`
  Meaning: AI returned valid structured output and the final adopted result includes AI review fields after guard validation

Guard behavior must be explicit:
- parse failure / timeout / retry exhaustion: return `rules_fallback`
- valid JSON but guard-downgraded fields: still `rules_plus_ai`, but store downgrade reason
- valid JSON that cannot be normalized safely: treat as `rules_fallback`

## Scope And Boundaries

This plan covers one subsystem only: the screening AI second-pass path used after five-layer candidate selection.

In scope:
- Dedicated AI review schema
- Dedicated prompt builder / service / guard path for screening
- Structured fallback behavior
- Candidate storage and API consumption changes needed to consume structured AI output
- Docs and tests for the new behavior

Out of scope:
- Reworking the five-layer upstream ranking logic
- Replacing the main single-stock analyzer used outside screening
- Large UI redesigns
- Backtest framework changes

## File Structure

**Likely create:**
- `src/schemas/screening_ai_review.py`
  Purpose: canonical schema and typed payload for screening AI second-pass
- `src/services/screening_ai_review_prompt_builder.py`
  Purpose: build the Notion-aligned JSON-only prompt from structured candidate inputs
- `src/services/screening_ai_review_guard.py`
  Purpose: apply hard constraints and downgrade rules after model output
- `src/services/screening_ai_review_service.py`
  Purpose: call the model, parse JSON, retry once on invalid output, and return structured review or fallback
- `tests/test_screening_ai_review_prompt_builder.py`
- `tests/test_screening_ai_review_guard.py`
- `tests/test_screening_ai_review_service.py`

**Likely modify:**
- `src/services/candidate_analysis_service.py`
  Purpose: stop using the general `AnalysisService` path for screening second-pass
- `src/services/screening_task_service.py`
  Purpose: wire the dedicated screening AI review path into the post-screening stage
- `src/services/ai_review_protocol.py`
  Purpose: either retire legacy keyword fallback responsibilities or narrow them to compatibility-only helpers
- `src/storage.py`
  Purpose: stop deriving screening behavior from prose-like `operation_advice`; consume structured AI review fields instead
- `api/v1/endpoints/screening.py`
  Purpose: ensure candidate list/detail responses expose the new structured fields cleanly if needed
- `apps/dsa-web/src/components/screening/**`
  Purpose: stop any UI dependence on prose-only `operation_advice` or legacy advice-derived behavior
- `tests/test_screening_task_service.py`
- `tests/test_screening_storage.py`
- `apps/dsa-web/src/components/screening/__tests__/**`
- `README.md`
- `docs/CHANGELOG.md`

## Implementation Strategy

### P0
- Separate screening AI second-pass from the general analyzer
- Enforce fixed JSON schema
- Remove keyword-based decision influence from screening
- Fail closed to rule results

### P1
- Make storage/API/front-end consumption depend on structured AI review fields
- Add complete observability and explicit source markers

### P2
- Clean up legacy compatibility code and document migration boundaries

## Task 1: Freeze The Contract

**Files:**
- Create: `src/schemas/screening_ai_review.py`
- Modify: `src/services/ai_review_protocol.py`
- Test: `tests/test_screening_ai_review_guard.py`

- [ ] **Step 1: Write a failing schema test**

Add a test that asserts the screening AI review result supports at least:
- `environment_ok`
- `trade_stage`
- `entry_maturity`
- `setup_type`
- `risk_level`
- `initial_position`
- `stop_loss_rule`
- `take_profit_plan`
- `invalidation_rule`
- `reasoning_summary`
- `confidence`
- `fallback_reason`
- `result_source`

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/test_screening_ai_review_guard.py -q`

Expected: FAIL because the current contract is incomplete.

- [ ] **Step 3: Add the canonical schema**

Create a typed schema model that:
- represents the Notion contract exactly
- separates raw model output from normalized final output
- includes explicit metadata fields such as `result_source`, `is_fallback`, and `fallback_reason`

- [ ] **Step 4: Add normalization helpers**

Implement helpers that:
- coerce enums safely
- reject invalid execution-level output when plan fields are missing
- preserve raw output separately for logging only

- [ ] **Step 5: Run the test again**

Run: `python -m pytest tests/test_screening_ai_review_guard.py -q`

Expected: PASS for the schema contract checks.

## Task 2: Build A Dedicated Screening Prompt

**Files:**
- Create: `src/services/screening_ai_review_prompt_builder.py`
- Modify: `src/services/candidate_analysis_service.py`
- Test: `tests/test_screening_ai_review_prompt_builder.py`

- [ ] **Step 1: Write a failing prompt test**

Add a test that asserts the screening prompt:
- consumes structured sections `context/market/theme/stock/setup/trade_plan`
- requests JSON only
- states that AI cannot override environment/theme hard constraints
- states that missing evidence must downgrade conservatively

- [ ] **Step 2: Run the failing test**

Run: `python -m pytest tests/test_screening_ai_review_prompt_builder.py -q`

Expected: FAIL because the current screening flow still reuses the general analyzer prompt.

- [ ] **Step 3: Implement the screening prompt builder**

Build a dedicated prompt builder that:
- never asks for a dashboard
- never asks for general stock commentary
- only includes structured candidate fields
- never includes long raw news text
- always includes the exact required output schema

- [ ] **Step 4: Replace screening prompt assembly**

Update `candidate_analysis_service.py` so screening AI requests use the dedicated builder instead of piggybacking on the general analyzer prompt.

- [ ] **Step 5: Run the test again**

Run: `python -m pytest tests/test_screening_ai_review_prompt_builder.py -q`

Expected: PASS with a stable JSON-only second-pass prompt.

## Task 3: Add Dedicated Review Execution And Fail-Closed Retry

**Files:**
- Create: `src/services/screening_ai_review_service.py`
- Test: `tests/test_screening_ai_review_service.py`

- [ ] **Step 1: Write failing service tests**

Add tests for:
- valid JSON output on first try
- invalid JSON output then valid JSON on retry
- invalid JSON twice then fallback to rules
- timeout or model exception then fallback to rules

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_screening_ai_review_service.py -q`

Expected: FAIL because no dedicated service exists yet.

- [ ] **Step 3: Implement the service**

Create a screening review service that:
- calls the model with the dedicated screening prompt
- uses the project's existing LLM calling abstraction rather than the general single-stock dashboard path
- retries exactly once on invalid JSON
- does not use keyword fallback for screening decisions
- returns `rules_fallback` when output stays invalid
- records prompt version, model, parse status, retry count, and source

- [ ] **Step 4: Keep legacy single-stock analysis isolated**

Ensure this new service does not share the general analyzer result conversion path used by non-screening workflows.

- [ ] **Step 5: Define normalize-failure behavior**

Document and implement that:
- invalid JSON can retry once
- valid JSON with invalid enum or impossible structure does not retry forever
- non-normalizable structured output becomes `rules_fallback`

- [ ] **Step 6: Run the tests again**

Run: `python -m pytest tests/test_screening_ai_review_service.py -q`

Expected: PASS with explicit retry and fallback behavior.

## Task 4: Enforce Hard Constraints After Model Output

**Files:**
- Create: `src/services/screening_ai_review_guard.py`
- Test: `tests/test_screening_ai_review_guard.py`

- [ ] **Step 1: Write failing guard tests**

Add cases for:
- `environment_ok=false` forcing `trade_stage <= watch`
- `setup_type=none` blocking high maturity
- missing stop loss anchor forcing downgrade from execution-level stages
- model output conflicting with regime/theme hard constraints

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_screening_ai_review_guard.py -q`

Expected: FAIL because the current implementation only applies a limited market ceiling.

- [ ] **Step 3: Implement guard rules**

Implement post-model enforcement that:
- applies environment ceiling
- applies setup validity checks
- applies execution-plan completeness checks
- downgrades conservatively with explicit reasons
- never silently accepts structurally incomplete execution-level output

- [ ] **Step 4: Add explicit fallback reason tags**

Use machine-readable fallback reasons like:
- `invalid_json`
- `timeout`
- `missing_stop_anchor`
- `environment_constraint`
- `setup_constraint`
- `rule_conflict`

- [ ] **Step 5: Run the tests again**

Run: `python -m pytest tests/test_screening_ai_review_guard.py -q`

Expected: PASS with deterministic downgrade behavior.

## Task 5: Rewire ScreeningTaskService To The New Path

**Files:**
- Modify: `src/services/screening_task_service.py`
- Modify: `src/services/candidate_analysis_service.py`
- Test: `tests/test_screening_task_service.py`

- [ ] **Step 1: Write failing orchestration tests**

Add tests that assert:
- screening AI second-pass no longer calls the general analyzer path
- unstructured prose output never becomes effective AI review for screening
- invalid model output keeps candidates on rule results
- structured valid output attaches a normalized screening AI review

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_screening_task_service.py -q`

Expected: FAIL against current orchestration assumptions.

- [ ] **Step 3: Implement the orchestration changes**

Update the AI stage so it:
- builds structured AI requests from candidate decisions
- invokes `screening_ai_review_service`
- attaches only normalized screening review objects
- marks `selected_for_ai` independently from `has_ai_analysis`
- stores `result_source` and `fallback_reason`

- [ ] **Step 4: Remove screening keyword fallback influence**

Any screening-specific path that still depends on `operation_advice` keywords for stage inference should be removed or confined to non-screening compatibility only.

- [ ] **Step 5: Run the orchestration tests again**

Run: `python -m pytest tests/test_screening_task_service.py -q`

Expected: PASS with the dedicated second-pass path in place.

## Task 6: Fix Storage And Response Consumption

**Files:**
- Modify: `src/storage.py`
- Modify: `api/v1/endpoints/screening.py`
- Test: `tests/test_screening_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add tests that assert:
- `rules_plus_ai` only applies when a valid structured AI review exists
- prose-like `ai_operation_advice` alone does not change candidate ranking behavior
- fallback results are clearly marked as rule-derived
- API payloads expose structured AI review fields without requiring prose parsing

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_screening_storage.py -q`

Expected: FAIL because the storage layer still derives meaning from `ai_operation_advice`.

- [ ] **Step 3: Implement structured storage behavior**

Update storage enrichment so it:
- uses structured AI review fields instead of prose suggestions
- preserves `result_source`, `is_fallback`, and `fallback_reason`
- avoids bonus/penalty logic that depends only on text advice
- keeps backward-compatible fields only as passive display metadata when needed

- [ ] **Step 4: Update API shaping if needed**

Expose a stable response model for:
- `trade_stage`
- `risk_level`
- execution plan fields
- `result_source`
- `fallback_reason`
- `confidence`

- [ ] **Step 5: Update Web consumption**

Update screening UI consumers so they:
- render `result_source` and `fallback_reason` explicitly when useful
- do not infer ranking or recommendation behavior from prose-only `operation_advice`
- prefer structured fields such as `trade_stage`, `risk_level`, and plan fields

- [ ] **Step 6: Run the tests again**

Run: `python -m pytest tests/test_screening_storage.py -q`

Expected: PASS with structure-first response shaping.

## Task 7: Add Observability Required By The Spec

**Files:**
- Modify: `src/services/screening_ai_review_service.py`
- Modify: `src/services/screening_task_service.py`
- Test: `tests/test_screening_task_service.py`

- [ ] **Step 1: Write failing observability tests**

Add checks for:
- model name/version logged
- prompt version logged
- parse result logged
- fallback source logged
- no long raw news body persisted in screening AI logs

- [ ] **Step 2: Run the failing tests**

Run: `python -m pytest tests/test_screening_task_service.py -q`

Expected: FAIL because the current logs do not fully reflect the Notion observability requirements.

- [ ] **Step 3: Implement observability**

Record:
- model name
- prompt version
- retry count
- parse success/failure
- fallback reason
- final result source
- compact structured input summary only

- [ ] **Step 4: Run the tests again**

Run: `python -m pytest tests/test_screening_task_service.py -q`

Expected: PASS with explicit source/fallback observability.

## Task 8: Update Documentation And Rollout Notes

**Files:**
- Modify: `README.md`
- Modify: `docs/CHANGELOG.md`
- Optional modify: `docs/strategy_system_refactor_plan.md`

- [ ] **Step 1: Update user-visible behavior docs**

Document that screening AI second-pass:
- is a structured review layer
- cannot override upstream hard constraints
- falls back to rules on invalid or incomplete output

- [ ] **Step 2: Update changelog**

Describe the behavior change from general-analysis compatibility to dedicated structured screening review.

- [ ] **Step 3: Add rollout note**

Capture any backward-compatibility caveats for API/UI consumers.

## Verification Matrix

Run at minimum:

- `python -m pytest tests/test_screening_ai_review_prompt_builder.py -q`
- `python -m pytest tests/test_screening_ai_review_guard.py -q`
- `python -m pytest tests/test_screening_ai_review_service.py -q`
- `python -m pytest tests/test_screening_task_service.py -q`
- `python -m pytest tests/test_screening_storage.py -q`
- `cd apps/dsa-web && npm run lint`
- `cd apps/dsa-web && npm run build`
- `./scripts/ci_gate.sh`
- `python -m py_compile src/schemas/screening_ai_review.py src/services/screening_ai_review_prompt_builder.py src/services/screening_ai_review_guard.py src/services/screening_ai_review_service.py src/services/candidate_analysis_service.py src/services/screening_task_service.py src/storage.py`

If user-visible screening API fields change, also run:

- `python -m pytest tests/test_screening_api.py -q`

## Delivery Notes

- `P0` is the minimum safe slice for correctness.
- `P1` is needed before declaring the new screening AI second-pass production-ready.
- `P2` should be done before removing legacy compatibility code.
- Do not preserve keyword-based screening behavior just for convenience; screening must fail closed to rules, not degrade into prose interpretation.
- `ai_review_protocol.py` should be kept only as a compatibility layer during migration; once no screening path depends on keyword fallback, schedule its screening-specific fallback logic for deletion in `P2`.
