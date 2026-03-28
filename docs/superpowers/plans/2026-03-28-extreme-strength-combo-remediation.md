# Extreme Strength Combo Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `extreme_strength_combo` flow match the intended "gap + limit-up + hot theme" strategy, and make candidate detail pages explain the catalyst news and rule hits clearly.

**Architecture:** Keep the current OpenClaw -> screening task -> factor snapshot -> candidate detail chain, but move `extreme_strength_combo` from "post-hoc enrichment" to the actual screening path. The implementation should first fix the OpenClaw entry and strategy routing, then make hot-theme membership a hard gate with real board data, then correct leader/core-signal scoring inputs, and finally expose stage-based explanations in the Web detail drawer.

**Tech Stack:** FastAPI, Python service layer, SQLAlchemy storage, React + TypeScript + Vitest, pytest

---

## File Map

### Backend entry and orchestration
- Modify: `api/v1/endpoints/screening.py`
- Modify: `api/v1/schemas/screening.py`
- Modify: `src/services/screening_task_service.py`
- Reference: `src/services/theme_context_ingest_service.py`
- Reference: `src/agent/skills/base.py`

### Factor enrichment and strategy evaluation
- Modify: `src/services/factor_service.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/theme_matching_service.py`
- Modify: `src/services/leader_score_calculator.py`
- Modify: `src/services/core_signal_identifier.py`
- Modify: `src/services/extreme_strength_scorer.py`
- Modify: `src/services/strategy_screening_engine.py`
- Modify: `strategies/extreme_strength_combo.yaml`
- Reference: `src/core/market_guard.py`
- Reference: `data_provider/base.py`

### Web explanation layer
- Modify: `apps/dsa-web/src/components/screening/CandidateDetailDrawer.tsx`
- Modify: `apps/dsa-web/src/types/screening.ts`
- Reference: `apps/dsa-web/src/stores/screeningStore.ts`

### Tests
- Modify: `tests/test_openclaw_endpoint_integration.py`
- Modify: `tests/test_screening_task_service_hot_theme.py`
- Modify: `tests/test_hot_theme_factor_enrichment.py`
- Modify: `tests/test_hot_theme_factor_enricher.py`
- Modify: `tests/test_theme_matching_service.py`
- Modify: `tests/test_leader_score_calculator.py`
- Modify: `tests/test_strategy_screening_engine.py`
- Modify: `tests/test_screening_api.py`
- Modify: `apps/dsa-web/src/components/screening/__tests__/CandidateDetailDrawer.test.tsx`

### Docs
- Modify: `.claude/reviews/extreme_strength_combo_strategy_audit_2026-03-28.md` only if the audit summary needs a post-implementation appendix
- Modify: `README.md` if API behavior or detail-view semantics become part of user-facing workflow
- Modify: `docs/CHANGELOG.md` because the OpenClaw-triggered screening result semantics and detail-view output are user-visible

## Constraints and Guardrails

- Follow TDD for each behavior change: add or extend a failing test first, then implement the minimal fix.
- Do not add a parallel screening path; reuse `ScreeningTaskService`, `FactorService`, and the existing strategy engine.
- Do not make hot theme a soft score bonus for this strategy. For `extreme_strength_combo`, hot-theme membership must be enforced before final candidate selection.
- Do not claim intraday fields like "minutes since open" when the system does not have trustworthy intraday data. Add explicit fallback semantics.
- Keep API compatibility where possible by appending fields instead of renaming existing ones.
- Do not commit unless the human explicitly asks for it. Replace commit steps with "checkpoint" steps in execution.

## Task 1: Fix OpenClaw Entry Wiring

**Outcome:** OpenClaw runs actually execute `extreme_strength_combo`, preserve the requested `trade_date`, and keep theme context in the run snapshot.

**Files:**
- Modify: `api/v1/endpoints/screening.py`
- Modify: `src/services/screening_task_service.py`
- Modify: `tests/test_openclaw_endpoint_integration.py`
- Modify: `tests/test_screening_task_service_hot_theme.py`
- Optional: `tests/test_screening_api.py`

- [ ] **Step 1: Add failing coverage for strategy-engine routing**

Add assertions that an OpenClaw-triggered run:
- passes the parsed request date into `execute_run`
- creates `ScreeningTaskService` with a live `SkillManager`
- persists `theme_context` in `run_snapshot`
- returns candidates whose `matched_strategies` are only `["extreme_strength_combo"]`

Suggested test targets:

```python
def test_openclaw_endpoint_passes_trade_date_and_strategy_engine(client):
    response = client.post(
        "/api/v1/screening/openclaw-theme-run",
        json={
            "trade_date": "2026-03-27",
            "market": "cn",
            "themes": [...],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["trade_date"] == "2026-03-27"
```

- [ ] **Step 2: Run focused backend tests and confirm they fail for the right reason**

Run:

```bash
python -m pytest tests/test_openclaw_endpoint_integration.py tests/test_screening_task_service_hot_theme.py -q
```

Expected before the fix:
- the route still uses `trade_date=None`
- the service still falls back to legacy screening

- [ ] **Step 3: Implement the minimal routing fix**

Make the endpoint build or receive a `SkillManager`, call `load_builtin_strategies()`, and inject it into `ScreeningTaskService`. Parse `request.trade_date` to `date` and pass it through to `execute_run`. Preserve `strategy_names=["extreme_strength_combo"]` and the `theme_context` payload in the stored run snapshot.

Implementation notes:

```python
skill_manager = SkillManager()
skill_manager.load_builtin_strategies()
service = ScreeningTaskService(skill_manager=skill_manager)
result = service.execute_run(
    trade_date=date.fromisoformat(request.trade_date),
    trigger_type="openclaw",
    strategy_names=["extreme_strength_combo"],
)
```

- [ ] **Step 4: Verify the routing fix**

Run:

```bash
python -m pytest tests/test_openclaw_endpoint_integration.py tests/test_screening_task_service_hot_theme.py tests/test_screening_api.py -q
python -m py_compile api/v1/endpoints/screening.py src/services/screening_task_service.py
```

Expected:
- OpenClaw requests preserve `trade_date`
- only `extreme_strength_combo` remains active for this path
- no syntax errors

- [ ] **Step 5: Checkpoint**

Record in the work log:
- OpenClaw route now uses strategy engine
- requested date is no longer discarded
- no commit without explicit approval

## Task 2: Make Hot Theme a Hard Gate With Real Board Data

**Outcome:** `extreme_strength_combo` first proves the stock belongs to the active hot theme, using real board membership instead of empty board lists and fuzzy fallback only.

**Files:**
- Modify: `src/services/factor_service.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/theme_matching_service.py`
- Reference: `data_provider/base.py`
- Modify: `tests/test_theme_matching_service.py`
- Modify: `tests/test_hot_theme_factor_enrichment.py`
- Modify: `tests/test_hot_theme_factor_enricher.py`

- [ ] **Step 1: Add failing tests for board-aware theme matching**

Cover these cases:
- board match present -> theme score passes hot-theme threshold
- no board match and only weak keyword overlap -> stock is rejected
- `extreme_strength_combo` does not select candidates when `is_hot_theme_stock` is false

Suggested test shape:

```python
def test_theme_match_prefers_real_board_membership():
    result = service.match_stock_to_themes(
        stock_name="寒武纪",
        boards=["芯片", "算力"],
        themes=[theme],
    )
    assert result.is_hot_theme_stock is True
    assert result.match_score >= 0.6
```

- [ ] **Step 2: Run the focused tests to capture current failure**

Run:

```bash
python -m pytest tests/test_theme_matching_service.py tests/test_hot_theme_factor_enrichment.py tests/test_hot_theme_factor_enricher.py -q
```

Expected before the fix:
- current factor snapshots still send `boards=[]`
- hot-theme logic still behaves like post-enrichment labeling

- [ ] **Step 3: Wire real boards into factor enrichment and enforce the gate**

Implementation requirements:
- fetch stock board/concept data through the existing provider path instead of inventing a new board source
- pass populated `boards` into `ThemeMatchingService`
- make `phase1` in `phase_results` reflect real market/theme gating
- for `extreme_strength_combo`, reject rows early when `is_hot_theme_stock` is false

Keep fallback behavior explicit:
- if board data is unavailable, allow a downgraded fuzzy match result to exist
- but do not treat downgraded matches as equivalent to confirmed board matches

- [ ] **Step 4: Verify theme gating behavior**

Run:

```bash
python -m pytest tests/test_theme_matching_service.py tests/test_hot_theme_factor_enrichment.py tests/test_hot_theme_factor_enricher.py tests/test_strategy_screening_engine.py -q
python -m py_compile src/services/factor_service.py src/services/hot_theme_factor_enricher.py src/services/theme_matching_service.py
```

Expected:
- board-aware tests pass
- non-hot-theme stocks do not enter the final candidate set for this strategy

- [ ] **Step 5: Checkpoint**

Record:
- board data now participates in theme scoring
- hot theme is a gating condition, not just a display tag

## Task 3: Correct Leader and Core-Signal Inputs

**Outcome:** leader scoring and core-signal scoring use trustworthy inputs, and fields that are unavailable are no longer silently treated as strongest-signal defaults.

**Files:**
- Modify: `src/services/factor_service.py`
- Modify: `src/services/leader_score_calculator.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/core_signal_identifier.py`
- Modify: `src/services/extreme_strength_scorer.py`
- Modify: `tests/test_leader_score_calculator.py`
- Modify: `tests/test_hot_theme_factor_enricher.py`
- Optional: `tests/test_factor_service.py`

- [ ] **Step 1: Add failing tests for missing-field fallbacks**

Add coverage for:
- missing `circ_mv` does not become a free small-cap bonus
- missing `intraday_minutes_since_open` does not imply "early limit-up"
- turnover scoring distinguishes real turnover from synthesized proxies
- score tiers align with the intended `>=80 selected / 60-79 watchlist / below 60 reject`

Suggested test shape:

```python
def test_missing_intraday_minutes_does_not_mark_early_limit_up():
    snapshot = {"is_limit_up": True}
    enriched = enricher.enrich_snapshot(snapshot, theme_context)
    assert enriched["leader_signals"]["early_limit_up"] is False
```

- [ ] **Step 2: Run the focused score tests**

Run:

```bash
python -m pytest tests/test_leader_score_calculator.py tests/test_hot_theme_factor_enricher.py -q
```

Expected before the fix:
- missing fields still inflate scores
- score semantics do not line up with product expectations

- [ ] **Step 3: Implement score-input corrections**

Implementation requirements:
- populate `circ_mv` only when real data is available
- when unavailable, mark the factor as unknown and score neutrally instead of optimistically
- keep `turnover_rate` separate from any derived proxy
- if intraday data is unavailable, expose `early_limit_up_confidence="unknown"` or an equivalent explicit flag
- unify the scorer so the final `extreme_strength_score` comes from one source of truth instead of overlapping helper classes

Use explicit branches like:

```python
if circ_mv is None:
    market_cap_score = 0.0
    missing_reasons.append("circ_mv_unavailable")
```

- [ ] **Step 4: Verify corrected score behavior**

Run:

```bash
python -m pytest tests/test_leader_score_calculator.py tests/test_hot_theme_factor_enricher.py tests/test_factor_service.py -q
python -m py_compile src/services/leader_score_calculator.py src/services/core_signal_identifier.py src/services/extreme_strength_scorer.py
```

Expected:
- no more default "max strength" on missing values
- score tiers become stable and explainable

- [ ] **Step 5: Checkpoint**

Record:
- unknown data is scored as unknown, not strongest
- leader and core-signal outputs now reflect available evidence

## Task 4: Repair Strategy Semantics and Stage Explanations

**Outcome:** the strategy engine respects the YAML semantics for `extreme_strength_combo`, and stored result fields explain the five-stage logic in product language.

**Files:**
- Modify: `src/services/strategy_screening_engine.py`
- Modify: `strategies/extreme_strength_combo.yaml`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `tests/test_strategy_screening_engine.py`
- Optional: `tests/test_hot_theme_screening_correct_strategy.py`

- [ ] **Step 1: Add failing tests for nested strategy filters and stage explanations**

Cover:
- YAML `any` groups are parsed and enforced
- candidates must match at least one core-signal branch
- `phase_results` reflect the five strategy stages instead of placeholder booleans
- `extreme_strength_reasons` are readable explanations rather than raw badges only

Suggested test target:

```python
def test_any_group_in_extreme_strength_combo_yaml_is_enforced():
    df = make_df(is_limit_up=False, gap_breakaway=False, pattern_123_low_trendline=False)
    result = engine.evaluate_dataframe(df, ["extreme_strength_combo"])
    assert result.empty
```

- [ ] **Step 2: Run semantic-strategy tests**

Run:

```bash
python -m pytest tests/test_strategy_screening_engine.py tests/test_hot_theme_screening_correct_strategy.py -q
```

Expected before the fix:
- nested `any` is ignored
- phase explanations do not reflect real strategy stages

- [ ] **Step 3: Implement parser and payload fixes**

Implementation requirements:
- extend the strategy rule builder to support nested `all` and `any` groups used by the YAML
- keep backward compatibility for older flat `field/op/value` rules
- rewrite `phase_results` to map to:
  - `phase1_market_and_theme`
  - `phase2_leader_screen`
  - `phase3_core_signal`
  - `phase4_entry_readiness`
  - `phase5_risk_controls`
- add a compact human-readable explanation list for detail view consumption

- [ ] **Step 4: Verify strategy semantics**

Run:

```bash
python -m pytest tests/test_strategy_screening_engine.py tests/test_hot_theme_screening_correct_strategy.py tests/test_end_to_end_strategy_matching.py -q
python -m py_compile src/services/strategy_screening_engine.py src/services/hot_theme_factor_enricher.py
```

Expected:
- YAML semantics are honored
- stored explanations match the five-stage strategy narrative

- [ ] **Step 5: Checkpoint**

Record:
- `extreme_strength_combo` is now defined once in YAML and honored in execution
- stage explanations are product-readable

## Task 5: Upgrade Candidate Detail Drawer Explanations

**Outcome:** the detail page clearly shows catalyst news, catalyst summary, stage explanations, and why the candidate was selected or downgraded.

**Files:**
- Modify: `apps/dsa-web/src/types/screening.ts`
- Modify: `apps/dsa-web/src/components/screening/CandidateDetailDrawer.tsx`
- Modify: `apps/dsa-web/src/components/screening/__tests__/CandidateDetailDrawer.test.tsx`

- [ ] **Step 1: Add failing UI tests for explanation blocks**

Cover:
- catalyst summary renders when present
- catalyst news renders as a structured list
- stage explanation labels render in strategy language
- raw `ruleHits` remain secondary to human-readable explanations
- missing explanation fields degrade gracefully

Suggested test shape:

```tsx
it('shows catalyst news and stage explanations', () => {
  mockStore.selectedCandidate = {
    ...mockCandidate,
    factorSnapshot: {
      theme_catalyst_summary: 'AI 芯片受政策催化',
      theme_catalyst_news: [{ title: '政策发布', summary: '...' }],
      phase_results: { phase1_market_and_theme: true },
      extreme_strength_reasons: ['跳空涨停突破前高'],
    },
  };
  render(<CandidateDetailDrawer />);
  expect(screen.getByText('AI 芯片受政策催化')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused Web tests**

Run:

```bash
cd apps/dsa-web
npm run test -- CandidateDetailDrawer
```

Expected before the fix:
- current drawer does not fully assert the new explanation structure

- [ ] **Step 3: Implement the explanation rendering pass**

Implementation requirements:
- keep current badges, but demote them below readable explanation sections
- render catalyst news as concise cards or rows with title, source, and summary if available
- normalize stage labels in the component instead of exposing raw backend keys directly
- avoid crashing on partial snapshots

- [ ] **Step 4: Verify Web rendering**

Run:

```bash
cd apps/dsa-web
npm run test -- CandidateDetailDrawer
npm run lint
npm run build
```

Expected:
- explanation sections render and build passes

- [ ] **Step 5: Checkpoint**

Record:
- detail drawer now tells the user why the stock matches the strategy
- news and stage explanations are visible without reading raw JSON

## Task 6: End-to-End Verification and Documentation

**Outcome:** the changed behavior is documented, and the verification evidence is ready for review.

**Files:**
- Modify: `docs/CHANGELOG.md`
- Modify: `README.md` if the OpenClaw workflow is described there
- Optional: `.claude/reviews/extreme_strength_combo_strategy_audit_2026-03-28.md`

- [ ] **Step 1: Add changelog entries before final verification**

Document:
- OpenClaw now truly runs `extreme_strength_combo`
- requested `trade_date` is honored
- hot-theme gating uses real board membership when available
- detail view now surfaces catalyst news and strategy explanations

- [ ] **Step 2: Run the minimum cross-surface verification set**

Run:

```bash
./scripts/ci_gate.sh
python -m pytest -m "not network" tests/test_openclaw_endpoint_integration.py tests/test_screening_task_service_hot_theme.py tests/test_theme_matching_service.py tests/test_leader_score_calculator.py tests/test_strategy_screening_engine.py -q
cd apps/dsa-web && npm ci && npm run lint && npm run build
```

Expected:
- backend gate passes
- focused strategy tests pass
- Web build passes

- [ ] **Step 3: Do a manual smoke check if local data permits**

Manual check:
1. Trigger `POST /api/v1/screening/openclaw-theme-run` with one hot theme
2. Confirm the run metadata shows the requested date and `extreme_strength_combo`
3. Confirm at least one candidate detail view shows:
   - catalyst summary
   - catalyst news
   - stage explanations
   - readable selection reasons

- [ ] **Step 4: Capture residual risks**

Explicitly note:
- if intraday board or turnover data still comes from fallback sources
- if market MA100 gating is still warning-only for non-OpenClaw paths
- if historical backfill quality varies by data provider

- [ ] **Step 5: Checkpoint**

Prepare the delivery summary under the repo format:
- 改了什么
- 为什么这么改
- 验证情况
- 未验证项
- 风险点
- 回滚方式

## Recommended Execution Order

1. Task 1: fix routing first, otherwise later fixes still run on the wrong engine
2. Task 2: make hot-theme gating and board matching correct, otherwise selection quality remains fundamentally off
3. Task 3: correct score inputs, otherwise rankings still drift
4. Task 4: repair YAML semantics and explanation payloads, otherwise strategy meaning remains inconsistent
5. Task 5: wire the explanation layer into Web
6. Task 6: verify and document

## Definition of Done

- OpenClaw-triggered runs use the actual `extreme_strength_combo` strategy engine
- requested `trade_date` is preserved end-to-end
- non-hot-theme stocks are excluded from `extreme_strength_combo`
- leader/core-signal scores no longer inflate on missing values
- YAML `any` semantics are enforced
- candidate detail pages show catalyst summary, catalyst news, stage explanations, and readable reasons
- focused backend tests and Web build pass
- `docs/CHANGELOG.md` is updated for the user-visible change

## Handoff Notes

- Start with Task 1 and Task 2 before touching the Web layer.
- Keep storage payload changes additive.
- If a clean board-membership source cannot be obtained from the existing provider layer, stop and document the data gap before inventing a new board taxonomy.
- Do not add intraday certainty where the project only has end-of-day data.
