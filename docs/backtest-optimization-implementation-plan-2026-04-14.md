# 回测模块优化实施方案（修订版）

> 首版日期：2026-04-14  
> 修订日期：2026-04-15  
> 状态：待实施  
> 优先级：P0 → P1 → P2 分三阶段  
> 依据：已结合一次真实运行 `flbt-722f9996f042` 复核当前实现与目标方案的差距

---

## 一、修订背景

本方案最初聚焦于“把回测页面从统计报表改成研究工作台”，但在 2026-04-15 对当前系统做了一次真实运行验证后，确认核心问题并不只是页面层级，而是**回测样本锚点、汇总口径、策略分布和归因语义仍未与目标问题对齐**。

本次真实运行参数：

- 接口：`POST /api/v1/five-layer-backtest/run`
- 区间：`2026-03-16` ~ `2026-04-15`
- `evaluation_mode`：`historical_snapshot`
- `execution_model`：`conservative`
- `market`：`cn`
- `eval_window_days`：`10`

本次真实运行结果：

- `backtest_run_id`：`flbt-722f9996f042`
- `status`：`completed`
- `run.sample_count`：`65`
- `completed_count`：`65`
- `error_count`：`0`
- `summary_count`：`36`
- `recommendation_count`：`2`

关键观察：

- `evaluations.total = 65`
- `entry = 0`
- `observation = 65`
- `overall.summary.sample_count = 10`
- `setup_type` 汇总只有 4 类，但明细 `snapshot_setup_type` 实际至少有 5 类，且 `trend_pullback = 17` 未进入汇总
- `primary_strategy` 基本为空
- `strategy_cohort = 0`
- `entry_timing_label = not_applicable` 覆盖全部明细

结论：

**当前页面虽然已经开始具备“研究工作台”的结构，但当前主运行路径产生的数据仍然更像“日期区间 observation 统计样本”，不是“围绕一次真实选股运行的归因样本”。**

---

## 二、当前最核心的问题

### 2.1 样本锚点错位

当前前端主入口调用的是：

```text
POST /api/v1/five-layer-backtest/run
```

而不是：

```text
POST /api/v1/five-layer-backtest/run/by-screening-run
```

这意味着当前回测主路径仍然是“按日期区间扫样本”，而不是“围绕某次真实选股运行做跟踪回测”。

这与本项目要回答的关键问题不一致：

- 哪只股票为什么入选
- 买点是否识别正确
- 是否已经错过最佳买点
- 哪个策略在真实入选样本里有效
- 哪类样本应该继续观察，哪类应该拒绝

### 2.2 页面上下在看不同批次样本

真实运行中出现了明显的口径分裂：

- 顶部运行上下文：`run.sample_count = 65`
- 页面核心汇总：`overall.sample_count = 10`

如果页面不显式说明“原始样本数”和“可汇总样本数”的差异，用户会自然误以为所有结论都建立在同一批 65 个样本上。

这会直接破坏页面可信度。

### 2.3 策略分布与真实样本分布不一致

本次 `evaluations` 中的 `snapshot_setup_type` 分布为：

- `none = 22`
- `bottom_divergence_breakout = 20`
- `trend_pullback = 17`
- `low123_breakout = 5`
- `trend_breakout = 1`

但 `setup_type` 汇总只返回：

- `bottom_divergence_breakout`
- `low123_breakout`
- `trend_breakout`
- `none`

`trend_pullback` 没有进入 setup 汇总。

这意味着当前左侧“策略分布”并不是对真实明细的忠实映射，而是一个被筛过的子集。

### 2.4 页面核心模块缺少真实语义支撑

本次 run 中：

- `entry = 0`
- `primary_strategy` 为空
- `entry_timing_label = not_applicable`
- `strategy_cohort = 0`
- `profit_factor = null`
- `plan_execution_rate = null`

这直接影响当前页面最重要的几个模块：

- `研究画布`
- `策略结论`
- `证据链与归因`
- `买点时机分布`
- `异常样本区`

它们可以渲染，但无法稳定回答“买点是否正确”“策略是否真正有效”。

### 2.5 已有数据能力没有进入页面主叙事

本次 run 已经返回：

- `RankingEffectiveness`
- `Recommendations = 2`

说明后端开始具备“分级有效性”和“调权建议”的能力。

但当前页面对它们的处理仍然偏弱：

- `RankingEffectiveness` 只被压缩成非常轻的提示信息
- `Recommendations` 没有进入主页面叙事

---

## 三、目标状态

本轮优化后的回测系统，要围绕“真实选股结果验证”来工作，而不是围绕“某段日期内的统计样本展示”来工作。

目标状态分为 4 层：

### 3.1 运行入口层

默认入口切到 `screening_run_id` 驱动：

- 主路径：按真实选股运行回测
- 辅路径：按日期区间做回放或补充验证

默认研究页应优先回答：

- 这是哪次选股运行
- 这次选股最终进入回测的样本有哪些
- 哪些是可交易样本，哪些只是观察样本

### 3.2 统计口径层

同一页面所有结论必须来自同一套可解释口径：

- 原始候选数
- 实际评估样本数
- entry 样本数
- observation 样本数
- 被抑制或被过滤的样本数

如果存在阈值压缩，页面必须能解释：

- 哪些样本被压掉
- 为什么被压掉
- 汇总结论建立在哪一层样本上

### 3.3 研究层

页面应能稳定回答：

- 哪个策略在真实选股结果里有效
- 哪类 trade stage / entry maturity 判断有效
- 哪些 observation 样本是正确等待，哪些是误判
- 哪些 entry 样本是偏早、偏晚、刚好
- 哪些策略在 P0 重点验证链路里表现异常

### 3.4 归因层

研究页应能拿到并展示：

- `primary_strategy`
- `contributing_strategies`
- `strategy_cohort_context`
- `sample_bucket`
- `entry_timing_label`
- `ma100_low123_validation_status`
- `factor_snapshot_json`
- `trade_plan_json`

如果这些字段缺失，不应该强行给“研究结论”，而应进入“数据不完备 / 当前仅适合观察研究”的降级态。

---

## 四、实施总原则

1. 先修样本锚点，再修页面叙事  
2. 先统一 run / summary / evaluations 口径，再做视觉层优化  
3. 先打通 `screening_run -> backtest -> summaries/evaluations -> page` 主链路，再做策略专项验证  
4. 日期区间回测保留，但降级为辅助入口，不再作为主研究入口  
5. 所有阶段都必须配真实运行验证，不能只看单测通过

---

## 五、实施方案

## Phase P0：修正主路径和统计口径

### P0-1 切换前端主入口到 `screening_run_id`

目标：

- 研究工作台默认不再直接围绕日期区间发起回测
- 页面默认优先选择最近一次 `screening run`
- 调用主接口改为：

```text
POST /api/v1/five-layer-backtest/run/by-screening-run
```

涉及文件：

- `apps/dsa-web/src/api/backtest.ts`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

完成标准：

- 页面能展示最近可用 `screening run`
- 主运行按钮默认走 `screening_run_id`
- 日期区间入口保留，但明确为“回放模式”或“辅助模式”

### P0-2 统一 run / summaries / evaluations 的样本口径

目标：

- 消除 `run.sample_count = 65`，但 `overall.sample_count = 10` 这类不可解释分裂
- 明确区分：
  - 原始样本数
  - 可汇总样本数
  - entry 样本数
  - observation 样本数
  - suppressed 样本数

涉及文件：

- `src/backtest/services/backtest_service.py`
- `src/backtest/aggregators/group_summary_aggregator.py`
- `src/backtest/models/backtest_models.py`
- `api/v1/schemas/five_layer_backtest.py`
- `tests/test_five_layer_aggregator.py`
- `tests/test_five_layer_backtest_models.py`
- `tests/test_five_layer_phase4_api.py`

完成标准：

- 页面上下看到的是同一套可解释样本基线
- 如有压缩阈值，返回里有明确原因

### P0-3 修复 `setup_type` 汇总漏策略问题

目标：

- 明细中出现的有效 `snapshot_setup_type` 不应无故丢失
- 至少要做到：
  - 进入汇总
  - 或在响应里显式标记“被抑制，不参与展示”

当前已知问题：

- `trend_pullback = 17` 出现在明细中，但不在 `setup_type` 汇总中

涉及文件：

- `src/backtest/aggregators/group_summary_aggregator.py`
- `src/backtest/services/backtest_service.py`
- `tests/test_five_layer_aggregator.py`

完成标准：

- 策略导航与真实策略分布一致
- 页面左侧不会再误导用户

### P0-4 保证真实运行里稳定产出 `entry`

目标：

- 基于 `screening_run_id` 的主路径必须能稳定得到可分析的 `entry` 样本
- 不能再出现 observation-only 成为默认常态

涉及文件：

- `src/backtest/services/backtest_service.py`
- `src/backtest/models/backtest_models.py`
- `src/services/factor_service.py`
- `tests/test_five_layer_phase4_api.py`

完成标准：

- 至少能得到可分析的 `entry`
- `entry_timing_label`、`forward_return_5d`、`plan_success` 在 entry 样本上有真实意义

---

## Phase P1：让研究页变成可信研究页

### P1-1 顶部上下文改为“双上下文”

目标：

- 页面明确区分：
  - 运行上下文：`screening_run_id` / `backtest_run_id`
  - 研究上下文：entry / observation / suppressed 的实际数量

涉及文件：

- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

完成标准：

- 用户一眼看出页面当前结论建立在哪批样本上

### P1-2 把 `RankingEffectiveness` 升级为主叙事

目标：

- 不再只显示“分级有效/仍需观察”
- 直接展示：
  - 哪个维度有效
  - 哪个维度无效
  - 对应样本量
  - 高低层级差异

涉及文件：

- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/components/backtest/StrategyResearchCanvas.tsx`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

### P1-3 把 `Recommendations` 接入研究结论区

目标：

- 当前 run 已经能返回建议，但页面没有把它转成策略动作
- 页面需要能回答：
  - 哪个 setup 该加权
  - 哪类信号该观察
  - 哪类样本量还不够，只能 display

涉及文件：

- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/components/backtest/StrategyResearchCanvas.tsx`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

### P1-4 加入“研究降级态”

目标：

- 当真实数据缺失关键归因字段时，页面不应强行输出研究结论
- 需要明确提示：
  - 当前 observation 主导
  - 当前无主策略归因
  - 当前仅适合做观察研究，不适合买点结论

涉及文件：

- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/components/backtest/StrategyResearchCanvas.tsx`
- `apps/dsa-web/src/components/backtest/EvaluationDetail.tsx`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

---

## Phase P2：回到策略专项验证

### P2-1 对 P0 策略做真实链路验证

重点策略：

- `bottom_divergence_double_breakout`
- `low123_breakout`
- `ma100_low123_combined`

目标：

- 这三类策略在 `screening_run -> backtest -> group summary -> page` 链路上都能拿到完整研究语义：
  - `primary_strategy`
  - `contributing_strategies`
  - `sample_bucket`
  - `entry_timing_label`
  - `strategy_cohort_context`

涉及文件：

- `src/backtest/services/backtest_service.py`
- `src/backtest/aggregators/group_summary_aggregator.py`
- `src/backtest/aggregators/system_grader.py`
- `tests/test_five_layer_aggregator.py`
- `tests/test_five_layer_phase4_api.py`

### P2-2 把 conservative mode 的拒绝语义显式展示

目标：

- `breakout_bar_index` 缺失导致的保守拒绝，不应只是后端隐性状态
- 页面应能单独看见：
  - 被保守拒绝的样本量
  - 原因
  - 受影响策略
  - 是否属于数据完备性问题

涉及文件：

- `src/backtest/services/backtest_service.py`
- `src/backtest/models/backtest_models.py`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/components/backtest/StrategyResearchCanvas.tsx`
- `tests/test_five_layer_phase4_api.py`

---

## 六、文件清单

### 后端

- `src/backtest/services/backtest_service.py`
- `src/backtest/aggregators/group_summary_aggregator.py`
- `src/backtest/aggregators/system_grader.py`
- `src/backtest/models/backtest_models.py`
- `api/v1/endpoints/five_layer_backtest.py`
- `api/v1/schemas/five_layer_backtest.py`

### 前端

- `apps/dsa-web/src/api/backtest.ts`
- `apps/dsa-web/src/types/backtest.ts`
- `apps/dsa-web/src/pages/BacktestPage.tsx`
- `apps/dsa-web/src/components/backtest/StrategyResearchCanvas.tsx`
- `apps/dsa-web/src/components/backtest/EvaluationDetail.tsx`
- `apps/dsa-web/src/components/backtest/StrategyWorkbenchSidebar.tsx`
- `apps/dsa-web/src/pages/__tests__/BacktestPage.test.tsx`

### 测试

- `tests/test_five_layer_aggregator.py`
- `tests/test_five_layer_backtest_models.py`
- `tests/test_five_layer_phase4_api.py`

---

## 七、实施顺序建议

建议严格按下面顺序推进：

1. 先完成 `P0-1`：切换主入口到 `screening_run_id`
2. 再完成 `P0-2`：统一 run / summary / evaluations 样本口径
3. 再完成 `P0-3`：修 setup_type 汇总漏策略问题
4. 再完成 `P0-4`：确保真实主路径里能稳定产出 entry
5. 完成一次真实 `screening_run_id` 回测复核
6. 在数据链路稳定后，再做 `P1`
7. 最后做 `P2` 的策略专项验证

**不建议**在 `P0` 未完成前继续做页面布局或视觉微调。

---

## 八、验收标准

### P0 验收标准

- 研究工作台默认走 `screening_run_id`
- 真实 run 不再 observation-only
- `run.sample_count`、`overall.sample_count`、`evaluations.total` 的关系可解释
- `setup_type` 汇总与明细策略分布一致或显式标记抑制原因

### P1 验收标准

- 页面顶部能明确说明当前研究样本基线
- `RankingEffectiveness` 和 `Recommendations` 进入主叙事
- 数据不完备时，页面进入明确降级态

### P2 验收标准

- P0 策略能稳定拿到完整归因链
- conservative mode 的关键拒绝原因可被页面解释

---

## 九、验证矩阵

### 后端验证

```bash
python -m pytest tests/test_five_layer_aggregator.py -v
python -m pytest tests/test_five_layer_backtest_models.py -v
python -m pytest tests/test_five_layer_phase4_api.py -v
```

### 前端验证

```bash
cd apps/dsa-web
npm test -- src/pages/__tests__/BacktestPage.test.tsx
npm run build
```

### 真实运行验证

至少做两次：

1. 当前旧路径：

```text
POST /api/v1/five-layer-backtest/run
```

2. 新主路径：

```text
POST /api/v1/five-layer-backtest/run/by-screening-run
```

对比项：

- entry / observation 占比
- `run.sample_count`
- `overall.sample_count`
- `setup_type` 汇总完整性
- `primary_strategy`
- `strategy_cohort`
- `entry_timing_label`
- `recommendations`

---

## 十、风险与边界

### 10.1 当前最大风险

如果继续让日期区间回测作为研究工作台主入口，那么页面再怎么调整，最终也只是一个“更好看的统计页”，而不是“围绕真实选股结果的研究页”。

### 10.2 兼容性风险

- 新旧路径会并存一段时间
- 日期区间模式仍需保留，避免回放能力丢失
- 前端需要明确区分“研究模式”和“回放模式”

### 10.3 数据完备性风险

- 历史样本可能没有完整 `primary_strategy`
- 历史样本可能没有完整 `strategy_cohort_context`
- 历史 observation 样本可能天然不具备买点研究语义

因此页面必须支持降级态，不能假设所有运行都适合输出完整研究结论。

### 10.4 不在本轮范围内

以下内容不作为本轮优先任务：

- 重新设计五层回测引擎本体
- 重写策略 YAML 规则
- 大规模重构筛选策略检测器
- 继续做页面纯视觉层微调

---

## 十一、最终判断

本次修订后的方案结论非常明确：

**当前回测模块的首要任务，不是继续修页面，而是先把“回测到底在研究哪批样本”这件事做对。**

只有当主路径切到 `screening_run_id`，并且 run / summaries / evaluations 的口径对齐之后，研究工作台上的“策略分布、研究结论、判断验证、样本浏览器”才会真正有意义。
