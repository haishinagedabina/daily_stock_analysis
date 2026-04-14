# Leader Stock Identification Simplification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前偏复杂的龙头识别逻辑简化为两条明确规则：同题材内优先取涨停股；若有多只涨停股，则取流通市值最小者作为龙头。

**Architecture:** 不再以多维 `leader_score` 作为龙头识别主逻辑，而改成“规则式 leader 选择器”。主链路仍沿用 `FactorService -> SectorHeatEngine -> ThemePositionResolver -> FiveLayerPipeline`，但龙头判定本身收敛为 `is_limit_up + circ_mv` 两个字段，其他强势分仅作为兼容字段保留，不再主导龙头结论。

**Tech Stack:** Python, pandas, pytest/unittest, existing service-layer tests under `tests/`

---

## 0. Scope And Constraints

### In Scope

- 以 `is_limit_up` + `circ_mv` 重写龙头判定语义
- 热点题材内龙头候选只从涨停股中产生
- 多只涨停股时，按流通市值从小到大取优先级
- `leader_pool`、`leader_candidate_count`、`front_codes` 与新规则对齐
- 用 TDD 方式完成测试、实现、日志调整

### Out Of Scope For This Round

- 最早封板、分时强度、开盘 30 分钟内涨停
- 换手率、趋势强度、突破强度参与龙头主判定
- 复杂 `theme_leader_score` 权重设计
- 新闻/研报/embedding 级题材增强

### New Decision Rule

同一热点题材/板块内：

1. 先筛出 `is_limit_up == True` 的股票
2. 若无涨停股，则该题材当日视为“无明确龙头股”
3. 若只有一只涨停股，则直接认定其为龙头
4. 若有多只涨停股，则按 `circ_mv` 从小到大排序，取最小者为龙头
5. `circ_mv` 缺失时排在有值股票之后，避免“未知市值”被误判为最小市值

### Existing Gaps To Correct First

- [src/services/leader_score_calculator.py](/e:/daily_stock_analysis/src/services/leader_score_calculator.py:1) 仍然是多维打分模型，不适合这次规则化简化
- [src/services/sector_heat_engine.py](/e:/daily_stock_analysis/src/services/sector_heat_engine.py:21) 仍用分数阈值统计 `leader_candidate_count`
- [src/services/candidate_pool_classifier.py](/e:/daily_stock_analysis/src/services/candidate_pool_classifier.py:1) 当前仍围绕 `leader_score/extreme_strength_score` 分层
- [tests/test_factor_service.py](/e:/daily_stock_analysis/tests/test_factor_service.py:167) 还没有锁定“涨停 + 最小流通市值”的规则输出

### Verification Baseline

- 首选命令：`python -m pytest -m "not network"`
- 每次变更至少执行对应目标测试文件
- 对改动过的 Python 文件执行：`python -m py_compile <changed_python_files>`

---

### Task 1: Define The Simplified Leader Rule In Tests

**Files:**
- Modify: `tests/test_hot_theme_factor_enricher.py`
- Modify: `tests/test_five_layer_pipeline.py`
- Modify: `tests/test_decision_modules.py`
- Modify: `tests/test_factor_service.py`

- [ ] **Step 1: 先写失败测试，锁定“龙头只由涨停 + 流通市值最小决定”**

建议新增断言：

```python
def test_limit_up_stock_is_preferred_over_non_limit_up_stock(self):
    self.assertEqual(leader_code, "000001")

def test_smallest_circ_mv_wins_when_multiple_limit_up_stocks_exist(self):
    self.assertEqual(leader_code, "000002")

def test_missing_circ_mv_ranks_after_known_circ_mv(self):
    self.assertEqual(leader_code, "000003")

def test_no_limit_up_means_no_clear_leader(self):
    self.assertIsNone(leader_code)
```

- [ ] **Step 2: 运行测试，确认当前实现仍按复杂分数工作**

Run: `python -m pytest tests/test_hot_theme_factor_enricher.py tests/test_five_layer_pipeline.py tests/test_decision_modules.py tests/test_factor_service.py -v`

Expected:
- FAIL
- 当前实现不能稳定产出“只取涨停股，再按最小流通市值排序”的结果

---

### Task 2: Replace Score-Led Leader Logic With Rule-Led Selection

**Files:**
- Modify: `src/services/leader_stock_selector.py`
- Modify: `src/services/hot_theme_factor_enricher.py`
- Modify: `src/services/five_layer_pipeline.py`
- Modify: `src/services/factor_service.py`

- [ ] **Step 1: 在 `LeaderStockSelector` 中实现规则式选择器**

实现约束：
- 输入一组同题材股票及其因子快照
- 仅从 `is_limit_up == True` 的股票中选择
- 候选按 `circ_mv` 升序排序
- `circ_mv is None` 的候选排在最后

- [ ] **Step 2: 在 `HotThemeFactorEnricher` 中取消复杂 leader 主判定**

实现约束：
- `theme_leader_score` 若保留，只作为兼容字段，不再承载复杂五维含义
- `entry_reason` 优先体现“涨停”
- 不再把 turnover / breakout / MA100 作为龙头主规则

- [ ] **Step 3: 在 `FactorService` / pipeline 中接入规则式 leader 结果**

实现约束：
- 主链路能拿到用于排序的 `is_limit_up` 与 `circ_mv`
- 对热点题材内股票，能输出 leader 标记或 leader 候选标记
- 缺失题材上下文时保持降级，不报错

- [ ] **Step 4: 运行目标测试并确认转绿**

Run: `python -m pytest tests/test_hot_theme_factor_enricher.py tests/test_five_layer_pipeline.py tests/test_factor_service.py -v`

Expected:
- PASS
- 龙头判定结果由规则而非综合分主导

---

### Task 3: Align Sector And Candidate Pool Semantics

**Files:**
- Modify: `src/services/sector_heat_engine.py`
- Modify: `src/services/candidate_pool_classifier.py`
- Modify: `src/services/theme_position_resolver.py`
- Modify: `tests/test_decision_modules.py`
- Modify: `tests/test_theme_services.py`

- [ ] **Step 1: 写失败测试，锁定板块层与候选池层的新语义**

建议新增断言：

```python
def test_leader_candidate_count_counts_limit_up_stocks_only(self):
    self.assertEqual(result.leader_candidate_count, 2)

def test_non_theme_stock_cannot_enter_leader_pool_without_limit_up(self):
    self.assertEqual(result, CandidatePoolLevel.WATCHLIST)

def test_main_theme_limit_up_stock_can_enter_leader_pool(self):
    self.assertEqual(result, CandidatePoolLevel.LEADER_POOL)
```

- [ ] **Step 2: 在 `SectorHeatEngine` 中改成规则式统计**

实现约束：
- `leader_candidate_count` 统计同板块内涨停股数量
- `leader_codes` 取板块内涨停股，按 `circ_mv` 升序输出
- `front_codes` 可保留现有涨幅逻辑，但不能再被解释成龙头列表

- [ ] **Step 3: 在 `CandidatePoolClassifier` 中简化准入逻辑**

实现约束：
- 不再依赖 `extreme_strength_score`
- `leader_pool` 至少要求：
  - `theme_position in (main_theme, secondary_theme)`
  - 且 `is_limit_up == True`
- 非主线题材或非涨停股默认不进 `leader_pool`

- [ ] **Step 4: 运行测试并确认转绿**

Run: `python -m pytest tests/test_decision_modules.py tests/test_theme_services.py tests/test_five_layer_pipeline.py -v`

Expected:
- PASS
- `leader_pool` 回到“主线题材涨停龙头池”的语义

---

### Task 4: Remove Unneeded Complex Scoring Dependencies

**Files:**
- Modify: `src/services/leader_score_calculator.py`
- Modify: `tests/test_leader_score_calculator.py`
- Modify: `src/services/hot_theme_factor_enricher.py`

- [ ] **Step 1: 写失败测试，锁定“复杂打分不再主导 leader 结论”**

建议断言：

```python
def test_non_limit_up_stock_does_not_win_even_with_higher_legacy_score(self):
    self.assertEqual(leader_code, "000001")

def test_smaller_circ_mv_wins_even_if_turnover_or_trend_is_weaker(self):
    self.assertEqual(leader_code, "000002")
```

- [ ] **Step 2: 收敛 `LeaderScoreCalculator` 的职责**

实现约束：
- 若仍保留该文件，仅作为兼容层存在
- 不再要求新增复杂权重
- 相关测试改成“兼容字段仍可计算，但不参与主判定”

- [ ] **Step 3: 删除或弱化多余解释路径**

实现约束：
- `entry_reason` 以“涨停”或“同题材最小流通市值涨停股”为主
- 避免继续输出误导性的“综合高分即龙头”解释

- [ ] **Step 4: 运行测试并确认转绿**

Run: `python -m pytest tests/test_leader_score_calculator.py tests/test_hot_theme_factor_enricher.py -v`

Expected:
- PASS
- 复杂分数被降级为兼容信息而不是主决策

---

### Task 5: Add Observability And Documentation

**Files:**
- Modify: `src/services/five_layer_pipeline.py`
- Modify: `src/services/sector_heat_engine.py`
- Modify: `tests/test_five_layer_pipeline.py`
- Modify: `docs/strategy_system_refactor_plan.md`

- [ ] **Step 1: 写失败测试，锁定新的日志字段**

建议断言：

```python
def test_pipeline_stats_include_limit_up_based_leader_counters(self):
    self.assertIn("limit_up_count", stats)
    self.assertIn("leader_candidate_count_by_board", stats)
    self.assertIn("leader_pool_candidate_preview", stats)
```

- [ ] **Step 2: 补齐日志与观测字段**

至少补：
- `limit_up_count`
- `leader_candidate_count_by_board`
- `leader_pool_count_by_theme_position`
- `leader_pool_candidate_preview`
- `leader_rule = "limit_up_then_smallest_circ_mv"`

- [ ] **Step 3: 同步文档口径**

更新 [docs/strategy_system_refactor_plan.md](/e:/daily_stock_analysis/docs/strategy_system_refactor_plan.md:1)：
- 龙头识别简化为两条规则
- 不再以复杂 `leader_score` 作为主判定
- `front_codes` 与 `leader_codes` 的语义区分

- [ ] **Step 4: 运行测试并确认转绿**

Run: `python -m pytest tests/test_five_layer_pipeline.py -v`

Expected:
- PASS
- 日志足以说明“为什么这只股票被视为龙头”

---

### Task 6: Full Verification Pass

**Files:**
- Verify changed Python files
- Verify changed docs

- [ ] **Step 1: 运行目标测试集合**

Run:

```bash
python -m pytest \
  tests/test_factor_service.py \
  tests/test_hot_theme_factor_enricher.py \
  tests/test_five_layer_pipeline.py \
  tests/test_decision_modules.py \
  tests/test_leader_score_calculator.py \
  tests/test_theme_services.py -v
```

Expected: PASS

- [ ] **Step 2: 运行非网络回归**

Run: `python -m pytest -m "not network"`

Expected: PASS or clearly documented unrelated failures

- [ ] **Step 3: 编译检查改动文件**

Run:

```bash
python -m py_compile \
  src/services/factor_service.py \
  src/services/hot_theme_factor_enricher.py \
  src/services/five_layer_pipeline.py \
  src/services/sector_heat_engine.py \
  src/services/candidate_pool_classifier.py \
  src/services/theme_position_resolver.py \
  src/services/leader_score_calculator.py \
  src/services/leader_stock_selector.py
```

Expected: no output

- [ ] **Step 4: 按新规则核对验收标准**

人工/日志检查：
- 热点题材中仅涨停股会进入龙头候选
- 多只涨停股时，龙头为流通市值最小者
- `leader_candidate_count` 与板块涨停分布一致
- `leader_pool` 中的股票绝大多数属于 `main_theme / secondary_theme`
- 解释字段能体现“涨停”和“流通市值最小”两个判定依据

---

## Suggested Execution Order

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6

## Risks To Watch

- 若某些数据源的 `circ_mv` 缺失率较高，可能导致同题材多只涨停股无法稳定比较，需要明确缺失值排序规则
- 规则简化后，可解释性会提升，但会损失对“非涨停强势龙头”的覆盖能力；这是本轮有意取舍
- 现有依赖 `leader_score` 的模块如果未完全切换语义，可能出现“字段名还在，含义已变”的兼容风险

## Rollback Plan

1. 回退 `LeaderStockSelector` 的规则式选择逻辑
2. 回退 `SectorHeatEngine` 与 `CandidatePoolClassifier` 的规则式 leader 统计
3. 恢复 `leader_score/extreme_strength_score` 为主判定逻辑
4. 保留新增测试，按旧语义重写或临时 `xfail`

## Notes

- 本计划默认不执行 `git commit`，与仓库 `AGENTS.md` 保持一致
- 当前方案是“简化识别”，不是“保留复杂评分后再加一层规则”，落地时应优先删除主判定中的复杂依赖
