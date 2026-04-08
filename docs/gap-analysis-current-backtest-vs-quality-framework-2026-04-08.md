# 现有回测系统与质量规范差距分析报告

**日期**：2026-04-08  
**适用项目**：`daily_stock_analysis`  
**分析对象（已审阅代码）**：
- `src/core/backtest_engine.py`
- `src/services/backtest_service.py`
- `src/repositories/backtest_repo.py`
- `src/repositories/stock_repo.py`
- `src/storage.py`
- `api/v1/endpoints/backtest.py`
- `api/v1/schemas/backtest.py`
- `src/agent/tools/backtest_tools.py`
- `tests/test_backtest_engine.py`
- `tests/test_backtest_service.py`
- `tests/test_backtest_summary.py`

**对照规范**：
- 回测质量控制与验证框架
- 回测输入、时机与信号类型评估口径规范
- 回测执行假设与成交模型规范
- 回测统计指标与优化建议生成规范
- 五层交易系统回测质量审查总清单

---

## 一、执行结论（先说人话）

当前项目里的 backtest 系统，**本质上仍然是一个“分析建议文本回测器”**，而不是“五层交易系统回测器”。

它已经具备的优点是：
- 结构清晰
- 逻辑纯净
- 有基本的 DB 持久化与汇总能力
- 有单元测试 / 集成测试
- 已经考虑了一个基础版的“同日止盈止损先后不明”问题

但如果按我们刚建立的质量框架来审，它和目标系统之间仍然存在**结构性差距**，不是小修小补就能补平的。

### 一句话判断
> **现有 backtest 可以保留为“旧版建议回测器 / 兼容层”，但不能作为未来五层交易系统回测主引擎继续演进。**

更准确一点：
- 适合继续保留：**是**
- 适合直接扩展成五层质量回测主系统：**不太适合**
- 适合作为兼容旧数据、对照新系统的 baseline：**非常适合**

---

## 二、现有系统到底在回测什么

从 `BacktestEngine.evaluate_single()` 和 `BacktestService.run_backtest()` 看，当前回测的核心对象是：

### 输入对象
- `AnalysisHistory`
- `operation_advice`
- `stop_loss`
- `take_profit`
- `analysis_date`
- 对应股票的 forward daily bars

### 核心逻辑
1. 从 `operation_advice` 文本推断：
   - `direction_expected`：up/down/not_down/flat
   - `position_recommendation`：long/cash
2. 用未来 N 天日线的最终涨跌幅判断：
   - `outcome = win/loss/neutral`
   - `direction_correct`
3. 对 long 仓位，检查：
   - 是否命中止损
   - 是否命中止盈
   - 哪个先触发
4. 给出：
   - `simulated_return_pct`

### 结论
它现在评估的是：

> “当时那句文本建议，大方向说得对不对；如果按简化 long-only 逻辑执行，收益大概怎样。”

它**没有在回测**：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `trade_plan`
- 五层系统的逐层门控是否有效

所以从系统定位上看，和目标回测体系是两代产品。

---

## 三、按质量框架逐组做差距分析

---

## A 组：回测输入数据差距

### 当前状态
现有回测数据源来自：
- `analysis_history`
- `stock_daily`

### 已满足
- 有明确的历史记录表 `analysis_history`
- 有快照字段 `operation_advice / stop_loss / take_profit`
- 能通过 `context_snapshot` 解析一部分日期信息
- 有回测结果表 `backtest_results`
- 有汇总表 `backtest_summaries`

### 关键差距
#### 1. 回测对象仍是 `AnalysisHistory`，不是 `screening_candidates`
这意味着现有系统天然围绕：
- 分析建议
而不是围绕：
- 五层决策快照

#### 2. 缺少五层字段输入
现有 `BacktestResult` 不保存：
- `market_regime`
- `theme_position`
- `candidate_pool_level`
- `setup_type`
- `entry_maturity`
- `trade_stage`
- `trade_plan_json`

虽然这些字段已经存在于 `screening_candidates`，但当前 backtest 流程完全没接入。

#### 3. Snapshot / Replay 语义不存在
当前系统没有区分：
- 历史真实快照回测
- 规则重演实验

它只有一种模式：
- 直接从 `AnalysisHistory` 取旧记录做回测

### 结论
**差距级别：HIGH**

这不是补几个字段就行，而是回测对象层级都不同。

---

## B 组：回测时机与模式差距

### 当前状态
`BacktestService.run_backtest()` 的时机语义是：
- 从历史分析记录中挑选已足够 old 的样本（`min_age_days`）
- 判断 forward bars 是否充足
- 然后做一次后验评估

### 已满足
- 有“样本成熟后再评估”的基本意识
- `min_age_days` 能粗略避免窗口未成熟就回测
- 支持 `force` 重算
- 支持按 `eval_window_days` 与 `engine_version` 区分结果版本

### 关键差距
#### 1. 没有真实区分三类模式
当前没有区分：
- snapshot backtest
- replay experiment
- parameter calibration

#### 2. `force` 不等于 replay 模式
现在的 `force=True` 只是覆盖已有结果，并不是：
- 用新规则重跑历史
- 记录 replay version
- 对比不同规则版本

#### 3. engine_version 只有字符串标签，没有实验语义
这只能算基础版本标签，不足以承载：
- 执行模型版本
- 规则版本
- 数据口径版本
- snapshot/replay 区别

### 结论
**差距级别：HIGH**

现有系统有“后验评估”的壳，但没有“多模式回测框架”。

---

## C 组：信号类型评估机制差距

### 当前状态
现有 `BacktestEngine` 通过 `operation_advice` 文本，把信号压成：
- bullish → up + long
- bearish → down + cash
- hold → not_down + long
- wait → flat + cash

然后统一走一套：
- outcome = win/loss/neutral
- direction_correct = bool/None

### 已满足
- 至少意识到不同 advice 有不同语义
- `buy / sell / hold / wait` 并非完全同处理
- 对 `sell` / `wait` 这类 cash 信号，不计算 long simulated entry

### 关键差距
#### 1. 买入 / 卖出 / 观望没有分 evaluator
当前本质还是统一口径，只是参数稍有差异。

#### 2. `观望` 被定义为 `flat`
这是最典型的问题之一。
当前测试里甚至明确写了：
- `观望` 后股票跌 5%，结果算 loss

但按我们刚建立的质量规范：
- 观望不该简单按“后来有没有显著涨跌”定对错
- 应评估是否避免低质量时机、是否等待到更优入场

#### 3. `卖出` 被当成“看跌方向正确性”
当前 `卖出` 逻辑更像：
- 如果后面跌了，那卖出就是 win

但未来目标系统中，卖出类应该重点评估：
- 风险规避价值
- 错卖率
- 机会成本
而不是只看方向。

### 结论
**差距级别：HIGH**

这部分不改，未来观望类和风险控制类回测一定会失真。

---

## D 组：执行假设与成交模型差距

### 当前状态
现有执行逻辑非常简化：
- start_price = analysis_date 对应 close
- long 仓位默认按 start_price 入场
- 止盈止损用 future daily bar high/low 触发
- 同日双触发 → `ambiguous`，默认按 stop_loss first
- 未触发时 → 按窗口末 close 结算

### 已满足
- 已经意识到“同一根日线无法确定止盈止损先后”
- 在 ambiguous 场景采用偏保守处理（stop-loss first）
- long-only 模型简单一致，容易解释

### 关键差距
#### 1. 默认按 analysis_date close 入场
但 `AnalysisHistory` 很大概率是收盘后生成的分析结果。按当天收盘价成交，天然偏乐观。

#### 2. 没有涨停买不到 / 跌停卖不掉
A 股关键限制完全没建模。

#### 3. 没有 gap 跳空滑点模型
如果次日直接低开跌破止损，当前仍可能按 stop_loss 价格离场，偏理想化。

#### 4. 没有 execution_model 字段
当前结果表里没有：
- `execution_model`
- `entry_timing`
- `entry_fill_status`
- `gap_adjusted`
- `limit_blocked`

### 结论
**差距级别：VERY HIGH**

这部分是现有系统与目标质量规范差距最大的一块之一。

---

## E 组：统计指标差距

### 当前状态
现有汇总指标包括：
- total / completed / insufficient
- long_count / cash_count
- win/loss/neutral
- direction_accuracy_pct
- win_rate_pct
- avg_stock_return_pct
- avg_simulated_return_pct
- stop_loss_trigger_rate
- take_profit_trigger_rate
- ambiguous_rate
- avg_days_to_first_hit
- advice_breakdown
- diagnostics

### 已满足
- 已经不只是看一个收益数字
- 有方向正确率、触发率、advice 分布等基础诊断
- 汇总结构清晰、API 能直接读

### 关键差距
#### 1. 没有中位数 / 分位数 / 分布指标
当前主要是均值与比率，容易被极端样本拉偏。

#### 2. 没有 MAE / MFE 汇总
虽然单条 bar 可推出 high/low 区间，但汇总层并未构造成买点质量核心指标。

#### 3. 没有稳定性统计
没有：
- 月度分段
- regime 分桶
- setup 分桶
- theme_position 分桶

#### 4. 没有结论分级
系统不会区分：
- 观察现象
- 假设结论
- 可执行优化建议

### 结论
**差距级别：MEDIUM-HIGH**

作为旧系统够用，但远不足以支撑五层规则优化。

---

## F 组：样本量与稳定性差距

### 当前状态
现有系统基本只做：
- 汇总总数
- 汇总 win/loss/neutral

没有单独的样本门槛机制。

### 已满足
- 至少有 `total_evaluations` / `completed_count`
- 结果不是完全黑箱

### 关键差距
#### 1. 没有最小样本门槛
系统不会阻止：
- 在极少样本上生成看起来很强的结论

#### 2. 没有时间稳定性分析
当前 summary 是整体汇总，不看时间切片。

#### 3. 没有跨环境稳定性
因为根本没接五层字段，也谈不上跨 regime / theme / pool 的稳定性。

### 结论
**差距级别：HIGH**

如果以后直接基于现有 summary 做策略优化，非常容易被噪声误导。

---

## G 组：归因与解释差距

### 当前状态
现有系统可以解释：
- 这条 advice 后来涨跌如何
- 是否命中止损/止盈
- 汇总 advice 分布如何

### 已满足
- 结果并非完全不可解释
- 单条 backtest result 可追溯到 `analysis_history_id`
- 有 `advice_breakdown` 和 `diagnostics`

### 关键差距
#### 1. 无法做五层归因
因为现有输入里根本没有五层字段。

#### 2. 无法做消融分析
不能回答：
- 去掉 theme gate 会怎样
- 去掉 candidate pool gate 会怎样
- 只保留 setup_type 会怎样

#### 3. 无法区分“规则问题”还是“执行模型问题”
因为执行模型没有结构化字段。

### 结论
**差距级别：HIGH**

现有系统解释的是“建议对错”，不是“系统哪一层出了问题”。

---

## H 组：优化建议闸门差距

### 当前状态
现有系统本身不会自动生成优化建议。

### 这既是优点，也是限制
#### 优点
- 不会误自动改规则

#### 限制
- 也没有建立“什么结论够资格驱动改规则”的机制

### 关键差距
- 没有 suggestion schema
- 没有 observation / hypothesis / actionable 分级
- 没有 replay 复核闭环

### 结论
**差距级别：MEDIUM**

当前系统尚未走到这一步，但未来如果要接优化闭环，必须新建，而不是靠现有 summary 硬凑。

---

## 四、现有系统中哪些东西值得保留

虽然差距很大，但现有系统并不是应该推倒重来。里面有几块很值得保留。

---

### 1）`BacktestEngine` 的“纯逻辑内核”设计
优点：
- 纯函数化倾向明显
- DB 无关
- 易测
- 易替换

这说明未来新回测系统也应该沿用这种设计思路：
- 把评估器做成纯逻辑 engine
- service 只负责 orchestration

### 2）`BacktestService` 的编排骨架
优点：
- 有 run → evaluate → save → recompute summary 的清晰流程
- 适合作为未来新 service 的参考骨架

### 3）`BacktestResult` / `BacktestSummary` 这套旧表
它们可以继续保留，作为：
- 旧版 advice backtest 兼容层
- 与新系统并存期间的 baseline 对照层

### 4）测试风格
当前：
- engine 有单测
- service 有集成测试
- summary 有统计单测

这是非常好的基础，未来五层回测系统也应该延续这种测试粒度。

---

## 五、哪些部分不适合继续硬扩展

下面这些位置，我不建议“在旧逻辑上缝缝补补”，而建议新建。

---

### 1）不建议继续以 `operation_advice` 作为主回测入口
因为这会把整个回测视角继续锁死在：
- 文本建议正确性
而不是：
- 五层决策有效性

### 2）不建议继续用 `infer_direction_expected()` 作为核心评价入口
它适合旧系统，但不适合：
- setup quality
- stage quality
- wait signal quality
- risk-off quality

### 3）不建议继续把所有信号压缩成 `long/cash`
这会让：
- watch/focus
- exit/reduce
- add_on_strength
- stand_aside

这些语义全部损失掉。

### 4）不建议在旧 `BacktestSummary` 上硬加过多五层字段
因为旧 summary 的聚合维度是：
- overall / stock

而未来需要的是：
- regime
- theme_position
- candidate_pool_level
- setup_type
- trade_stage
- 组合条件

这基本是新 summary 模型，不是旧表平滑演进能优雅承载的。

---

## 六、我对“现有系统应该怎么处理”的建议

### 建议定位
把当前系统正式定位为：

> **Legacy Advice Backtest（旧版建议回测器）**

用途：
- 保留已有 API 与数据可用性
- 保留对 `AnalysisHistory` 的评估能力
- 作为新五层回测系统的 baseline / 对照组

而不是让它承担：
- 五层交易系统主回测
- 优化闭环主引擎

---

## 七、建议的新旧系统关系

### 旧系统保留
- `src/core/backtest_engine.py`
- `src/services/backtest_service.py`
- `backtest_results`
- `backtest_summaries`

### 新系统新增
- 面向 `screening_candidates` 的新回测入口
- 三类 evaluator：
  - Entry
  - Exit
  - Observation
- 新 execution model 字段
- 新分组 summary / calibration / recommendation 模型

### 两者关系
- 旧系统：回测文本建议
- 新系统：回测五层决策链
- 两者并存一段时间
- 后续主要优化依据逐步迁移到新系统

---

## 八、差距优先级排序（最应该先解决什么）

### Priority 1（最高）
1. **回测对象从 `AnalysisHistory` 切换到 `screening_candidates`**
2. **拆分买入 / 卖出 / 观望三类评估器**
3. **建立执行模型（conservative / baseline / optimistic）**

### Priority 2
4. **引入 snapshot / replay / calibration 三类模式语义**
5. **建立五层字段级 summary 与组合 summary**
6. **补充中位数 / 分位数 / MAE / MFE / 稳定性指标**

### Priority 3
7. **建立优化建议分级与 replay 复核机制**
8. **建立 recommendation schema 和 calibration outputs**

---

## 九、最终结论

### 结论 1
当前 backtest 系统不是坏系统，它只是：

> **评估对象太旧，评估语义太粗。**

### 结论 2
它适合作为：
- 旧版建议回测
- 兼容层
- baseline 对照系统

### 结论 3
它不适合作为：
- 未来五层交易系统回测主引擎
- 规则优化闭环主系统

### 结论 4
正确做法不是推翻它，而是：

> **保留它，冻结它的定位；然后为五层交易系统新建一套回测主链路。**

---

## 十、一句话结论

> 现有 backtest 系统已经能较好完成“历史分析建议回测”这件事，但它与“五层交易系统质量回测框架”之间存在对象层、语义层和执行层的结构性错位；最合理的路线不是在旧系统上继续硬扩，而是保留其兼容价值，同时新建面向 `screening_candidates` 和五层决策字段的新回测主引擎。

---

*写于 2026-04-08：用于基于当前代码实现，审查现有回测系统与已建立质量规范之间的差距，并明确其在未来系统中的合理定位。*
